/**
 * Entity Distance Group Card
 * Lovelace custom card for the Entity Distance integration.
 * Force-directed graph: one circle per entity, lines between every pair.
 */

const GROUP_CARD_VERSION = "0.2.0";

console.info(
  `%c ENTITY-DISTANCE-GROUP-CARD %c v${GROUP_CARD_VERSION} %c — github.com/italo-lombardi`,
  "color: white; background: #009688; font-weight: bold; padding: 2px 6px; border-radius: 3px 0 0 3px;",
  "color: #009688; background: #e0f2f1; font-weight: bold; padding: 2px 6px;",
  "color: #9e9e9e; background: #e0f2f1; padding: 2px 6px; border-radius: 0 3px 3px 0;"
);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "entity-distance-group-card",
  name: "Entity Distance — Group Card",
  description: "Force-directed graph showing all entities in a group with distance, direction, and proximity on each connecting line.",
  preview: true,
  documentationURL: "https://github.com/italo-lombardi/Home-Assistant-EntityDistance",
});

customElements.whenDefined("ha-panel-lovelace").then(() => {
  if (customElements.get("entity-distance-group-card")) return;

  const haPanel = customElements.get("ha-panel-lovelace");
  if (!haPanel) return;
  const LitElement = Object.getPrototypeOf(haPanel);
  const { html, svg, nothing } = LitElement.prototype;

  const css = LitElement.prototype.css || (() => {
    class CSSResult {
      constructor(t) { this.cssText = t; }
      toString() { return this.cssText; }
    }
    return (strings, ...values) => new CSSResult(
      strings.reduce((acc, s, i) => acc + s + (values[i] != null ? String(values[i]) : ""), "")
    );
  })();

  // ─── constants ───────────────────────────────────────────────────────────────

  const NODE_RADIUS = 32;
  const MIN_EDGE_PX = 80;
  const MAX_EDGE_PX = 280;
  const REPULSION = 4500;
  const SPRING_K = 0.04;
  const DAMPING = 0.72;
  const SETTLE_STEPS = 180;
  const IDLE_STEPS = 2;
  const IDLE_ALPHA = 0.008;
  const IDLE_TIMEOUT_MS = 6000;

  // ─── helpers ─────────────────────────────────────────────────────────────────

  function _zoneColor(bucket) {
    if (bucket === "very_near") return "#4caf50";
    if (bucket === "near") return "#8bc34a";
    if (bucket === "mid") return "#ff9800";
    if (bucket === "far") return "#ff5722";
    if (bucket === "very_far") return "#9e9e9e";
    return "#9e9e9e";
  }

  function _dirArrow(dir) {
    if (dir === "approaching") return "↓";
    if (dir === "diverging") return "↑";
    if (dir === "stationary") return "•";
    return "";
  }

  function _formatDistance(m) {
    if (m === null || m === undefined) return "—";
    if (m >= 1000) return `${(m / 1000).toFixed(1)} km`;
    return `${Math.round(m)} m`;
  }

  function _nameHue(name) {
    let hash = 0;
    for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
    return Math.abs(hash) % 360;
  }

  function _initials(name) {
    if (!name) return "?";
    const words = name.trim().split(/[\s_]+/).filter(Boolean);
    if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
    return (words[0][0] + words[words.length - 1][0]).toUpperCase();
  }

  function _personName(hass, entityId) {
    if (!entityId) return entityId || "?";
    const s = hass.states[entityId];
    if (s?.attributes?.friendly_name) return s.attributes.friendly_name;
    return entityId.replace(/^[^.]+\./, "").replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  }

  function _entityStateLabel(hass, entityId) {
    if (!entityId) return null;
    const s = hass.states[entityId];
    if (!s || s.state === "unknown" || s.state === "unavailable") return null;
    const state = s.state;
    if (state === "home") return "Home";
    if (state === "not_home") return "Away";
    const zone = hass.states[`zone.${state}`];
    if (zone?.attributes?.friendly_name) return zone.attributes.friendly_name;
    return state.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  }

  function _entityPicture(hass, entityId) {
    if (!entityId) return null;
    return hass.states[entityId]?.attributes?.entity_picture || null;
  }

  /**
   * Discover all pairs in hass.states that involve only entities from the given list.
   * Returns array of { slug, entityA, entityB, distEntityId }
   */
  function _getPairsForEntities(hass, entities) {
    const entitySet = new Set(entities);
    return Object.values(hass.states)
      .filter(s =>
        s.entity_id.startsWith("sensor.") &&
        s.entity_id.endsWith("_distance") &&
        s.attributes?.entity_a != null &&
        entitySet.has(s.attributes.entity_a) &&
        entitySet.has(s.attributes.entity_b)
      )
      .map(s => ({
        slug: s.entity_id.slice("sensor.".length, -"_distance".length),
        entityA: s.attributes.entity_a,
        entityB: s.attributes.entity_b,
        distEntityId: s.entity_id,
      }));
  }

  /**
   * Discover all distinct groups in hass.states.
   * Returns array of { entities: [...], label: "..." }
   */
  function _discoverGroups(hass) {
    const pairSensors = Object.values(hass.states).filter(s =>
      s.entity_id.startsWith("sensor.") &&
      s.entity_id.endsWith("_distance") &&
      s.attributes?.entity_a != null
    );

    // Build adjacency to find clusters
    const adj = new Map();
    for (const s of pairSensors) {
      const a = s.attributes.entity_a;
      const b = s.attributes.entity_b;
      if (!adj.has(a)) adj.set(a, new Set());
      if (!adj.has(b)) adj.set(b, new Set());
      adj.get(a).add(b);
      adj.get(b).add(a);
    }

    // Find connected components
    const visited = new Set();
    const groups = [];
    for (const start of adj.keys()) {
      if (visited.has(start)) continue;
      const component = [];
      const queue = [start];
      while (queue.length) {
        const node = queue.shift();
        if (visited.has(node)) continue;
        visited.add(node);
        component.push(node);
        for (const neighbor of (adj.get(node) || [])) {
          if (!visited.has(neighbor)) queue.push(neighbor);
        }
      }
      if (component.length >= 2) groups.push(component.sort());
    }

    return groups.map(entities => ({
      entities,
      label: entities.map(e => {
        const s = hass.states[e];
        return s?.attributes?.friendly_name || e.replace(/^[^.]+\./, "").replace(/_/g, " ");
      }).join(" · "),
    }));
  }

  // ─── force simulation ─────────────────────────────────────────────────────────

  class ForceGraph {
    constructor(width, height) {
      this.width = width;
      this.height = height;
      this.nodes = [];
      this.edges = [];
    }

    setNodes(nodes) { this.nodes = nodes; }
    setEdges(edges) { this.edges = edges; }

    tick(alpha = 1.0) {
      const { nodes, edges, width, height } = this;

      // Repulsion between all node pairs
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j];
          const dx = b.x - a.x, dy = b.y - a.y;
          const distSq = dx * dx + dy * dy || 1;
          const dist = Math.sqrt(distSq);
          const force = alpha * REPULSION / distSq;
          const fx = force * dx / dist, fy = force * dy / dist;
          a.vx -= fx; a.vy -= fy;
          b.vx += fx; b.vy += fy;
        }
      }

      // Spring attraction along edges toward target length
      for (const e of edges) {
        const a = nodes[e.sourceIdx], b = nodes[e.targetIdx];
        const dx = b.x - a.x, dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = alpha * SPRING_K * (dist - e.targetLength);
        const fx = force * dx / dist, fy = force * dy / dist;
        a.vx += fx; a.vy += fy;
        b.vx -= fx; b.vy -= fy;
      }

      // Center gravity
      const cx = width / 2, cy = height / 2;
      for (const n of nodes) {
        n.vx += alpha * 0.012 * (cx - n.x);
        n.vy += alpha * 0.012 * (cy - n.y);
      }

      // Integrate + dampen + clamp
      const pad = NODE_RADIUS + 8;
      for (const n of nodes) {
        n.vx *= DAMPING; n.vy *= DAMPING;
        n.x = Math.max(pad, Math.min(width - pad, n.x + n.vx));
        n.y = Math.max(pad, Math.min(height - pad, n.y + n.vy));
      }
    }

    run(steps, alpha = 1.0) {
      for (let i = 0; i < steps; i++) this.tick(alpha);
    }
  }

  // ─── card styles ─────────────────────────────────────────────────────────────

  const cardStyles = css`
    :host { user-select: none; }
    ha-card { overflow: hidden; }

    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 16px 16px 10px;
      gap: 8px;
    }

    .card-title {
      font-size: 15px;
      font-weight: 600;
      color: var(--primary-text-color);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .group-badge {
      font-size: 0.72rem;
      font-weight: 600;
      padding: 3px 10px;
      border-radius: 12px;
      white-space: nowrap;
      flex-shrink: 0;
    }
    .group-badge.any-prox {
      background: #4caf5022;
      color: #4caf50;
      border: 1px solid #4caf5055;
    }
    .group-badge.no-prox {
      background: #9e9e9e18;
      color: #9e9e9e;
      border: 1px solid #9e9e9e44;
    }

    .graph-wrap {
      position: relative;
      width: 100%;
    }

    svg {
      display: block;
      width: 100%;
      overflow: visible;
    }

    .error-msg {
      padding: 16px;
      color: var(--error-color, #db4437);
      font-size: 14px;
    }

    @keyframes prox-pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.45; }
    }
    .prox-glow { animation: prox-pulse 2s ease-in-out infinite; }
  `;

  // ─── card ────────────────────────────────────────────────────────────────────

  class EntityDistanceGroupCard extends LitElement {
    static get properties() {
      return {
        hass: { attribute: false },
        _config: { state: true },
        _nodes: { state: true },
      };
    }

    static get styles() { return cardStyles; }

    static getConfigElement() {
      return document.createElement("entity-distance-group-card-editor");
    }

    static getStubConfig(hass) {
      const groups = _discoverGroups(hass);
      const entities = groups.length > 0 ? groups[0].entities : [];
      return { entities, title: "" };
    }

    constructor() {
      super();
      this._sim = null;
      this._nodes = [];
      this._edges = [];
      this._pairs = [];
      this._rafId = null;
      this._idleTimer = null;
      this._settled = false;
      this._ro = null;
    }

    setConfig(config) {
      if (!config.entities || !Array.isArray(config.entities) || config.entities.length < 2) {
        throw new Error("entity-distance-group-card: 'entities' list with at least 2 items is required.");
      }
      this._config = { title: "", ...config };
      this._settled = false;
      this._nodes = [];
    }

    getCardSize() {
      const n = this._config?.entities?.length || 2;
      return Math.ceil(Math.max(300, n * 90 + 60) / 70);
    }

    connectedCallback() {
      super.connectedCallback();
    }

    disconnectedCallback() {
      super.disconnectedCallback();
      this._stopIdle();
      if (this._ro) { this._ro.disconnect(); this._ro = null; }
    }

    // Build/update sim nodes and edges from current hass state
    _buildSim(width) {
      if (!this.hass || !this._config) return;
      const { entities } = this._config;
      const height = Math.max(300, entities.length * 90 + 60);
      const pairs = _getPairsForEntities(this.hass, entities);
      this._pairs = pairs;

      const distanceValues = pairs.map(p => {
        const s = this.hass.states[`sensor.${p.slug}_distance`];
        return s && s.state !== "unknown" && s.state !== "unavailable" ? parseFloat(s.state) : null;
      }).filter(v => v !== null && !isNaN(v));

      const maxDist = distanceValues.length ? Math.max(...distanceValues) : 10000;

      // Initialize nodes if needed (preserve positions if already settled)
      const existingById = new Map((this._nodes || []).map(n => [n.id, n]));
      const cx = width / 2, cy = height / 2;
      const r = Math.min(width, height) * 0.3;
      const nodes = entities.map((entityId, i) => {
        const existing = existingById.get(entityId);
        if (existing) return { ...existing };
        const angle = (2 * Math.PI * i) / entities.length - Math.PI / 2;
        return {
          id: entityId,
          x: cx + r * Math.cos(angle),
          y: cy + r * Math.sin(angle),
          vx: 0, vy: 0,
        };
      });

      const edges = pairs.map(p => {
        const sIdx = nodes.findIndex(n => n.id === p.entityA);
        const tIdx = nodes.findIndex(n => n.id === p.entityB);
        const distState = this.hass.states[`sensor.${p.slug}_distance`];
        const distM = distState && distState.state !== "unknown" && distState.state !== "unavailable"
          ? parseFloat(distState.state) : maxDist;
        const ratio = maxDist > 0 ? Math.min(distM / maxDist, 1) : 0.5;
        const targetLength = MIN_EDGE_PX + ratio * (MAX_EDGE_PX - MIN_EDGE_PX);
        return { sourceIdx: sIdx, targetIdx: tIdx, targetLength };
      });

      if (!this._sim) this._sim = new ForceGraph(width, height);
      this._sim.width = width;
      this._sim.height = height;
      this._sim.setNodes(nodes);
      this._sim.setEdges(edges);

      if (!this._settled) {
        this._sim.run(SETTLE_STEPS);
        this._settled = true;
      }

      this._nodes = [...this._sim.nodes];
    }

    _startIdle() {
      this._stopIdle();
      const step = () => {
        if (!this._sim || !this.isConnected) return;
        this._sim.tick(IDLE_ALPHA);
        this._nodes = [...this._sim.nodes];
        this._rafId = requestAnimationFrame(step);
      };
      this._rafId = requestAnimationFrame(step);
      this._idleTimer = setTimeout(() => this._stopIdle(), IDLE_TIMEOUT_MS);
    }

    _stopIdle() {
      if (this._rafId) { cancelAnimationFrame(this._rafId); this._rafId = null; }
      if (this._idleTimer) { clearTimeout(this._idleTimer); this._idleTimer = null; }
    }

    shouldUpdate(changed) {
      if (changed.has("_config") || changed.has("_nodes")) return true;
      if (!this.hass) return false;
      const old = changed.get("hass");
      if (!old) return true;
      const watchIds = this._watchIds();
      return watchIds.some(id => old.states[id] !== this.hass.states[id]);
    }

    _watchIds() {
      const ids = [];
      for (const p of (this._pairs || [])) {
        ids.push(
          `sensor.${p.slug}_distance`,
          `sensor.${p.slug}_direction`,
          `sensor.${p.slug}_proximity_zone`,
          `binary_sensor.${p.slug}_in_proximity`,
        );
        ids.push(p.entityA, p.entityB);
      }
      return ids;
    }

    _getWidth() {
      const rect = this.shadowRoot?.querySelector(".graph-wrap")?.getBoundingClientRect();
      return (rect?.width > 10 ? rect.width : null) || this.offsetWidth || 360;
    }

    firstUpdated() {
      const rebuild = () => {
        const w = this._getWidth();
        if (w > 10) {
          this._settled = false;
          this._buildSim(w);
          this._startIdle();
        }
      };
      // ResizeObserver catches layout-deferred width in sections grid
      this._ro = new ResizeObserver(() => {
        if (this._ro) { this._ro.disconnect(); this._ro = null; }
        rebuild();
      });
      const wrap = this.shadowRoot?.querySelector(".graph-wrap");
      if (wrap) this._ro.observe(wrap);
      rebuild();
    }

    updated(changed) {
      if (changed.has("hass") || changed.has("_config")) {
        const width = this._getWidth();
        this._buildSim(width);
        this._startIdle();
      }
    }

    _onLineClick(distEntityId) {
      this.dispatchEvent(new CustomEvent("hass-more-info", {
        detail: { entityId: distEntityId },
        bubbles: true,
        composed: true,
      }));
    }

    render() {
      if (!this._config || !this.hass) return html``;
      const { entities, title } = this._config;
      const height = Math.max(300, entities.length * 90 + 60);

      if (!entities || entities.length < 2) {
        return html`<ha-card><div class="error-msg">Configure at least 2 entities.</div></ha-card>`;
      }

      const width = this._getWidth();
      const nodes = this._nodes;
      const pairs = this._pairs;

      if (!nodes.length) {
        return html`<ha-card>
          <div class="card-header"><div class="card-title"><span>🗺</span><span>${entities.map(e => _personName(this.hass, e)).join(" · ")}</span></div></div>
          <div class="graph-wrap" style="height:${height}px"></div>
        </ha-card>`;
      }

      const proxCount = pairs.filter(p => {
        const s = this.hass.states[`binary_sensor.${p.slug}_in_proximity`];
        return s?.state === "on";
      }).length;
      const totalPairs = pairs.length;

      const cardTitle = title || entities.map(e => _personName(this.hass, e)).join(" · ");

      return html`
        <ha-card>
          <div class="card-header">
            <div class="card-title">
              <span>🗺</span>
              <span>${cardTitle}</span>
            </div>
            <span class="group-badge ${proxCount > 0 ? "any-prox" : "no-prox"}">
              ${proxCount} of ${totalPairs} pair${totalPairs !== 1 ? "s" : ""} in proximity
            </span>
          </div>

          <div class="graph-wrap">
            <svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">

              <!-- defs for clip paths and glow filter -->
              <defs>
                ${nodes.map(n => html`
                  <clipPath id="clip-${n.id.replace(/[^a-z0-9]/gi, "_")}">
                    <circle cx="${n.x}" cy="${n.y}" r="${NODE_RADIUS - 2}"></circle>
                  </clipPath>
                `)}
                <filter id="prox-glow" x="-50%" y="-50%" width="200%" height="200%">
                  <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
                  <feMerge>
                    <feMergeNode in="coloredBlur"/>
                    <feMergeNode in="SourceGraphic"/>
                  </feMerge>
                </filter>
              </defs>

              <!-- edges -->
              ${pairs.map(p => {
                const ni = nodes.findIndex(n => n.id === p.entityA);
                const nj = nodes.findIndex(n => n.id === p.entityB);
                if (ni < 0 || nj < 0) return nothing;
                const a = nodes[ni], b = nodes[nj];

                const distState = this.hass.states[`sensor.${p.slug}_distance`];
                const dirState = this.hass.states[`sensor.${p.slug}_direction`];
                const zoneState = this.hass.states[`sensor.${p.slug}_proximity_zone`];
                const proxState = this.hass.states[`binary_sensor.${p.slug}_in_proximity`];

                const distM = distState?.state !== "unknown" && distState?.state !== "unavailable"
                  ? parseFloat(distState?.state) : null;
                const dir = dirState?.state;
                const zone = zoneState?.state;
                const inProx = proxState?.state === "on";

                const color = _zoneColor(zone);
                const strokeW = inProx ? 3 : 1.5;
                const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;

                // Perpendicular offset for label
                const dx = b.x - a.x, dy = b.y - a.y;
                const len = Math.sqrt(dx * dx + dy * dy) || 1;
                const ox = -dy / len * 14, oy = dx / len * 14;

                const distLabel = _formatDistance(distM);
                const arrow = _dirArrow(dir);
                const zoneLabel = zone ? zone.replace(/_/g, " ") : "";
                const lineLabel = [distLabel, arrow, zoneLabel].filter(Boolean).join(" ");

                return html`
                  <g
                    style="cursor:pointer"
                    @click=${() => this._onLineClick(p.distEntityId)}
                  >
                    ${inProx ? html`
                      <line
                        x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"
                        stroke="${color}" stroke-width="8" stroke-opacity="0.18"
                        filter="url(#prox-glow)"
                        class="prox-glow"
                      ></line>
                    ` : nothing}
                    <line
                      x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"
                      stroke="${color}" stroke-width="${strokeW}" stroke-opacity="0.9"
                    ></line>
                    <!-- line label bg -->
                    <rect
                      x="${mx + ox - lineLabel.length * 3.2}"
                      y="${my + oy - 9}"
                      width="${lineLabel.length * 6.4}"
                      height="16"
                      rx="4"
                      fill="var(--card-background-color, #fff)"
                      fill-opacity="0.88"
                    ></rect>
                    <text
                      x="${mx + ox}" y="${my + oy + 4}"
                      text-anchor="middle"
                      font-size="10"
                      font-family="inherit"
                      fill="${color}"
                      font-weight="600"
                    >${lineLabel}</text>
                  </g>
                `;
              })}

              <!-- nodes -->
              ${nodes.map(n => {
                const pic = _entityPicture(this.hass, n.id);
                const name = _personName(this.hass, n.id);
                const stateLabel = _entityStateLabel(this.hass, n.id);
                const hue = _nameHue(name);
                const clipId = `clip-${n.id.replace(/[^a-z0-9]/gi, "_")}`;

                return html`
                  <g>
                    <!-- shadow ring -->
                    <circle
                      cx="${n.x}" cy="${n.y}" r="${NODE_RADIUS + 1}"
                      fill="none"
                      stroke="var(--divider-color, rgba(0,0,0,0.12))"
                      stroke-width="1.5"
                    ></circle>
                    <!-- avatar background -->
                    <circle
                      cx="${n.x}" cy="${n.y}" r="${NODE_RADIUS - 2}"
                      fill="hsl(${hue}, 45%, 42%)"
                    ></circle>
                    ${pic ? html`
                      <image
                        href="${pic.startsWith("/") ? pic : pic}"
                        x="${n.x - NODE_RADIUS + 2}" y="${n.y - NODE_RADIUS + 2}"
                        width="${(NODE_RADIUS - 2) * 2}" height="${(NODE_RADIUS - 2) * 2}"
                        clip-path="url(#${clipId})"
                        preserveAspectRatio="xMidYMid slice"
                      ></image>
                    ` : html`
                      <text
                        x="${n.x}" y="${n.y + 5}"
                        text-anchor="middle"
                        font-size="15"
                        font-weight="700"
                        font-family="inherit"
                        fill="#fff"
                        pointer-events="none"
                      >${_initials(name)}</text>
                    `}
                    <!-- name below -->
                    <text
                      x="${n.x}" y="${n.y + NODE_RADIUS + 14}"
                      text-anchor="middle"
                      font-size="11"
                      font-weight="600"
                      font-family="inherit"
                      fill="var(--primary-text-color)"
                    >${name}</text>
                    ${stateLabel ? html`
                      <text
                        x="${n.x}" y="${n.y + NODE_RADIUS + 26}"
                        text-anchor="middle"
                        font-size="9.5"
                        font-family="inherit"
                        fill="var(--secondary-text-color)"
                      >${stateLabel}</text>
                    ` : nothing}
                  </g>
                `;
              })}

            </svg>
          </div>
        </ha-card>
      `;
    }
  }

  customElements.define("entity-distance-group-card", EntityDistanceGroupCard);

  // ─── editor ──────────────────────────────────────────────────────────────────

  class EntityDistanceGroupCardEditor extends LitElement {
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
        select, input[type="text"], input[type="range"] {
          width: 100%;
          padding: 8px;
          border: 1px solid var(--divider-color, #ccc);
          border-radius: 4px;
          box-sizing: border-box;
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color, #212121);
          font-size: 0.9rem;
        }
        input[type="range"] { padding: 4px 0; }
        .hint { font-size: 0.75rem; color: var(--secondary-text-color); margin-top: 3px; }
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

    _input(key, e) { this._update(key, e.target.value || undefined); }
    _select(key, e) { this._update(key, e.target.value); }

    render() {
      if (!this._config) return html``;
      const groups = _discoverGroups(this.hass);
      const currentEntities = (this._config.entities || []).join(",");

      return html`
        <div class="editor">

          <div class="section-title">Group</div>
          <div class="row">
            <label>Entity group</label>
            ${groups.length === 0 ? html`
              <div class="hint">No groups detected — make sure the Entity Distance integration is loaded.</div>
            ` : html`
              <select @change=${e => {
                const idx = parseInt(e.target.value, 10);
                if (!isNaN(idx) && groups[idx]) this._update("entities", groups[idx].entities);
              }}>
                ${groups.map((g, i) => html`
                  <option value="${i}" ?selected=${g.entities.join(",") === currentEntities}>
                    ${g.label}
                  </option>
                `)}
              </select>
            `}
          </div>

          <div class="section-title">Display</div>
          <div class="row">
            <label>Title (optional)</label>
            <input type="text" .value=${this._config.title || ""}
              placeholder="Leave blank to use entity names"
              @input=${e => this._input("title", e)} />
          </div>

        </div>
      `;
    }
  }

  customElements.define("entity-distance-group-card-editor", EntityDistanceGroupCardEditor);

}); // end whenDefined
