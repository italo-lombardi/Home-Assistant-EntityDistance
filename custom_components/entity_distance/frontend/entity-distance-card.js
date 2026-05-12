/**
 * Entity Distance Card
 * Lovelace custom card for the Entity Distance integration.
 * Displays distance, direction, closing speed, ETA, proximity status,
 * and today's proximity time for a configured entity pair.
 */

class EntityDistanceCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  setConfig(config) {
    if (!config.entity_a || !config.entity_b) {
      throw new Error("entity_a and entity_b are required in card config.");
    }
    this._config = config;
    this.render();
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  _entity(suffix) {
    const entryId = this._config.entry_id;
    if (entryId) {
      return this._hass.states[`sensor.${entryId}_${suffix}`] || null;
    }
    // fallback: search by friendly name pattern using entity_a + entity_b slugs
    const aSlug = this._config.entity_a.split(".")[1];
    const bSlug = this._config.entity_b.split(".")[1];
    const key = `sensor.entity_distance_${aSlug}_${bSlug}_${suffix}`;
    return this._hass.states[key] || null;
  }

  _stateVal(suffix, fallback = "—") {
    const s = this._entity(suffix);
    return s ? s.state : fallback;
  }

  _directionIcon(direction) {
    switch (direction) {
      case "approaching": return "↘";
      case "diverging":   return "↗";
      case "stationary":  return "•";
      default:            return "?";
    }
  }

  _directionColor(direction) {
    switch (direction) {
      case "approaching": return "#4caf50";
      case "diverging":   return "#f44336";
      case "stationary":  return "#9e9e9e";
      default:            return "#9e9e9e";
    }
  }

  _proximityColor(isOn) {
    return isOn ? "#4caf50" : "#9e9e9e";
  }

  _formatDistance(state) {
    if (!state || state === "unknown" || state === "unavailable") return "—";
    const m = parseFloat(state);
    if (isNaN(m)) return "—";
    if (m >= 1000) return `${(m / 1000).toFixed(1)} km`;
    return `${Math.round(m)} m`;
  }

  _entityName(entityId) {
    if (!entityId) return "";
    const state = this._hass.states[entityId];
    if (state && state.attributes.friendly_name) return state.attributes.friendly_name;
    return entityId.split(".")[1].replace(/_/g, " ");
  }

