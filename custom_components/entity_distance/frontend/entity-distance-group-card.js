/**
 * Entity Distance Group Card
 * Lovelace custom card for the Entity Distance integration.
 * Force-directed graph: one circle per entity, lines between every pair.
 */

const GROUP_CARD_VERSION = "0.2.5";

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

  const ZONE_COLORS = {
    very_near: "#4caf50",
    near: "#8bc34a",
    mid: "#ff9800",
    far: "#ff5722",
    very_far: "#9e9e9e",
  };

  const DIR_ARROWS = {
    approaching: "↓",
    diverging: "↑",
    stationary: "•",
  };

  function _zoneColor(bucket) {
    return ZONE_COLORS[bucket] || "#9e9e9e";
  }

  function _dirArrow(dir) {
    return DIR_ARROWS[dir] || "";
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

  function _encodeAttr(s) {
    return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function _entityPicture(hass, entityId) {
    if (!entityId) return null;
    return hass.states[entityId]?.attributes?.entity_picture || null;
  }

  /**
   * Discover all pairs in hass.states that involve only entities from the given list.
   * Returns array of { slug, entityA, entityB, distEntityId }
   */
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

    // Build a set of all known pairs keyed as "a|b" (sorted)
    const pairSet = new Set();
    for (const s of pairSensors) {
      pairSet.add([s.attributes.entity_a, s.attributes.entity_b].sort().join("|"));
    }

    // Find all maximal cliques: groups where every pair has a distance sensor.
    function isCompleteGroup(entities) {
      for (let i = 0; i < entities.length; i++) {
        for (let j = i + 1; j < entities.length; j++) {
          if (!pairSet.has([entities[i], entities[j]].sort().join("|"))) return false;
        }
      }
      return true;
    }

    // Build adjacency
    const adj = new Map();
    for (const s of pairSensors) {
      const a = s.attributes.entity_a;
      const b = s.attributes.entity_b;
      if (!adj.has(a)) adj.set(a, new Set());
      if (!adj.has(b)) adj.set(b, new Set());
      adj.get(a).add(b);
      adj.get(b).add(a);
    }

    // Generate combinations of `size` elements from `arr` starting at `offset`
    function combinations(arr, size, offset = 0, current = []) {
      if (current.length === size) return [current.slice()];
      const result = [];
      for (let i = offset; i < arr.length; i++) {
        current.push(arr[i]);
        result.push(...combinations(arr, size, i + 1, current));
        current.pop();
      }
      return result;
    }

    const groupKeys = new Set();
    const groups = [];

    for (const start of adj.keys()) {
      const neighbors = [start, ...(adj.get(start) || [])];
      for (let size = neighbors.length; size >= 2; size--) {
        for (const combo of combinations(neighbors, size)) {
          const sorted = combo.sort();
          const key = sorted.join("|");
          if (groupKeys.has(key)) continue;
          if (isCompleteGroup(sorted)) {
            groupKeys.add(key);
            groups.push(sorted);
          }
        }
      }
    }

    // Remove subsets: if group A is a subset of group B, drop A
    const maximalGroups = groups.filter(g =>
      !groups.some(other =>
        other !== g && other.length > g.length && g.every(e => other.includes(e))
      )
    );

    return maximalGroups.map(entities => ({
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
      };
    }

    static get styles() { return cardStyles; }

    static getConfigElement() {
      return document.createElement("entity-distance-group-card-editor");
    }

    static getStubConfig(hass) {
      const groups = _discoverGroups(hass);
      const entities = groups.length > 0 ? groups[0].entities : [];
      return { entities, title: "", fixed_layout: true };
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
      this._nodeLabelSide = {};
    }

    setConfig(config) {
      if (!config.entities || !Array.isArray(config.entities) || config.entities.length < 2) {
        throw new Error("entity-distance-group-card: 'entities' list with at least 2 items is required.");
      }
      this._config = { title: "", fixed_layout: true, ...config };
      this._settled = false;
      this._nodes = [];
      this._nodeLabelSide = {};
    }

    getCardSize() {
      const n = this._config?.entities?.length || 2;
      return Math.ceil(Math.max(300, n * 90 + 60) / 70);
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
      const hiddenSet = new Set(this._config.hidden_entities || []);
      const visibleEntities = entities.filter(e => !hiddenSet.has(e));
      if (visibleEntities.length < 2) { this._nodes = []; this._pairs = []; return; }

      const height = Math.max(300, visibleEntities.length * 90 + 60);
      const pairs = _getPairsForEntities(this.hass, visibleEntities);
      this._pairs = pairs;

      const distanceValues = pairs.map(p => {
        const s = this.hass.states[`sensor.${p.slug}_distance`];
        return s && s.state !== "unknown" && s.state !== "unavailable" ? parseFloat(s.state) : null;
      }).filter(v => v !== null && !isNaN(v));

      const maxDist = distanceValues.length ? Math.max(...distanceValues) : 10000;

      // Initialize nodes if needed (preserve positions if already settled)
      const existingById = new Map((this._nodes || []).map(n => [n.id, n]));
      const cx = width / 2, cy = height / 2;
      const rx = width * 0.28, ry = height * 0.28;
      const pad = NODE_RADIUS + 8;

      // Reset settled flag if entity list changed (triggers re-simulation)
      const prevIds = (this._nodes || []).map(n => n.id).sort().join(",");
      const nextIds = [...visibleEntities].sort().join(",");
      if (prevIds !== nextIds) this._settled = false;

      // Grid-based initial positions by count
      const GRID_POSITIONS = {
        2: [[0.5, 0.3], [0.5, 0.7]],
        3: [[0.28, 0.28], [0.72, 0.28], [0.5, 0.72]],
        4: [[0.28, 0.28], [0.72, 0.28], [0.28, 0.72], [0.72, 0.72]],
        5: [[0.28, 0.2], [0.72, 0.2], [0.5, 0.5], [0.28, 0.8], [0.72, 0.8]],
      };
      const grid = GRID_POSITIONS[visibleEntities.length];

      const nodes = visibleEntities.map((entityId, i) => {
        const existing = existingById.get(entityId);
        if (existing) {
          // Clamp preserved positions to current canvas bounds
          return { ...existing,
            x: Math.max(pad, Math.min(width - pad, existing.x)),
            y: Math.max(pad, Math.min(height - pad, existing.y)),
          };
        }
        const pos = grid ? grid[i] : null;
        return {
          id: entityId,
          x: pos ? pos[0] * width : cx + rx * Math.cos((2 * Math.PI * i) / visibleEntities.length - Math.PI / 2),
          y: pos ? pos[1] * height : cy + ry * Math.sin((2 * Math.PI * i) / visibleEntities.length - Math.PI / 2),
          vx: 0, vy: 0,
        };
      });

      const fixedLayout = this._config.fixed_layout === true;
      const FIXED_EDGE_PX = (MIN_EDGE_PX + MAX_EDGE_PX) / 2;

      const edges = pairs.map(p => {
        const sIdx = nodes.findIndex(n => n.id === p.entityA);
        const tIdx = nodes.findIndex(n => n.id === p.entityB);
        let targetLength;
        if (fixedLayout) {
          targetLength = FIXED_EDGE_PX;
        } else {
          const distState = this.hass.states[`sensor.${p.slug}_distance`];
          const distM = distState && distState.state !== "unknown" && distState.state !== "unavailable"
            ? parseFloat(distState.state) : maxDist;
          const ratio = maxDist > 0 ? Math.min(distM / maxDist, 1) : 0.5;
          targetLength = MIN_EDGE_PX + ratio * (MAX_EDGE_PX - MIN_EDGE_PX);
        }
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
      // Fixed layout: grid positions are already optimal, no animation needed
      if (this._config?.fixed_layout === true) return;
      const step = () => {
        if (!this._sim || !this.isConnected) return;
        this._sim.tick(IDLE_ALPHA);
        this._nodes = [...this._sim.nodes];
        this._renderSVG();
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
      return (this._pairs || []).flatMap(p => [
        `sensor.${p.slug}_distance`,
        `sensor.${p.slug}_direction`,
        `sensor.${p.slug}_proximity_zone`,
        `binary_sensor.${p.slug}_in_proximity`,
        p.entityA,
        p.entityB,
      ]);
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
          this._renderSVG();
          this._startIdle();
        }
      };
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
      this._renderSVG();
    }

    _nodeLabel(n, above, safeName, safeState, showState) {
      const nameW = Math.max(safeName.length * 6.5 + 8, 48);
      const stateW = (showState && safeState) ? Math.max(safeState.length * 5.5 + 8, 40) : 0;
      const nameY = above ? n.y - NODE_RADIUS - 5 : n.y + NODE_RADIUS + 13;
      const stateY = above ? nameY - 13 : nameY + 13;
      return `
        <rect x="${n.x - nameW / 2}" y="${nameY - 11}" width="${nameW}" height="14" rx="3" fill="var(--card-background-color,#fff)" fill-opacity="0.82"/>
        <text x="${n.x}" y="${nameY}" text-anchor="middle" font-size="11" font-weight="600" font-family="inherit" fill="var(--primary-text-color)" pointer-events="none">${safeName}</text>
        ${safeState && showState ? `
        <rect x="${n.x - stateW / 2}" y="${stateY - 10}" width="${stateW}" height="13" rx="3" fill="var(--card-background-color,#fff)" fill-opacity="0.82"/>
        <text x="${n.x}" y="${stateY}" text-anchor="middle" font-size="9.5" font-family="inherit" fill="var(--secondary-text-color)" pointer-events="none">${safeState}</text>` : ""}`;
    }

    _renderSVG() {
      const wrap = this.shadowRoot?.querySelector(".graph-wrap");
      if (!wrap || !this._nodes.length || !this.hass || !this._config) return;
      const hiddenSet = new Set(this._config.hidden_entities || []);
      const width = wrap.getBoundingClientRect().width || 360;
      const nodes = this._nodes.filter(n => !hiddenSet.has(n.id));
      const pairs = this._pairs.filter(p => !hiddenSet.has(p.entityA) && !hiddenSet.has(p.entityB));

      if (!nodes.length) {
        wrap.innerHTML = "";
        wrap.style.height = "0";
        return;
      }

      // Compute actual bounding box — labels can appear above OR below circles
      const PAD_H = NODE_RADIUS + 52; // top nodes have name+state above circle
      const PAD_X = NODE_RADIUS + 32;
      const minX = Math.min(...nodes.map(n => n.x)) - PAD_X;
      const maxX = Math.max(...nodes.map(n => n.x)) + PAD_X;
      const minY = Math.min(...nodes.map(n => n.y)) - PAD_H;
      const maxY = Math.max(...nodes.map(n => n.y)) + PAD_H;
      const vbW = maxX - minX;
      const vbH = Math.max(maxY - minY, 200);
      // Scale viewBox to fit card width, compute display height
      const scale = width / vbW;
      const height = Math.max(200, Math.round(vbH * scale));

      const pairSettings = this._config.pair_settings || {};
      const graphCentroidX = nodes.reduce((s, n) => s + n.x, 0) / (nodes.length || 1);
      const graphCentroidY = nodes.reduce((s, n) => s + n.y, 0) / (nodes.length || 1);

      const edgesHTML = pairs.map(p => {
        const ni = nodes.findIndex(n => n.id === p.entityA);
        const nj = nodes.findIndex(n => n.id === p.entityB);
        if (ni < 0 || nj < 0) return "";
        const a = nodes[ni], b = nodes[nj];
        const distState = this.hass.states[`sensor.${p.slug}_distance`];
        const dirState = this.hass.states[`sensor.${p.slug}_direction`];
        const zoneState = this.hass.states[`sensor.${p.slug}_proximity_zone`];
        const proxState = this.hass.states[`binary_sensor.${p.slug}_in_proximity`];
        const distM = distState?.state !== "unknown" && distState?.state !== "unavailable" ? parseFloat(distState?.state) : null;
        const zone = zoneState?.state;
        const inProx = proxState?.state === "on";
        const color = _zoneColor(zone);
        const strokeW = inProx ? 3 : 1.5;
        const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
        const dx = b.x - a.x, dy = b.y - a.y;
        const len = Math.sqrt(dx * dx + dy * dy) || 1;
        let ox = -dy / len * 22, oy = dx / len * 22;
        // Flip offset to always face away from graph center (outer side of line)
        // Epsilon guard: skip flip when edge midpoint is very close to centroid (avoids erratic behavior)
        const towardDot = (graphCentroidX - mx) * ox + (graphCentroidY - my) * oy;
        if (towardDot > 1) { ox = -ox; oy = -oy; }
        const pairKey = [p.entityA, p.entityB].sort().join(",");
        const ps = pairSettings[pairKey] || {};
        const showDistance = ps.show_distance !== false;
        const showZone = ps.show_zone !== false;
        const distLabel = showDistance && distM !== null ? _formatDistance(distM) : "";
        const arrow = (showDistance || showZone) ? _dirArrow(dirState?.state) : "";
        const zoneLabel = showZone && zone ? zone.replace(/_/g, " ") : "";
        const lineLabel = [distLabel, arrow, zoneLabel].filter(Boolean).join(" ");
        const lx = mx + ox, ly = my + oy;
        const labelW = Math.max(lineLabel.length * 6.4, 64);
        const labelHTML = lineLabel ? `
            <rect x="${lx - labelW / 2}" y="${ly - 9}" width="${labelW}" height="16" rx="4" fill="var(--card-background-color,#fff)" fill-opacity="0.88"/>
            <text x="${lx}" y="${ly + 4}" text-anchor="middle" font-size="10" font-family="inherit" font-weight="600" fill="${color}">${lineLabel}</text>` : "";
        const eid = p.distEntityId.replace(/"/g, "");
        return `
          <g style="cursor:pointer" data-entity="${eid}">
            ${inProx ? `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="${color}" stroke-width="8" stroke-opacity="0.18" filter="url(#prox-glow)" class="prox-glow"/>` : ""}
            <line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="${color}" stroke-width="${strokeW}" stroke-opacity="0.9"/>
            ${labelHTML}
          </g>`;
      }).join("");

      // Centroid Y to decide whether label goes above or below circle (more stable than min/max midpoint)
      const midY = graphCentroidY;
      const midYBand = 20; // deadband: nodes within ±20px of midY keep their last side
      const nodeSide = this._nodeLabelSide;
      const nodeSettings = this._config.node_settings || {};

      const nodesHTML = nodes.map(n => {
        const pic = _entityPicture(this.hass, n.id);
        const name = _personName(this.hass, n.id);
        const stateLabel = _entityStateLabel(this.hass, n.id);
        const hue = _nameHue(name);
        const clipId = `clip-${n.id.replace(/[^a-z0-9]/gi, "_")}`;
        const initials = _initials(name).replace(/&/g, "&amp;").replace(/</g, "&lt;");
        const safeName = name.replace(/&/g, "&amp;").replace(/</g, "&lt;");
        const safeState = (stateLabel || "").replace(/&/g, "&amp;").replace(/</g, "&lt;");

        const ns = nodeSettings[n.id] || {};
        const showName  = ns.show_name  !== false;
        const showState = (ns.show_state !== false) && (this._config.show_state !== false);
        const pos = ns.label_position || "auto"; // "above" | "below" | "auto"

        let above;
        if (pos === "above") {
          above = true;
        } else if (pos === "below") {
          above = false;
        } else {
          // auto: centroid + deadband
          if (Math.abs(n.y - midY) > midYBand) nodeSide[n.id] = n.y < midY;
          above = nodeSide[n.id] ?? true;
        }

        return `
          <g>
            <circle cx="${n.x}" cy="${n.y}" r="${NODE_RADIUS + 1}" fill="none" stroke="var(--divider-color,rgba(0,0,0,0.12))" stroke-width="1.5"/>
            <circle cx="${n.x}" cy="${n.y}" r="${NODE_RADIUS - 2}" fill="hsl(${hue},45%,42%)"/>
            ${pic
              ? `<clipPath id="${clipId}"><circle cx="${n.x}" cy="${n.y}" r="${NODE_RADIUS - 2}"/></clipPath>
                 <image href="${_encodeAttr(pic)}" x="${n.x - NODE_RADIUS + 2}" y="${n.y - NODE_RADIUS + 2}" width="${(NODE_RADIUS - 2) * 2}" height="${(NODE_RADIUS - 2) * 2}" clip-path="url(#${clipId})" preserveAspectRatio="xMidYMid slice"/>`
              : `<text x="${n.x}" y="${n.y + 5}" text-anchor="middle" font-size="15" font-weight="700" font-family="inherit" fill="#fff" pointer-events="none">${initials}</text>`}
            ${showName ? this._nodeLabel(n, above, safeName, safeState, showState) : ""}
          </g>`;
      }).join("");

      const svgStr = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="${minX} ${minY} ${vbW} ${vbH}" style="display:block;width:100%;overflow:visible;touch-action:manipulation">
        <defs>
          <filter id="prox-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
            <feMerge><feMergeNode in="coloredBlur"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
        </defs>
        ${edgesHTML}
        ${nodesHTML}
      </svg>`;

      wrap.style.height = `${height}px`;
      wrap.innerHTML = svgStr;

      // Re-attach click listeners (innerHTML wipes them)
      // Re-attach click listeners (innerHTML wipes them)
      wrap.querySelectorAll("g[data-entity]").forEach(g => {
        g.addEventListener("click", () => this._onLineClick(g.dataset.entity));
      });
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

      if (!entities || entities.length < 2) {
        return html`<ha-card><div class="error-msg">Configure at least 2 entities.</div></ha-card>`;
      }

      const hiddenSet = new Set(this._config.hidden_entities || []);
      const livePairs = _getPairsForEntities(this.hass, entities)
        .filter(p => !hiddenSet.has(p.entityA) && !hiddenSet.has(p.entityB));
      const proxCount = livePairs.filter(p => {
        const s = this.hass.states[`binary_sensor.${p.slug}_in_proximity`];
        return s?.state === "on";
      }).length;
      const totalPairs = livePairs.length;
      const cardTitle = title || entities.map(e => _personName(this.hass, e)).join(" · ");
      // _renderSVG sets actual height after sim; initial height prevents layout jump
      const initHeight = Math.max(260, (entities?.length || 2) * 80);

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
          <div class="graph-wrap" style="height:${initHeight}px;overflow:hidden"></div>
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
        .hint { font-size: 0.75rem; color: var(--secondary-text-color); margin-top: 3px; }
        .entity-order { display: flex; flex-direction: column; gap: 4px; margin-top: 6px; }
        .entity-row {
          display: flex;
          align-items: center;
          gap: 6px;
          background: var(--secondary-background-color, #f5f5f5);
          border-radius: 4px;
          padding: 5px 8px;
          font-size: 0.85rem;
        }
        .entity-row .pos {
          font-size: 0.7rem;
          font-weight: 700;
          color: var(--secondary-text-color);
          width: 16px;
          flex-shrink: 0;
        }
        .entity-row .name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .entity-row button {
          background: none;
          border: none;
          cursor: pointer;
          color: var(--secondary-text-color);
          padding: 2px 4px;
          font-size: 14px;
          line-height: 1;
          border-radius: 3px;
        }
        .entity-row button:hover { background: var(--divider-color, #e0e0e0); }
        .entity-row button:disabled { opacity: 0.3; cursor: default; }
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

    _updatePair(pairKey, subKey, value) {
      const pairSettings = { ...(this._config.pair_settings || {}) };
      pairSettings[pairKey] = { ...(pairSettings[pairKey] || {}), [subKey]: value };
      this._update("pair_settings", pairSettings);
    }

    _updateNode(entityId, subKey, value) {
      const nodeSettings = { ...(this._config.node_settings || {}) };
      nodeSettings[entityId] = { ...(nodeSettings[entityId] || {}), [subKey]: value };
      this._update("node_settings", nodeSettings);
    }

    _input(key, e) { this._update(key, e.target.value || undefined); }

    _moveEntity(idx, dir) {
      const entities = [...(this._config.entities || [])];
      const target = idx + dir;
      if (target < 0 || target >= entities.length) return;
      [entities[idx], entities[target]] = [entities[target], entities[idx]];
      this._update("entities", entities);
    }

    _toggleHidden(eid) {
      const hidden = [...(this._config.hidden_entities || [])];
      const i = hidden.indexOf(eid);
      if (i >= 0) hidden.splice(i, 1); else hidden.push(eid);
      this._update("hidden_entities", hidden.length ? hidden : undefined);
    }

    _renderNodeSettings(currentEntities) {
      if (!currentEntities.length) return nothing;
      const nodeSettings = this._config.node_settings || {};
      return html`
        <div class="section-title">Node Labels</div>
        ${currentEntities.map(eid => {
          const s = this.hass?.states[eid];
          const name = s?.attributes?.friendly_name || eid.replace(/^[^.]+\./, "").replace(/_/g, " ");
          const ns = nodeSettings[eid] || {};
          return html`
            <div style="margin-bottom:10px">
              <div style="font-size:0.82rem;font-weight:600;color:var(--primary-text-color);margin-bottom:4px">${name}</div>
              <div style="display:flex;flex-direction:column;gap:4px;padding-left:8px">
                <div style="display:flex;align-items:center;gap:8px">
                  <input type="checkbox" id="sname_${eid}"
                    .checked=${ns.show_name !== false}
                    @change=${e => this._updateNode(eid, "show_name", e.target.checked)} />
                  <label for="sname_${eid}" style="font-size:0.82rem;margin:0;cursor:pointer">Show name</label>
                </div>
                <div style="display:flex;align-items:center;gap:8px">
                  <input type="checkbox" id="sstate_${eid}"
                    .checked=${ns.show_state !== false}
                    @change=${e => this._updateNode(eid, "show_state", e.target.checked)} />
                  <label for="sstate_${eid}" style="font-size:0.82rem;margin:0;cursor:pointer">Show state</label>
                </div>
                <div style="display:flex;align-items:center;gap:8px">
                  <label for="lpos_${eid}" style="font-size:0.82rem;margin:0;min-width:90px">Label position</label>
                  <select id="lpos_${eid}" style="width:auto;padding:4px 6px;font-size:0.82rem"
                    @change=${e => this._updateNode(eid, "label_position", e.target.value)}>
                    <option value="auto"   ?selected=${!ns.label_position || ns.label_position === "auto"}>Auto</option>
                    <option value="above"  ?selected=${ns.label_position === "above"}>Above</option>
                    <option value="below"  ?selected=${ns.label_position === "below"}>Below</option>
                  </select>
                </div>
              </div>
            </div>
          `;
        })}
      `;
    }

    _renderPairSettings(currentEntities) {
      if (currentEntities.length < 2 || !this.hass) return nothing;
      const pairs = _getPairsForEntities(this.hass, currentEntities);
      if (!pairs.length) return nothing;
      const pairSettings = this._config.pair_settings || {};
      return html`
        <div class="section-title">Pairs</div>
        ${pairs.map(p => {
          const pairKey = [p.entityA, p.entityB].sort().join(",");
          const ps = pairSettings[pairKey] || {};
          const nameA = this.hass.states[p.entityA]?.attributes?.friendly_name || p.entityA.replace(/^[^.]+\./, "").replace(/_/g, " ");
          const nameB = this.hass.states[p.entityB]?.attributes?.friendly_name || p.entityB.replace(/^[^.]+\./, "").replace(/_/g, " ");
          return html`
            <div style="margin-bottom:10px">
              <div style="font-size:0.82rem;font-weight:600;color:var(--primary-text-color);margin-bottom:4px">${nameA} & ${nameB}</div>
              <div style="display:flex;flex-direction:column;gap:4px;padding-left:8px">
                <div style="display:flex;align-items:center;gap:8px">
                  <input type="checkbox" id="dist_${pairKey}"
                    .checked=${ps.show_distance !== false}
                    @change=${e => this._updatePair(pairKey, "show_distance", e.target.checked)} />
                  <label for="dist_${pairKey}" style="font-size:0.82rem;margin:0;cursor:pointer">Show distance</label>
                </div>
                <div style="display:flex;align-items:center;gap:8px">
                  <input type="checkbox" id="zone_${pairKey}"
                    .checked=${ps.show_zone !== false}
                    @change=${e => this._updatePair(pairKey, "show_zone", e.target.checked)} />
                  <label for="zone_${pairKey}" style="font-size:0.82rem;margin:0;cursor:pointer">Show proximity zone (very near, near…)</label>
                </div>
              </div>
            </div>
          `;
        })}
      `;
    }

    render() {
      if (!this._config) return html``;
      const groups = _discoverGroups(this.hass);
      const currentEntities = this._config.entities || [];
      const currentKey = currentEntities.join(",");

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
                  <option value="${i}" ?selected=${g.entities.join(",") === currentKey}>
                    ${g.label}
                  </option>
                `)}
              </select>
            `}
          </div>

          ${currentEntities.length >= 2 ? html`
            <div class="section-title">Entity Order</div>
            <div class="hint" style="margin-bottom:6px">Order determines grid position (slot 1 = top-left, etc.)</div>
            <div class="entity-order">
              ${currentEntities.map((eid, i) => {
                const s = this.hass?.states[eid];
                const name = s?.attributes?.friendly_name || eid.replace(/^[^.]+\./, "").replace(/_/g, " ");
                const hidden = (this._config.hidden_entities || []).includes(eid);
                return html`
                  <div class="entity-row" style="${hidden ? "opacity:0.45" : ""}">
                    <span class="pos">${i + 1}</span>
                    <span class="name">${name}</span>
                    <button title="${hidden ? "Show" : "Hide"}" @click=${() => this._toggleHidden(eid)} style="display:flex;align-items:center;justify-content:center;width:24px;height:24px">
                      <ha-icon icon="${hidden ? "mdi:eye-off" : "mdi:eye"}" style="--mdi-icon-size:16px"></ha-icon>
                    </button>
                    <button ?disabled=${i === 0} @click=${() => this._moveEntity(i, -1)}>↑</button>
                    <button ?disabled=${i === currentEntities.length - 1} @click=${() => this._moveEntity(i, 1)}>↓</button>
                  </div>
                `;
              })}
            </div>
          ` : nothing}

          <div class="section-title">Display</div>
          <div class="row">
            <label>Title (optional)</label>
            <input type="text" .value=${this._config.title || ""}
              placeholder="Leave blank to use entity names"
              @input=${e => this._input("title", e)} />
          </div>
          <div class="row" style="display:flex;align-items:center;gap:8px">
            <input type="checkbox" id="fixed_layout"
              .checked=${this._config.fixed_layout === true}
              @change=${e => this._update("fixed_layout", e.target.checked)} />
            <label for="fixed_layout" style="margin:0;cursor:pointer">Equal spacing (ignore real distances)</label>
          </div>
          <div class="row" style="display:flex;align-items:center;gap:8px">
            <input type="checkbox" id="show_state"
              .checked=${this._config.show_state !== false}
              @change=${e => this._update("show_state", e.target.checked)} />
            <label for="show_state" style="margin:0;cursor:pointer">Show entity state (Home, Away…)</label>
          </div>

          ${this._renderNodeSettings(currentEntities)}
          ${this._renderPairSettings(currentEntities)}
          </div>
      `;
    }
  }

  customElements.define("entity-distance-group-card-editor", EntityDistanceGroupCardEditor);

}); // end whenDefined
