// Unit tests for the pure helpers in entity-distance-pair-card.js.
import { test } from "node:test";
import assert from "node:assert/strict";
import { captureCard } from "./_harness.mjs";

const { classes, helpers } = await captureCard("entity-distance-pair-card.js", [
  "_formatDistance",
  "_formatMinutes",
  "_formatTs",
  "_slug",
  "_zoneColor",
  "_dirIcon",
  "_dirColor",
]);
const {
  _formatDistance,
  _formatMinutes,
  _formatTs,
  _slug,
  _zoneColor,
  _dirIcon,
  _dirColor,
} = helpers;

test("card classes registered", () => {
  assert.ok(classes["entity-distance-pair-card"]);
  assert.ok(classes["entity-distance-pair-card-editor"]);
});

test("_formatDistance: threshold + null", () => {
  assert.equal(_formatDistance(999), "999 m");
  assert.equal(_formatDistance(1000), "1.0 km");
  assert.equal(_formatDistance(2500), "2.5 km");
  assert.equal(_formatDistance(null), "—");
});

test("_formatMinutes: boundaries and week carry", () => {
  assert.equal(_formatMinutes(0), "0 min");
  assert.equal(_formatMinutes(0.5), "< 1 min");
  assert.equal(_formatMinutes(59), "59 min");
  // Sub-minute values round both ways (not floor/ceil): 30.4 -> 30, 30.6 -> 31.
  assert.equal(_formatMinutes(30.4), "30 min");
  assert.equal(_formatMinutes(30.6), "31 min");
  assert.equal(_formatMinutes(60), "1h");
  assert.equal(_formatMinutes(90), "1h 30m");
  assert.equal(_formatMinutes(29822.78), "2w 6d");
  assert.equal(_formatMinutes(null), "—");
});

test("_formatTs: rounds, junk -> em dash", () => {
  const ago = (sec) => new Date(Date.now() - sec * 1000).toISOString();
  assert.equal(_formatTs(ago(59)), "just now");
  assert.equal(_formatTs(ago(60)), "1m ago"); // 60 s boundary
  assert.equal(_formatTs(ago(90)), "2m ago"); // 1.5 min ROUNDS to 2 (not floor -> 1)
  assert.equal(_formatTs(ago(6900)), "2h ago");
  assert.equal(_formatTs("unavailable"), "—");
});

test("_slug: prefix/suffix guard", () => {
  assert.equal(_slug("sensor.a_b_distance"), "a_b");
  assert.equal(_slug("sensor.a_b"), null);
  assert.equal(_slug("light.x"), null);
});

test("_zoneColor: all buckets + null fallback", () => {
  assert.equal(_zoneColor("very_near"), "#4caf50");
  assert.equal(_zoneColor("near"), "#8bc34a");
  assert.equal(_zoneColor("mid"), "#ff9800");
  assert.equal(_zoneColor("far"), "#ff5722");
  assert.equal(_zoneColor("very_far"), "#9e9e9e");
  assert.equal(_zoneColor("bogus"), null);
});

test("_dirIcon/_dirColor", () => {
  assert.equal(_dirIcon("approaching"), "↓");
  assert.equal(_dirIcon("stationary"), "•");
  assert.equal(_dirIcon("x"), "?");
  assert.match(_dirColor("approaching"), /edc-approach/);
});
