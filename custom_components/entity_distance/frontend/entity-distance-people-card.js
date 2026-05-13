/**
 * Entity Distance People Card
 * Lovelace custom card for the Entity Distance integration.
 * People-focused layout: two avatars side-by-side with distance in the middle.
 */

const PEOPLE_CARD_VERSION = "0.1.0";

console.info(
  `%c ENTITY-DISTANCE-PEOPLE-CARD %c v${PEOPLE_CARD_VERSION} %c`,
  "color: white; background: #9c27b0; font-weight: bold; padding: 2px 6px; border-radius: 3px 0 0 3px;",
  "color: #9c27b0; background: #f3e5f5; font-weight: bold; padding: 2px 6px;",
  "color: #9e9e9e; background: #f3e5f5; padding: 2px 6px; border-radius: 0 3px 3px 0;"
);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "entity-distance-people-card",
  name: "Entity Distance People Card",
  description: "Shows two people's avatars side-by-side with distance, direction, and proximity stats for a configured entity pair.",
  preview: true,
  documentationURL: "https://github.com/italo-lombardi/Home-Assistant-EntityDistance",
});

customElements.whenDefined("ha-panel-lovelace").then(() => {
  if (customElements.get("entity-distance-people-card")) return;

  const haPanel = customElements.get("ha-panel-lovelace");
  if (!haPanel) return;
  const LitElement = Object.getPrototypeOf(haPanel);
  const { html, nothing } = LitElement.prototype;

  const css = LitElement.prototype.css || (() => {
    class CSSResult {
      constructor(t) { this.cssText = t; }
      toString() { return this.cssText; }
    }
    return (strings, ...values) => new CSSResult(
      strings.reduce((acc, s, i) => acc + s + (values[i] != null ? String(values[i]) : ""), "")
    );
  })();

  // ─── helpers ────────────────────────────────────────────────────────────────

  function _slug(id) {
    return id.startsWith("binary_sensor.entity_distance_")
      ? id.replace("binary_sensor.entity_distance_", "").replace("_proximity", "")
      : null;
  }

  function _getPairs(hass) {
    return Object.keys(hass.states)
      .filter(id => id.startsWith("binary_sensor.entity_distance_") && id.endsWith("_proximity"))
      .map(id => {
        const slug = _slug(id);
        const label = _pairLabel(hass, slug);
        return { slug, label };
      })
      .sort((a, b) => a.label.localeCompare(b.label));
  }

  function _pairLabel(hass, slug) {
    const proxId = `binary_sensor.entity_distance_${slug}_proximity`;
    const state = hass.states[proxId];
    if (state?.attributes?.friendly_name) {
      return state.attributes.friendly_name.replace(/^Entity Distance[^\w]*/i, "").replace(" — ", " & ") || slug;
    }
    return slug.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  }

  function _val(hass, slug, suffix, fallback = null) {
    const s = hass.states[`sensor.entity_distance_${slug}_${suffix}`] || null;
    if (!s || s.state === "unknown" || s.state === "unavailable") return fallback;
    return s.state;
  }

  function _num(hass, slug, suffix) {
    const v = _val(hass, slug, suffix);
    if (v === null) return null;
    const n = parseFloat(v);
    return isNaN(n) ? null : n;
  }

  function _formatDistance(m) {
    if (m === null || m === undefined) return "—";
    if (m >= 1000) return `${(m / 1000).toFixed(1)} km`;
    return `${Math.round(m)} m`;
  }

  function _formatMinutes(min) {
    if (min === null) return "—";
    if (min < 1) return "< 1 min";
    if (min >= 60) {
      const h = Math.floor(min / 60);
      const m = Math.round(min % 60);
      return m > 0 ? `${h}h ${m}m` : `${h}h`;
    }
    return `${Math.round(min)} min`;
  }

  function _formatTs(isoStr) {
    if (!isoStr || isoStr === "unknown" || isoStr === "unavailable") return "—";
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return "—";
    const now = new Date();
    const diffMs = now - d;
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return "just now";
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffH = Math.floor(diffMin / 60);
    if (diffH < 24) return `${diffH}h ago`;
    const diffD = Math.floor(diffH / 24);
    return `${diffD}d ago`;
  }

  function _dirIcon(dir) {
    if (dir === "approaching") return "↓";
    if (dir === "diverging") return "↑";
    if (dir === "stationary") return "•";
    return "?";
  }

  function _dirColor(dir) {
    if (dir === "approaching") return "var(--edpc-approach, #4caf50)";
    if (dir === "diverging") return "var(--edpc-diverge, #f44336)";
    return "var(--secondary-text-color)";
  }

  /** Generate a deterministic hue from a string for initials avatars. */
  function _nameHue(name) {
    let hash = 0;
    for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
    return Math.abs(hash) % 360;
  }

  /** Get 1-2 initials from a friendly_name or entity_id. */
  function _initials(name) {
    if (!name) return "?";
    const words = name.trim().split(/[\s_]+/).filter(Boolean);
    if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
    return (words[0][0] + words[words.length - 1][0]).toUpperCase();
  }

  /**
   * Derive a display name for one side of the pair.
   * Priority: friendly_name of the entity, then entity_id basename.
   */
  function _personName(hass, entityId) {
    if (!entityId) return null;
    const state = hass.states[entityId];
    if (state?.attributes?.friendly_name) return state.attributes.friendly_name;
    // strip domain
    return entityId.replace(/^[^.]+\./, "").replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  }

  // ─── card styles ─────────────────────────────────────────────────────────────

  const cardStyles = css`
    :host {
      --edpc-approach: #4caf50;
      --edpc-diverge: #f44336;
      --edpc-proximity-on: #4caf50;
      --edpc-proximity-off: #9e9e9e;
      --edpc-divider: var(--divider-color, rgba(0,0,0,0.12));
      --edpc-avatar-size: 56px;
    }

    ha-card { overflow: hidden; }

    .card-header {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 16px 16px 12px;
    }
    .compact .card-header { padding: 12px 16px 8px; }

    .pair-title {
      font-size: 16px;
      font-weight: 500;
      color: var(--primary-text-color);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      text-align: center;
    }

    .divider { height: 1px; background: var(--edpc-divider); margin: 0 16px; }

    /* ── hero row ── */
    .hero {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 16px 20px 12px;
      gap: 0;
    }
    .compact .hero { padding: 12px 20px 8px; }

    /* person column: avatar + name */
    .person-col {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 6px;
      flex: 0 0 auto;
      min-width: 72px;
    }

    .avatar-wrap {
      width: var(--edpc-avatar-size);
      height: var(--edpc-avatar-size);
      border-radius: 50%;
      overflow: hidden;
      border: 2px solid var(--divider-color, rgba(0,0,0,0.15));
      flex-shrink: 0;
    }

    .avatar-wrap img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }

    .avatar-initials {
      width: 100%;
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.1rem;
      font-weight: 700;
      color: #fff;
      letter-spacing: 0.03em;
    }

    .person-name {
      font-size: 0.82rem;
      font-weight: 500;
      color: var(--primary-text-color);
      text-align: center;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 80px;
    }
    .compact .person-name { font-size: 0.78rem; }

    /* middle distance block */
    .middle {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 4px;
      padding: 0 12px;
      min-width: 0;
    }

    .distance-value {
      font-size: 1.9rem;
      font-weight: 700;
      color: var(--primary-text-color);
      line-height: 1;
      white-space: nowrap;
      text-align: center;
    }
    .compact .distance-value { font-size: 1.5rem; }

    .dir-row {
      display: flex;
      align-items: center;
      gap: 4px;
    }

    .dir-icon {
      font-size: 1.1rem;
      line-height: 1;
    }
    .compact .dir-icon { font-size: 0.95rem; }

    .dir-label {
      font-size: 0.72rem;
      text-transform: capitalize;
      white-space: nowrap;
    }

    .zone-label {
      font-size: 0.72rem;
      color: var(--secondary-text-color);
      text-transform: capitalize;
      text-align: center;
    }

    /* ── proximity badge row ── */
    .prox-badge-row {
      display: flex;
      justify-content: center;
      padding: 8px 16px 12px;
    }
    .compact .prox-badge-row { padding: 6px 16px 8px; }

    .prox-badge {
      font-size: 0.72rem;
      font-weight: 600;
      padding: 4px 14px;
      border-radius: 12px;
      white-space: nowrap;
    }
    .prox-badge.on {
      background: #4caf5022;
      color: var(--edpc-proximity-on);
      border: 1px solid #4caf5055;
    }
    .prox-badge.off {
      background: #9e9e9e18;
      color: var(--edpc-proximity-off);
      border: 1px solid #9e9e9e44;
    }

    /* ── stats rows ── */
    .stats { padding: 6px 16px 12px; }
    .compact .stats { padding: 4px 16px 8px; }

    .stat-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 4px 0;
    }
    .compact .stat-row { padding: 3px 0; }

    .stat-label {
      font-size: 0.85rem;
      color: var(--secondary-text-color);
    }
    .compact .stat-label { font-size: 0.8rem; }

    .stat-value {
      font-size: 0.85rem;
      font-weight: 500;
      color: var(--primary-text-color);
    }
    .compact .stat-value { font-size: 0.8rem; }

    .error-msg {
      padding: 16px;
      color: var(--error-color, #db4437);
      font-size: 14px;
    }
  `;

  // ─── card ────────────────────────────────────────────────────────────────────

  class EntityDistancePeopleCard extends LitElement {
    static get properties() {
      return {
        hass: { attribute: false },
        _config: { state: true },
      };
    }

    static get styles() { return cardStyles; }

    static getConfigElement() {
      return document.createElement("entity-distance-people-card-editor");
    }

    static getStubConfig(hass) {
      const pairs = _getPairs(hass);
      const slug = pairs.length > 0 ? pairs[0].slug : "";
      return {
        slug,
        entity_a: "",
        entity_b: "",
        title: "",
        show_direction: true,
        show_zone: true,
        show_proximity_badge: true,
        show_speed: true,
        show_eta: true,
        show_today_time: true,
        show_proximity_duration: false,
        show_last_seen: false,
        compact: false,
      };
    }

    setConfig(config) {
      if (!config.slug) throw new Error("entity-distance-people-card: 'slug' is required.");
      this._config = {
        entity_a: "",
        entity_b: "",
        title: "",
        show_direction: true,
        show_zone: true,
        show_proximity_badge: true,
        show_speed: true,
        show_eta: true,
        show_today_time: true,
        show_proximity_duration: false,
        show_last_seen: false,
        compact: false,
        ...config,
      };
    }

    getCardSize() { return this._config?.compact ? 3 : 4; }

    shouldUpdate(changed) {
      if (changed.has("_config")) return true;
      if (!this.hass) return false;
      const old = changed.get("hass");
      if (!old) return true;
      const slug = this._config?.slug;
      if (!slug) return false;
      const watchIds = this._watchIds(slug);
      return watchIds.some(id => old.states[id] !== this.hass.states[id]);
    }

    _watchIds(slug) {
      const p = `sensor.entity_distance_${slug}`;
      const ids = [
        `binary_sensor.entity_distance_${slug}_proximity`,
        `${p}_distance`, `${p}_direction`, `${p}_bucket`,
        `${p}_closing_speed`, `${p}_eta`,
        `${p}_proximity_duration`, `${p}_today_proximity_time`,
        `${p}_last_seen_together`,
      ];
      if (this._config?.entity_a) ids.push(this._config.entity_a);
      if (this._config?.entity_b) ids.push(this._config.entity_b);
      return ids;
    }

    // Derive pair member names from the pair label (best-effort) if entity_a/b not set.
    _pairNames(slug) {
      const label = _pairLabel(this.hass, slug);
      const parts = label.split(/\s*[&]\s*/);
      return {
        nameA: parts[0]?.trim() || "A",
        nameB: parts[1]?.trim() || "B",
      };
    }

    _renderAvatar(entityId, fallbackName) {
      const hue = _nameHue(fallbackName || entityId || "?");
      if (entityId && this.hass.states[entityId]) {
        const state = this.hass.states[entityId];
        const pic = state.attributes?.entity_picture;
        if (pic) {
          const src = pic.startsWith("/") ? pic : pic;
          return html`
            <div class="avatar-wrap">
              <img src="${src}" alt="${fallbackName}" />
            </div>`;
        }
      }
      // Initials fallback
      const name = (entityId && _personName(this.hass, entityId)) || fallbackName || "?";
      const initials = _initials(name);
      return html`
        <div class="avatar-wrap">
          <div class="avatar-initials"
            style="background: hsl(${hue}, 50%, 45%)">
            ${initials}
          </div>
        </div>`;
    }

    render() {
      if (!this._config || !this.hass) return html``;
      const { slug } = this._config;

      if (!slug) {
        return html`<ha-card><div class="error-msg">No entity pair configured.</div></ha-card>`;
      }

      const proxState = this.hass.states[`binary_sensor.entity_distance_${slug}_proximity`];
      if (!proxState) {
        return html`<ha-card><div class="error-msg">Pair "${slug}" not found. Check integration is loaded.</div></ha-card>`;
      }

      const c = this._config;
      const isProx = proxState.state === "on";
      const title = c.title || _pairLabel(this.hass, slug);
      const compactClass = c.compact ? "compact" : "";

      const distM = _num(this.hass, slug, "distance");
      const direction = _val(this.hass, slug, "direction");
      const bucket = _val(this.hass, slug, "bucket");
      const speedKmh = _num(this.hass, slug, "closing_speed");
      const etaMin = _num(this.hass, slug, "eta");
      const proxDurMin = _num(this.hass, slug, "proximity_duration");
      const todayMin = _num(this.hass, slug, "today_proximity_time");
      const lastSeen = _val(this.hass, slug, "last_seen_together");

      const bucketLabel = bucket ? bucket.replace(/_/g, " ") : null;
      const dirColor = _dirColor(direction);

      const { nameA, nameB } = this._pairNames(slug);
      const entityA = c.entity_a || null;
      const entityB = c.entity_b || null;
      const displayNameA = (entityA && _personName(this.hass, entityA)) || nameA;
      const displayNameB = (entityB && _personName(this.hass, entityB)) || nameB;

      const hasStats = this._hasStats();

      return html`
        <ha-card class="${compactClass}">

          <!-- title -->
          <div class="card-header">
            <span class="pair-title">${title}</span>
          </div>

          <div class="divider"></div>

          <!-- hero: avatar A — distance — avatar B -->
          <div class="hero">
            <!-- person A -->
            <div class="person-col">
              ${this._renderAvatar(entityA, displayNameA)}
              <span class="person-name">${displayNameA}</span>
            </div>

            <!-- middle: distance + direction + zone -->
            <div class="middle">
              <div class="distance-value">${_formatDistance(distM)}</div>
              ${c.show_direction && direction ? html`
                <div class="dir-row" style="color:${dirColor}">
                  <span class="dir-icon">${_dirIcon(direction)}</span>
                  <span class="dir-label">${direction}</span>
                </div>` : nothing}
              ${c.show_zone && bucketLabel ? html`
                <div class="zone-label">${bucketLabel}</div>` : nothing}
            </div>

            <!-- person B -->
            <div class="person-col">
              ${this._renderAvatar(entityB, displayNameB)}
              <span class="person-name">${displayNameB}</span>
            </div>
          </div>

          <!-- proximity badge -->
          ${c.show_proximity_badge ? html`
            <div class="prox-badge-row">
              <span class="prox-badge ${isProx ? "on" : "off"}">
                ${isProx ? "In Proximity" : "Not in Proximity"}
              </span>
            </div>` : nothing}

          ${hasStats ? html`<div class="divider"></div>` : nothing}

          <!-- stats -->
          ${hasStats ? html`
            <div class="stats">
              ${c.show_speed && speedKmh !== null ? html`
                <div class="stat-row">
                  <span class="stat-label">Approach speed</span>
                  <span class="stat-value">${speedKmh.toFixed(1)} km/h</span>
                </div>` : nothing}
              ${c.show_eta && direction === "approaching" && etaMin !== null ? html`
                <div class="stat-row">
                  <span class="stat-label">ETA</span>
                  <span class="stat-value">${_formatMinutes(etaMin)}</span>
                </div>` : nothing}
              ${c.show_today_time && todayMin !== null ? html`
                <div class="stat-row">
                  <span class="stat-label">Together today</span>
                  <span class="stat-value">${_formatMinutes(todayMin)}</span>
                </div>` : nothing}
              ${c.show_proximity_duration && proxDurMin !== null ? html`
                <div class="stat-row">
                  <span class="stat-label">Proximity duration</span>
                  <span class="stat-value">${_formatMinutes(proxDurMin)}</span>
                </div>` : nothing}
              ${c.show_last_seen ? html`
                <div class="stat-row">
                  <span class="stat-label">Last seen together</span>
                  <span class="stat-value">${_formatTs(lastSeen)}</span>
                </div>` : nothing}
            </div>
          ` : nothing}

        </ha-card>
      `;
    }

    _hasStats() {
      const c = this._config;
      return c.show_speed || c.show_eta || c.show_today_time || c.show_proximity_duration || c.show_last_seen;
    }
  }

  customElements.define("entity-distance-people-card", EntityDistancePeopleCard);

  // ─── editor ──────────────────────────────────────────────────────────────────

  class EntityDistancePeopleCardEditor extends LitElement {
    static get properties() {
      return {
        hass: { attribute: false },
        _config: { state: true },
      };
    }

    static get styles() {
      return css`
        .editor { padding: 16px; }
        .section-title {
          font-size: 0.75rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          color: var(--secondary-text-color);
          margin: 16px 0 8px;
          padding-bottom: 4px;
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
        }
        .section-title:first-child { margin-top: 0; }
        .row { margin-bottom: 10px; }
        .row label {
          display: block;
          font-size: 0.85rem;
          font-weight: 500;
          margin-bottom: 4px;
          color: var(--primary-text-color);
        }
        select, input[type="text"] {
          width: 100%;
          padding: 8px;
          border: 1px solid var(--divider-color, #ccc);
          border-radius: 4px;
          box-sizing: border-box;
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color, #212121);
          font-size: 0.9rem;
        }
        .check-row {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 3px 0;
          cursor: pointer;
        }
        .check-row input[type="checkbox"] { width: 16px; height: 16px; cursor: pointer; }
        .check-row span { font-size: 0.88rem; color: var(--primary-text-color); }
        .hint {
          font-size: 0.75rem;
          color: var(--secondary-text-color);
          margin-top: 3px;
        }
      `;
    }

    setConfig(config) { this._config = config; }

    _update(key, value) {
      if (!this._config) return;
      const cfg = { ...this._config, [key]: value };
      if (value === undefined || value === "") delete cfg[key];
      this._config = cfg;
      this.dispatchEvent(new CustomEvent("config-changed", {
        detail: { config: this._config },
        bubbles: true,
        composed: true,
      }));
    }

    _check(key, e) { this._update(key, e.target.checked); }
    _input(key, e) { this._update(key, e.target.value || undefined); }
    _select(key, e) { this._update(key, e.target.value); }

    _checkRow(key, label) {
      return html`
        <label class="check-row">
          <input type="checkbox" .checked=${this._config[key] === true}
            @change=${e => this._check(key, e)} />
          <span>${label}</span>
        </label>`;
    }

    render() {
      if (!this._config) return html``;
      const pairs = _getPairs(this.hass);

      return html`
        <div class="editor">

          <div class="section-title">Entity Pair</div>
          <div class="row">
            <label>Pair</label>
            ${pairs.length === 0 ? html`
              <input type="text" .value=${this._config.slug || ""}
                placeholder="No pairs found — check integration"
                @input=${e => this._input("slug", e)} />
            ` : html`
              <select .value=${this._config.slug || ""}
                @change=${e => this._select("slug", e)}>
                ${pairs.map(p => html`
                  <option value=${p.slug} ?selected=${this._config.slug === p.slug}>
                    ${p.label}
                  </option>`)}
              </select>
            `}
          </div>
          <div class="row">
            <label>Title (optional)</label>
            <input type="text" .value=${this._config.title || ""}
              placeholder="Leave blank to use pair name"
              @input=${e => this._input("title", e)} />
          </div>

          <div class="section-title">People</div>
          <div class="row">
            <label>Person A entity (optional)</label>
            <input type="text" .value=${this._config.entity_a || ""}
              placeholder="person.alice"
              @input=${e => this._input("entity_a", e)} />
            <div class="hint">Used to show avatar photo. Leave blank to show initials.</div>
          </div>
          <div class="row">
            <label>Person B entity (optional)</label>
            <input type="text" .value=${this._config.entity_b || ""}
              placeholder="person.bob"
              @input=${e => this._input("entity_b", e)} />
            <div class="hint">Used to show avatar photo. Leave blank to show initials.</div>
          </div>

          <div class="section-title">Display</div>
          ${this._checkRow("show_direction", "Show direction (approaching / diverging / stationary)")}
          ${this._checkRow("show_zone", "Show proximity zone label (Very Near … Very Far)")}
          ${this._checkRow("show_proximity_badge", "Show proximity badge (In Proximity / Not in Proximity)")}

          <div class="section-title">Movement</div>
          ${this._checkRow("show_speed", "Show approach speed (km/h)")}
          ${this._checkRow("show_eta", "Show ETA (only when approaching)")}

          <div class="section-title">Time Together</div>
          ${this._checkRow("show_today_time", "Show time together today")}
          ${this._checkRow("show_proximity_duration", "Show total proximity duration")}
          ${this._checkRow("show_last_seen", "Show last seen together")}

          <div class="section-title">Layout</div>
          ${this._checkRow("compact", "Compact mode")}

        </div>
      `;
    }
  }

  customElements.define("entity-distance-people-card-editor", EntityDistancePeopleCardEditor);

}); // end whenDefined