  render() {
    if (!this._config || !this._hass) return;

    const distanceState   = this._entity("distance");
    const proximityKey = Object.keys(this._hass.states).find(k =>
      k.startsWith("binary_sensor.") && k.includes("proximity") &&
      k.includes(this._config.entity_a.split(".")[1])
    );
    const proximityState = proximityKey ? this._hass.states[proximityKey] : null;

    const direction        = this._stateVal("direction");
    const closingSpeed     = this._stateVal("closing_speed");
    const eta              = this._stateVal("eta");
    const todayTime        = this._stateVal("today_proximity_time");
    const bucket           = this._stateVal("bucket");
    const isProximity      = proximityState ? proximityState.state === "on" : false;
    const distFormatted    = this._formatDistance(distanceState ? distanceState.state : null);
    const dirIcon          = this._directionIcon(direction);
    const dirColor         = this._directionColor(direction);
    const proxColor        = this._proximityColor(isProximity);
    const proxLabel        = proximityState
      ? (isProximity ? "In Proximity" : "Not in Proximity")
      : "—";

    const nameA = this._entityName(this._config.entity_a);
    const nameB = this._entityName(this._config.entity_b);

    const etaRow = (direction === "approaching" && eta !== "unknown" && eta !== "—")
      ? `<div class="row">
           <span class="label">ETA</span>
           <span class="value">${parseFloat(eta).toFixed(0)} min</span>
         </div>`
      : "";

    const speedRow = (closingSpeed !== "unknown" && closingSpeed !== "—")
      ? `<div class="row">
           <span class="label">Closing speed</span>
           <span class="value">${parseFloat(closingSpeed).toFixed(1)} km/h</span>
         </div>`
      : "";

    const todayRow = (todayTime !== "unknown" && todayTime !== "—")
      ? `<div class="row">
           <span class="label">Together today</span>
           <span class="value">${parseFloat(todayTime).toFixed(0)} min</span>
         </div>`
      : "";

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--paper-font-body1_-_font-family, sans-serif);
        }
        ha-card {
          padding: 16px;
          box-sizing: border-box;
        }
        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 16px;
        }
        .entities {
          font-size: 1rem;
          font-weight: 600;
          color: var(--primary-text-color);
        }
        .entities span.sep {
          margin: 0 6px;
          color: var(--secondary-text-color);
          font-weight: 400;
        }
        .proximity-badge {
          font-size: 0.75rem;
          font-weight: 600;
          padding: 3px 10px;
          border-radius: 12px;
          background: ${proxColor}22;
          color: ${proxColor};
          border: 1px solid ${proxColor}55;
        }
        .distance-row {
          display: flex;
          align-items: center;
          gap: 12px;
          margin-bottom: 16px;
        }
        .distance {
          font-size: 2.8rem;
          font-weight: 700;
          color: var(--primary-text-color);
          line-height: 1;
        }
        .direction-block {
          display: flex;
          flex-direction: column;
          align-items: center;
        }
        .direction-icon {
          font-size: 2rem;
          color: ${dirColor};
          line-height: 1;
        }
        .direction-label {
          font-size: 0.65rem;
          color: ${dirColor};
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .bucket {
          font-size: 0.75rem;
          color: var(--secondary-text-color);
          margin-bottom: 12px;
          text-transform: capitalize;
        }
        .divider {
          border: none;
          border-top: 1px solid var(--divider-color, #e0e0e0);
          margin: 12px 0;
        }
        .row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 4px 0;
        }
        .label {
          font-size: 0.85rem;
          color: var(--secondary-text-color);
        }
        .value {
          font-size: 0.85rem;
          font-weight: 500;
          color: var(--primary-text-color);
        }
      </style>
      <ha-card>
        <div class="header">
          <div class="entities">
            ${nameA}<span class="sep">↔</span>${nameB}
          </div>
          <div class="proximity-badge">${proxLabel}</div>
        </div>

        <div class="distance-row">
          <div class="distance">${distFormatted}</div>
          <div class="direction-block">
            <div class="direction-icon">${dirIcon}</div>
            <div class="direction-label">${direction !== "—" ? direction : ""}</div>
          </div>
        </div>

        ${bucket !== "—" && bucket !== "unknown"
          ? `<div class="bucket">${bucket.replace(/_/g, " ")}</div>`
          : ""}

        <hr class="divider"/>

        ${speedRow}
        ${etaRow}
        ${todayRow}
      </ha-card>
    `;
  }

  static getConfigElement() {
    return document.createElement("entity-distance-card-editor");
  }

  static getStubConfig() {
    return {
      entity_a: "person.alice",
      entity_b: "person.bob",
    };
  }

  getCardSize() {
    return 3;
  }
}

/**
 * Simple visual editor for the card.
 */
class EntityDistanceCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  setConfig(config) {
    this._config = config;
    this.render();
  }

  set hass(hass) {
    this._hass = hass;
  }

  _valueChanged(field, e) {
    const val = e.target.value;
    this.dispatchEvent(new CustomEvent("config-changed", {
      detail: { config: { ...this._config, [field]: val } },
      bubbles: true,
      composed: true,
    }));
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        .row { margin-bottom: 12px; }
        label { display: block; font-size: 0.85rem; margin-bottom: 4px; color: var(--secondary-text-color); }
        input {
          width: 100%;
          box-sizing: border-box;
          padding: 6px 8px;
          border: 1px solid var(--divider-color, #ccc);
          border-radius: 4px;
          font-size: 0.9rem;
          background: var(--card-background-color);
          color: var(--primary-text-color);
        }
      </style>
      <div class="row">
        <label>Entity A</label>
        <input type="text" value="${this._config.entity_a || ""}" placeholder="person.alice"
          @change="${this._valueChanged.bind(this, "entity_a")}"/>
      </div>
      <div class="row">
        <label>Entity B</label>
        <input type="text" value="${this._config.entity_b || ""}" placeholder="person.bob"
          @change="${this._valueChanged.bind(this, "entity_b")}"/>
      </div>
    `;

    this.shadowRoot.querySelectorAll("input").forEach((input) => {
      const field = input.previousElementSibling.textContent.trim() === "Entity A" ? "entity_a" : "entity_b";
      input.addEventListener("change", this._valueChanged.bind(this, field));
    });
  }
}

customElements.define("entity-distance-card", EntityDistanceCard);
customElements.define("entity-distance-card-editor", EntityDistanceCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "entity-distance-card",
  name: "Entity Distance Card",
  description: "Shows distance, direction, ETA, and proximity status for an entity pair.",
  preview: false,
});
