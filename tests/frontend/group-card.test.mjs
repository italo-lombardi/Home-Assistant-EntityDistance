// Unit tests for the pure helpers in entity-distance-group-card.js.
import { test } from "node:test";
import assert from "node:assert/strict";
import { captureCard } from "./_harness.mjs";

const { classes, helpers } = await captureCard("entity-distance-group-card.js", [
  "_formatDistance",
  "_nameHue",
  "_initials",
  "_zoneColor",
  "_dirArrow",
  "_encodeAttr",
]);
const {
  _formatDistance,
  _nameHue,
  _initials,
  _zoneColor,
  _dirArrow,
  _encodeAttr,
} = helpers;

test("card classes registered", () => {
  assert.ok(classes["entity-distance-group-card"]);
  assert.ok(classes["entity-distance-group-card-editor"]);
});

test("_formatDistance: threshold + null", () => {
  assert.equal(_formatDistance(999), "999 m");
  assert.equal(_formatDistance(1000), "1.0 km");
  assert.equal(_formatDistance(null), "—");
});

test("_nameHue: deterministic, in range", () => {
  const h = _nameHue("Kitchen");
  assert.equal(h, _nameHue("Kitchen"));
  assert.ok(h >= 0 && h < 360);
});

test("_initials: 1-2 upper-cased letters", () => {
  assert.equal(_initials("Alice Smith"), "AS");
  assert.equal(_initials("bob"), "BO");
  assert.equal(_initials(""), "?");
});

test("_zoneColor: map lookup with grey fallback", () => {
  assert.equal(_zoneColor("very_near"), "#4caf50");
  assert.equal(_zoneColor("near"), "#8bc34a");
  assert.equal(_zoneColor("mid"), "#ff9800");
  assert.equal(_zoneColor("far"), "#ff5722");
  assert.equal(_zoneColor("very_far"), "#9e9e9e");
  assert.equal(_zoneColor("unknown_bucket"), "#9e9e9e"); // grey fallback, not null here
});

test("_dirArrow: map lookup with empty fallback", () => {
  assert.equal(_dirArrow("approaching"), "↓");
  assert.equal(_dirArrow("diverging"), "↑");
  assert.equal(_dirArrow("stationary"), "•");
  assert.equal(_dirArrow("other"), "");
});

test("_encodeAttr: escapes HTML-significant chars (XSS guard)", () => {
  assert.equal(_encodeAttr(`a&b"c<d>e`), "a&amp;b&quot;c&lt;d&gt;e");
  assert.equal(_encodeAttr('"><script>'), "&quot;&gt;&lt;script&gt;");
  assert.equal(_encodeAttr(42), "42"); // coerces non-strings
});
