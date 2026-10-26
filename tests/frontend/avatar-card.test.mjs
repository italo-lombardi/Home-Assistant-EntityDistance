// Unit tests for the pure helpers in entity-distance-avatar-card.js.
// Run with: node --test "tests/frontend/*.test.mjs"
import { test } from "node:test";
import assert from "node:assert/strict";
import { captureCard } from "./_harness.mjs";

const { classes, helpers } = await captureCard("entity-distance-avatar-card.js", [
  "_formatDistance",
  "_formatMinutes",
  "_formatTs",
  "_formatDate",
  "_slug",
  "_initials",
  "_nameHue",
  "_zoneColor",
  "_dirIcon",
  "_dirColor",
]);
const {
  _formatDistance,
  _formatMinutes,
  _formatTs,
  _formatDate,
  _slug,
  _initials,
  _nameHue,
  _zoneColor,
  _dirIcon,
  _dirColor,
} = helpers;

test("card classes registered", () => {
  assert.ok(classes["entity-distance-avatar-card"], "card class captured");
  assert.ok(classes["entity-distance-avatar-card-editor"], "editor class captured");
});

test("_formatDistance: metres below 1 km, rounded", () => {
  assert.equal(_formatDistance(0), "0 m");
  assert.equal(_formatDistance(4.4), "4 m");
  assert.equal(_formatDistance(4.6), "5 m");
  assert.equal(_formatDistance(999), "999 m");
});

test("_formatDistance: km at/above the 1000 m threshold, 1 d.p.", () => {
  assert.equal(_formatDistance(1000), "1.0 km");
  assert.equal(_formatDistance(1500), "1.5 km");
  assert.equal(_formatDistance(12345), "12.3 km");
});

test("_formatDistance: null/undefined render as em dash", () => {
  assert.equal(_formatDistance(null), "—");
  assert.equal(_formatDistance(undefined), "—");
});

test("_formatMinutes: small-value branches", () => {
  assert.equal(_formatMinutes(null), "—");
  assert.equal(_formatMinutes(0), "0 min");
  assert.equal(_formatMinutes(0.5), "< 1 min");
  assert.equal(_formatMinutes(1), "1 min");
  assert.equal(_formatMinutes(59), "59 min");
  // Rounds both ways (not floor/ceil): 30.4 -> 30, 30.6 -> 31.
  assert.equal(_formatMinutes(30.4), "30 min");
  assert.equal(_formatMinutes(30.6), "31 min");
});

test("_formatMinutes: hours/days split at the 60-min boundary", () => {
  assert.equal(_formatMinutes(60), "1h");
  assert.equal(_formatMinutes(90), "1h 30m");
  assert.equal(_formatMinutes(1440), "1d");
  assert.equal(_formatMinutes(1500), "1d 1h");
});

test("_formatMinutes: weeks are exact, no re-rounding carry (regression)", () => {
  // 29822.78 min -> 2w 6d, never 2w 7d. Guards the float->seconds->split path.
  assert.equal(_formatMinutes(29822.78), "2w 6d");
  assert.equal(_formatMinutes(10080), "1w"); // exactly 7 days
  assert.equal(_formatMinutes(11520), "1w 1d"); // 8 days
});

test("_formatTs: relative time rounds (not floors) to match HA", () => {
  const ago = (sec) => new Date(Date.now() - sec * 1000).toISOString();
  assert.equal(_formatTs(ago(30)), "just now"); // < 60 s
  assert.equal(_formatTs(ago(59)), "just now"); // still under a minute
  assert.equal(_formatTs(ago(60)), "1m ago"); // 60 s boundary flips
  assert.equal(_formatTs(ago(90)), "2m ago"); // 1.5 min rounds to 2
  assert.equal(_formatTs(ago(6900)), "2h ago"); // 1h55m rounds to 2h
  assert.equal(_formatTs(ago(100000)), "1d ago");
});

test("_formatTs: junk input renders em dash", () => {
  assert.equal(_formatTs(null), "—");
  assert.equal(_formatTs("unknown"), "—");
  assert.equal(_formatTs("unavailable"), "—");
  assert.equal(_formatTs("not-a-date"), "—");
});

test("_formatDate: null for junk, non-null string for a valid date", () => {
  assert.equal(_formatDate(null), null);
  assert.equal(_formatDate("unknown"), null);
  assert.equal(_formatDate("unavailable"), null);
  assert.equal(_formatDate("not-a-date"), null);
  // Locale output varies by runtime; assert it produced a non-empty string
  // and included the year rather than pinning an exact format.
  const out = _formatDate("2026-03-15T12:00:00Z");
  assert.equal(typeof out, "string");
  assert.match(out, /2026/);
});

test("_slug: strips sensor. prefix and _distance suffix", () => {
  assert.equal(_slug("sensor.alice_bob_distance"), "alice_bob");
  assert.equal(_slug("sensor.x_distance"), "x");
});

test("_slug: rejects ids missing prefix or suffix", () => {
  assert.equal(_slug("light.kitchen"), null);
  assert.equal(_slug("sensor.alice_bob"), null);
  assert.equal(_slug("alice_bob_distance"), null);
});

test("_initials: 1-2 letters, upper-cased", () => {
  assert.equal(_initials("Alice Smith"), "AS");
  assert.equal(_initials("bob"), "BO");
  assert.equal(_initials("alice_bob"), "AB"); // underscore split
  assert.equal(_initials(""), "?");
  assert.equal(_initials(null), "?");
});

test("_nameHue: deterministic and in [0,360)", () => {
  const h = _nameHue("Alice");
  assert.equal(h, _nameHue("Alice"), "stable for same input");
  assert.ok(h >= 0 && h < 360);
  assert.notEqual(_nameHue("Alice"), _nameHue("Bob"));
});

test("_zoneColor: all buckets, null fallback", () => {
  assert.equal(_zoneColor("very_near"), "#4caf50");
  assert.equal(_zoneColor("near"), "#8bc34a");
  assert.equal(_zoneColor("mid"), "#ff9800");
  assert.equal(_zoneColor("far"), "#ff5722");
  assert.equal(_zoneColor("very_far"), "#9e9e9e");
  assert.equal(_zoneColor("nope"), null);
});

test("_dirIcon/_dirColor: direction glyphs and colours", () => {
  assert.equal(_dirIcon("approaching"), "↓");
  assert.equal(_dirIcon("diverging"), "↑");
  assert.equal(_dirIcon("stationary"), "•");
  assert.equal(_dirIcon("weird"), "?");
  assert.match(_dirColor("approaching"), /edpc-approach/);
  assert.match(_dirColor("diverging"), /edpc-diverge/);
  assert.match(_dirColor("stationary"), /secondary-text-color/);
});
