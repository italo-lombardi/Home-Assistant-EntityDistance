/**
 * Entity Distance Card
 * Lovelace custom card for the Entity Distance integration.
 */

const CARD_VERSION = "0.1.0";

console.info(
  `%c ENTITY-DISTANCE-CARD %c v${CARD_VERSION} %c`,
  "color: white; background: #2196f3; font-weight: bold; padding: 2px 6px; border-radius: 3px 0 0 3px;",
  "color: #2196f3; background: #e3f2fd; font-weight: bold; padding: 2px 6px;",
  "color: #9e9e9e; background: #e3f2fd; padding: 2px 6px; border-radius: 0 3px 3px 0;"
);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "entity-distance-card",
  name: "Entity Distance Card",
  description: "Shows distance, direction, proximity status, and time-together stats for a configured entity pair.",
  preview: true,
  documentationURL: "https://github.com/italo-lombardi/Home-Assistant-EntityDistance",
});

customElements.whenDefined("ha-panel-lovelace").then(() => {
  if (customElements.get("entity-distance-card")) return;

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

  function _slug(id) { return id.startsWith("sensor.entity_distance_") ? id.replace("sensor.entity_distance_", "").replace(/_distance$/, "") : null; }

  function _getPairs(hass) {
    return Object.keys(hass.states)
      .filter(id => id.startsWith("sensor.entity_distance_") && id.endsWith("_distance"))
      .map(id => {
        const slug = _slug(id);
        const label = _pairLabel(hass, slug);
        return { slug, label };
      })
      .sort((a, b) => a.label.localeCompare(b.label));
  }

  function _pairLabel(hass, slug) {
    const distState = hass.states[`sensor.entity_distance_${slug}_distance`];
    if (distState?.attributes?.friendly_name) {
      return distState.attributes.friendly_name
        .replace(/^Entity Distance[^\w]*/i, "")
        .replace(/\s*[-—]?\s*Distance\s*$/i, "")
        .replace(" — ", " & ") || slug;
    }
    return slug.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  }

  function _s(hass, slug, suffix) {
    return hass.states[`sensor.entity_distance_${slug}_${suffix}`] || null;
  }

  function _val(hass, slug, suffix, fallback = null) {
    const s = _s(hass, slug, suffix);
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
    if (min === 0) return "0 min";
    if (min < 1) return "< 1 min";
    if (min >= 60) {
      const h = Math.floor(min / 60);
      const m = Math.round(min % 60);
      return m > 0 ? `${h}h ${m}m` : `${h}h`;
    }
    return `${Math.round(min)} min`;
  }

  function _formatDate(isoStr) {
    if (!isoStr || isoStr === "unknown" || isoStr === "unavailable") return null;
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return null;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
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

  function _zoneColor(bucket) {
    if (bucket === "very_near") return "#4caf50";
    if (bucket === "near") return "#8bc34a";
    if (bucket === "mid") return "#ff9800";
    if (bucket === "far") return "#ff5722";
    if (bucket === "very_far") return "#9e9e9e";
    return null;
  }

  function _dirIcon(dir) {
    if (dir === "approaching") return "↓";
    if (dir === "diverging") return "↑";
    if (dir === "stationary") return "•";
    return "?";
  }

  function _dirColor(dir) {
    if (dir === "approaching") return "var(--edc-approach, #4caf50)";
    if (dir === "diverging") return "var(--edc-diverge, #f44336)";
    return "var(--secondary-text-color)";
  }

  // ─── card styles ─────────────────────────────────────────────────────────────

  const cardStyles = css`
    :host {
      --edc-approach: #4caf50;
      --edc-diverge: #f44336;
      --edc-proximity-on: #4caf50;
      --edc-proximity-off: #9e9e9e;
      --edc-divider: var(--divider-color, rgba(0,0,0,0.12));
      user-select: text;
    }

    ha-card { overflow: hidden; }

    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 16px 16px 12px;
      gap: 8px;
    }
    .compact .card-header { padding: 12px 16px 8px; }

    .pair-title {
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
      overflow: hidden;
    }

    .pair-title-icon {
      font-size: 1.2rem;
      flex-shrink: 0;
    }

    .pair-title-text {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      font-size: 16px;
      color: var(--primary-text-color);
    }

    .pair-title-text strong {
      font-weight: 700;
    }

    .pair-title-text .pair-suffix {
      font-weight: 400;
      color: var(--secondary-text-color);
    }

    .prox-badge {
      font-size: 0.72rem;
      font-weight: 600;
      padding: 3px 10px;
      border-radius: 12px;
      white-space: nowrap;
      flex-shrink: 0;
    }
    .prox-badge.on {
      background: #4caf5022;
      color: var(--edc-proximity-on);
      border: 1px solid #4caf5055;
    }
    .prox-badge.off {
      background: #9e9e9e18;
      color: var(--edc-proximity-off);
      border: 1px solid #9e9e9e44;
    }

    .divider { height: 1px; background: var(--edc-divider); margin: 0 16px; }

    /* ── hero row ── */
    .hero {
      display: flex;
      align-items: center;
      padding: 14px 16px 10px;
      gap: 16px;
    }
    .compact .hero { padding: 10px 16px 8px; }

    .distance-block { flex: 1; min-width: 0; }

    .distance-value {
      font-size: 2.6rem;
      font-weight: 700;
      color: var(--primary-text-color);
      line-height: 1;
      white-space: nowrap;
    }
    .compact .distance-value { font-size: 2rem; }

    .zone-label {
      font-size: 0.75rem;
      color: var(--secondary-text-color);
      margin-top: 4px;
      text-transform: capitalize;
    }

    .direction-block {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 2px;
      min-width: 44px;
    }

    .dir-icon {
      font-size: 1.8rem;
      line-height: 1;
    }
    .compact .dir-icon { font-size: 1.4rem; }

    .dir-label {
      font-size: 0.62rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }

    /* ── stats rows (movement) ── */
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

    /* ── stat boxes ── */
    .stat-boxes {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      padding: 8px 16px 12px;
    }
    .compact .stat-boxes { padding: 6px 16px 8px; gap: 6px; }

    .stat-box {
      min-width: 0;
      background: var(--secondary-background-color, rgba(0,0,0,0.04));
      border-radius: 10px;
      padding: 10px 12px;
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .stat-box.full-width { grid-column: 1 / -1; }
    .compact .stat-box { padding: 7px 10px; border-radius: 8px; }

    .stat-box-label {
      font-size: 0.72rem;
      color: var(--secondary-text-color);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .stat-box-value {
      font-size: 1.1rem;
      font-weight: 700;
      color: var(--primary-text-color);
      white-space: nowrap;
    }
    .compact .stat-box-value { font-size: 0.95rem; }

    .stat-box-sub {
      font-size: 0.68rem;
      color: var(--secondary-text-color);
      margin-top: 1px;
    }

    /* ── zone breakdown chips ── */
    .zone-breakdown { padding: 4px 16px 12px; }

    .zone-breakdown-title {
      font-size: 0.72rem;
      font-weight: 600;
      color: var(--secondary-text-color);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      padding: 0 0 6px;
    }

    .zone-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }

    .zone-chip {
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 6px 12px;
      border-radius: 20px;
      background: var(--secondary-background-color, rgba(0,0,0,0.04));
      border: 1px solid var(--divider-color, rgba(0,0,0,0.1));
      min-width: 60px;
    }

    .zone-chip-label {
      font-size: 0.68rem;
      color: var(--secondary-text-color);
      white-space: nowrap;
    }

    .zone-chip-value {
      font-size: 0.85rem;
      font-weight: 700;
      color: var(--primary-text-color);
      white-space: nowrap;
    }

    /* ── diagnostic section ── */
    .diag-section { padding: 0 16px 10px; }

    .diag-title {
      font-size: 0.72rem;
      font-weight: 600;
      color: var(--secondary-text-color);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      padding: 6px 0 4px;
    }

    .diag-cols {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0 12px;
    }

    .diag-col-header {
      font-size: 0.72rem;
      font-weight: 600;
      color: var(--secondary-text-color);
      padding: 2px 0 4px;
      border-bottom: 1px solid var(--divider-color, rgba(0,0,0,0.1));
      margin-bottom: 4px;
    }

    .diag-item {
      display: flex;
      flex-direction: column;
      padding: 3px 0;
    }

    .diag-item-label {
      font-size: 0.72rem;
      color: var(--secondary-text-color);
    }

    .diag-item-value {
      font-size: 0.82rem;
      font-weight: 500;
      color: var(--primary-text-color);
    }

    .error-msg {
      padding: 16px;
      color: var(--error-color, #db4437);
      font-size: 14px;
    }
  `;

  // ─── card ────────────────────────────────────────────────────────────────────

  class EntityDistanceCard extends LitElement {
    static get properties() {
      return {
        hass: { attribute: false },
        _config: { state: true },
      };
    }

    static get styles() { return cardStyles; }

    static getConfigElement() {
      return document.createElement("entity-distance-card-editor");
    }

    static getStubConfig(hass) {
      const pairs = _getPairs(hass);
      const slug = pairs.length > 0 ? pairs[0].slug : "";
      return {
        slug,
        show_distance: true,
        show_direction: true,
        show_zone: true,
        show_proximity_badge: true,
        show_speed: true,
        show_eta: true,
        show_proximity_duration: false,
        show_today_time: true,
        show_last_seen: false,
        show_today_zone_times: false,
        show_gps_accuracy: false,
        show_last_update: false,
        show_update_count: false,
        compact: false,
      };
    }

    setConfig(config) {
      if (!config.slug) throw new Error("entity-distance-card: 'slug' is required.");
      this._config = {
        show_distance: true,
        show_direction: true,
        show_zone: true,
        show_proximity_badge: true,
        show_speed: true,
        show_eta: true,
        show_proximity_duration: false,
        show_today_time: true,
        show_last_seen: false,
        show_today_zone_times: false,
        show_gps_accuracy: false,
        show_last_update: false,
        show_update_count: false,
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
      const base = [
        `binary_sensor.entity_distance_${slug}_in_proximity`,
        `${p}_distance`, `${p}_direction`, `${p}_direction_level`, `${p}_proximity_zone`,
        `${p}_approach_speed`, `${p}_estimated_arrival_time`,
        `${p}_proximity_duration`, `${p}_today_proximity_time`,
        `${p}_last_seen_together`,
        `${p}_today_very_near_time`, `${p}_today_near_time`,
        `${p}_today_medium_time`, `${p}_today_far_time`,
        `${p}_today_very_far_time`,
      ];
      const dynamic = Object.keys(this.hass?.states || {}).filter(id =>
        id.startsWith(`${p}_gps_accuracy_`) ||
        id.startsWith(`${p}_last_update_`) ||
        id.startsWith(`${p}_update_count_`)
      );
      const distState = this.hass?.states[`${p}_distance`];
      const entityA = distState?.attributes?.entity_a;
      const entityB = distState?.attributes?.entity_b;
      if (entityA) base.push(entityA);
      if (entityB) base.push(entityB);
      return [...base, ...dynamic];
    }

    render() {
      if (!this._config || !this.hass) return html``;
      const { slug } = this._config;

      if (!slug) {
        return html`<ha-card><div class="error-msg">No entity pair configured.</div></ha-card>`;
      }

      const proxState = this.hass.states[`binary_sensor.entity_distance_${slug}_in_proximity`];
      if (!proxState) {
        return html`<ha-card><div class="error-msg">Pair "${slug}" not found. Check integration is loaded.</div></ha-card>`;
      }

      const c = this._config;
      const isProx = proxState.state === "on";
      const rawLabel = this._config.title || _pairLabel(this.hass, slug);
      // Bold each name, non-bold the connector and any suffix like " Distance"
      // rawLabel should be "Italo & Dercy" after _pairLabel strips device/sensor name
      const ampIdx = rawLabel.indexOf(" & ");
      const boldLabel = ampIdx >= 0
        ? html`<strong>${rawLabel.slice(0, ampIdx)}</strong><span class="pair-suffix"> &amp; </span><strong>${rawLabel.slice(ampIdx + 3).replace(/\s*distance\s*$/i, "")}</strong>`
        : html`<strong>${rawLabel.replace(/\s*distance\s*$/i, "")}</strong>`;
      const compactClass = c.compact ? "compact" : "";

      const distM = _num(this.hass, slug, "distance");
      const direction = _val(this.hass, slug, "direction");
      const bucket = _val(this.hass, slug, "proximity_zone");
      const speedKmh = _num(this.hass, slug, "approach_speed");
      const etaMin = _num(this.hass, slug, "estimated_arrival_time");
      const proxDurMin = _num(this.hass, slug, "proximity_duration");
      const proxTrackingStarted = _val(this.hass, slug, "proximity_tracking_started");
      const todayMin = _num(this.hass, slug, "today_proximity_time");
      const lastSeen = _val(this.hass, slug, "last_seen_together");

      const bucketLabel = bucket ? bucket.replace(/_/g, " ") : null;
      const zoneColor = bucket ? _zoneColor(bucket) : null;
      const dirColor = _dirColor(direction);

      return html`
        <ha-card class="${compactClass}">
          <!-- header -->
          <div class="card-header">
            <div class="pair-title">
              <span class="pair-title-icon">📍</span>
              <span class="pair-title-text">${boldLabel}</span>
            </div>
            ${c.show_proximity_badge ? html`
              <span class="prox-badge ${isProx ? "on" : "off"}">
                ${isProx ? "In Proximity" : "Not in Proximity"}
              </span>` : nothing}
          </div>

          <div class="divider"></div>

          <!-- hero: distance + direction -->
          ${c.show_distance || c.show_direction ? html`
            <div class="hero">
              ${c.show_distance ? html`
                <div class="distance-block">
                  <div class="distance-value" style="${zoneColor ? `color:${zoneColor}` : ""}">${_formatDistance(distM)}</div>
                  ${c.show_zone && bucketLabel ? html`<div class="zone-label" style="${zoneColor ? `color:${zoneColor};opacity:0.8` : ""}">${bucketLabel}</div>` : nothing}
                </div>` : nothing}
              ${c.show_direction && direction ? html`
                <div class="direction-block" style="color:${dirColor}">
                  <div class="dir-icon">${_dirIcon(direction)}</div>
                  <div class="dir-label">${direction}</div>
                </div>` : nothing}
            </div>
            <div class="divider"></div>` : nothing}

          <!-- movement stat boxes -->
          ${this._hasMovementStats() ? html`
            <div class="stat-boxes">
              ${c.show_speed && speedKmh !== null ? html`
                <div class="stat-box" style="background:rgba(14,165,233,0.1);border:1px solid rgba(14,165,233,0.25)">
                  <span class="stat-box-label">💨 Approach speed</span>
                  <span class="stat-box-value" style="color:#0284c7">${speedKmh.toFixed(1)} km/h</span>
                </div>` : nothing}
              ${c.show_eta && direction === "approaching" && etaMin !== null ? html`
                <div class="stat-box" style="background:rgba(168,85,247,0.1);border:1px solid rgba(168,85,247,0.25)">
                  <span class="stat-box-label">⏱ ETA</span>
                  <span class="stat-box-value" style="color:#9333ea">${_formatMinutes(etaMin)}</span>
                </div>` : nothing}
            </div>
            ${this._hasTimeStats() || this._hasDiagnostics() ? html`<div class="divider"></div>` : nothing}
          ` : nothing}

          <!-- time-together stat boxes -->
          ${this._hasTimeStats() ? html`${(() => {
            const showDur = c.show_proximity_duration && proxDurMin !== null;
            const showToday = c.show_today_time && todayMin !== null;
            const showLast = c.show_last_seen;
            const count = [showDur, showToday, showLast].filter(Boolean).length;
            const lastFull = count % 2 === 1; // odd count → last item spans full width
            const lastIdx = [showDur, showToday, showLast].lastIndexOf(true);
            return html`
              <div class="stat-boxes">
                ${showDur ? html`
                  <div class="stat-box ${lastIdx === 0 && lastFull ? "full-width" : ""}" style="background:rgba(99,102,241,0.12);border:1px solid rgba(99,102,241,0.25)">
                    <span class="stat-box-label">⏳ Proximity duration</span>
                    <span class="stat-box-value" style="color:#6366f1">${_formatMinutes(proxDurMin)}</span>
                    ${proxTrackingStarted ? html`<span class="stat-box-sub">since ${_formatDate(proxTrackingStarted)}</span>` : nothing}
                  </div>` : nothing}
                ${showToday ? html`
                  <div class="stat-box ${lastIdx === 1 && lastFull ? "full-width" : ""}" style="background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.25)">
                    <span class="stat-box-label">📅 Together today</span>
                    <span class="stat-box-value" style="color:#16a34a">${_formatMinutes(todayMin)}</span>
                  </div>` : nothing}
                ${showLast ? html`
                  <div class="stat-box ${lastIdx === 2 && lastFull ? "full-width" : ""}" style="background:rgba(251,146,60,0.1);border:1px solid rgba(251,146,60,0.25)">
                    <span class="stat-box-label">👁 Last seen together</span>
                    <span class="stat-box-value" style="color:#ea580c">${_formatTs(lastSeen)}</span>
                  </div>` : nothing}
              </div>`;
          })()}
            ${c.show_today_zone_times ? nothing : (this._hasDiagnostics() ? html`<div class="divider"></div>` : nothing)}
          ` : nothing}

          <!-- zone breakdown chips -->
          ${c.show_today_zone_times ? html`
            <div class="zone-breakdown">
              <div class="zone-breakdown-title">🗺 Time by zone today</div>
              <div class="zone-chips">
                ${["very_near", "near", "mid", "far", "very_far"].map(z => {
                  const suffix = z === "mid" ? "today_medium_time" : `today_${z}_time`;
                  const min = _num(this.hass, slug, suffix);
                  if (min === null || min === 0) return nothing;
                  const zLabel = z === "mid" ? "Medium" : z.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
                  return html`
                    <div class="zone-chip">
                      <span class="zone-chip-label">${zLabel}</span>
                      <span class="zone-chip-value">${_formatMinutes(min)}</span>
                    </div>`;
                })}
              </div>
            </div>
            ${this._hasDiagnostics() ? html`<div class="divider"></div>` : nothing}
          ` : nothing}

          <!-- diagnostics -->
          ${this._hasDiagnostics() ? html`
            <div class="diag-section">
              <div class="diag-title">🔬 Diagnostics</div>
              ${this._renderDiagCols(slug, c)}
            </div>
          ` : nothing}

        </ha-card>
      `;
    }

    _diagItem(label, value) {
      return html`
        <div class="diag-item">
          <span class="diag-item-label">${label}</span>
          <span class="diag-item-value">${value}</span>
        </div>`;
    }

    // Get person name from entity_id basename.
    _personNameFromId(entityId) {
      if (!entityId) return null;
      const s = this.hass.states[entityId];
      if (s?.attributes?.friendly_name) return s.attributes.friendly_name;
      return entityId.replace(/^[^.]+\./, "").replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
    }

    // Returns { a: {metric, val}, b: {metric, val} } ordered by entity_a/entity_b from distance sensor.
    _diagSplit(slug, prefix, unit, isTs) {
      const p = `sensor.entity_distance_${slug}_${prefix}`;
      const distState = this.hass.states[`sensor.entity_distance_${slug}_distance`];
      const entityA = distState?.attributes?.entity_a;
      const entityB = distState?.attributes?.entity_b;
      // Derive expected name suffixes from entity friendly names (lowercase, no spaces)
      const nameA = entityA ? this._personNameFromId(entityA) : null;
      const nameB = entityB ? this._personNameFromId(entityB) : null;

      const ids = Object.keys(this.hass.states).filter(id => id.startsWith(p));

      const _parse = (id) => {
        const s = this.hass.states[id];
        const rawLabel = s?.attributes?.friendly_name || id.replace(`sensor.entity_distance_${slug}_`, "");
        const afterDevice = rawLabel.includes(" — ") ? rawLabel.slice(rawLabel.lastIndexOf(" — ") + 3) : rawLabel;
        const parenMatch = afterDevice.match(/^(.+?)\s*\((.+?)\)\s*$/);
        const metric = parenMatch ? parenMatch[1].trim() : afterDevice;
        const rawVal = s && s.state !== "unknown" && s.state !== "unavailable" ? s.state : null;
        let val;
        if (isTs) {
          val = _formatTs(s?.state);
        } else {
          const num = rawVal !== null ? parseFloat(rawVal) : NaN;
          const isInt = unit === "" && !isNaN(num) && Number.isInteger(num);
          val = rawVal === null ? "—" : (!isNaN(num)
            ? `${isInt ? num : num.toFixed(1)}${unit ? " " + unit : ""}`
            : `${rawVal}${unit ? " " + unit : ""}`);
        }
        return { metric, val };
      };

      // Match IDs to A/B by checking if entity friendly name appears in the sensor ID suffix
      let idA = null, idB = null;
      for (const id of ids) {
        const suffix = id.slice(p.length).toLowerCase();
        const aMatch = nameA && suffix.startsWith(nameA.toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, ""));
        if (aMatch) { idA = id; } else { idB = id; }
      }
      // Fallback: if only one entity configured, just use first
      if (!idA && !idB && ids.length > 0) idA = ids[0];
      if (!idA && ids.length > 1) { idA = ids[0]; idB = ids[1]; }

      return {
        a: idA ? _parse(idA) : null,
        b: idB ? _parse(idB) : null,
        nameA, nameB,
      };
    }

    _renderDiagCols(slug, c) {
      const rowsA = [], rowsB = [];
      let nameA = null, nameB = null;

      const addSplit = (prefix, unit, isTs) => {
        const r = this._diagSplit(slug, prefix, unit, isTs);
        if (!nameA && r.nameA) nameA = r.nameA;
        if (!nameB && r.nameB) nameB = r.nameB;
        if (r.a) rowsA.push(r.a);
        if (r.b) rowsB.push(r.b);
      };

      if (c.show_gps_accuracy) addSplit("gps_accuracy_", "m", false);
      if (c.show_last_update) addSplit("last_update_", "", true);
      if (c.show_update_count) addSplit("update_count_", "", false);

      if (!rowsA.length && !rowsB.length) return nothing;

      const _iconFor = (metric) => {
        const m = metric.toLowerCase();
        if (m.includes("gps") || m.includes("accuracy")) return "📡";
        if (m.includes("update") && m.includes("count")) return "🔄";
        if (m.includes("update") || m.includes("last")) return "🕐";
        return "";
      };

      return html`
        <div class="diag-cols">
          <div>
            ${nameA ? html`<div class="diag-col-header">${nameA}</div>` : nothing}
            ${rowsA.map(r => this._diagItem(`${_iconFor(r.metric)} ${r.metric}`, r.val))}
          </div>
          <div>
            ${nameB ? html`<div class="diag-col-header">${nameB}</div>` : nothing}
            ${rowsB.map(r => this._diagItem(`${_iconFor(r.metric)} ${r.metric}`, r.val))}
          </div>
        </div>`;
    }

    _hasMovementStats() {
      const c = this._config;
      return c.show_speed || c.show_eta;
    }

    _hasTimeStats() {
      const c = this._config;
      return c.show_proximity_duration || c.show_today_time || c.show_last_seen;
    }

    _hasDiagnostics() {
      const c = this._config;
      return c.show_gps_accuracy || c.show_last_update || c.show_update_count;
    }
  }

  customElements.define("entity-distance-card", EntityDistanceCard);

  // ─── editor ──────────────────────────────────────────────────────────────────

  class EntityDistanceCardEditor extends LitElement {
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
      `;
    }

    setConfig(config) { this._config = config; }

    _update(key, value) {
      if (!this._config) return;
      const cfg = { ...this._config, [key]: value };
      if (value === undefined) delete cfg[key];
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

          <div class="section-title">Main Display</div>
          ${this._checkRow("show_distance", "Show distance")}
          ${this._checkRow("show_direction", "Show direction (approaching / diverging / stationary)")}
          ${this._checkRow("show_zone", "Show proximity zone label (Very Near … Very Far)")}
          ${this._checkRow("show_proximity_badge", "Show proximity badge (In Proximity / Not in Proximity)")}

          <div class="section-title">Movement</div>
          ${this._checkRow("show_speed", "Show approach speed (km/h)")}
          ${this._checkRow("show_eta", "Show ETA (only when approaching)")}

          <div class="section-title">Time Together</div>
          ${this._checkRow("show_proximity_duration", "Show total proximity duration")}
          ${this._checkRow("show_today_time", "Show time together today")}
          ${this._checkRow("show_last_seen", "Show last seen together")}
          ${this._checkRow("show_today_zone_times", "Show today's time per zone (Very Near, Near, …)")}

          <div class="section-title">Diagnostics</div>
          ${this._checkRow("show_gps_accuracy", "Show GPS accuracy (A & B)")}
          ${this._checkRow("show_last_update", "Show last update time (A & B)")}
          ${this._checkRow("show_update_count", "Show update count — last 30 min (A & B)")}

          <div class="section-title">Layout</div>
          ${this._checkRow("compact", "Compact mode")}

        </div>
      `;
    }
  }

  customElements.define("entity-distance-card-editor", EntityDistanceCardEditor);

}); // end whenDefined
