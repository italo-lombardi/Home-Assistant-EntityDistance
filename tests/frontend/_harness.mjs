// Shared test harness for the Entity Distance Lovelace cards.
//
// The cards (../../custom_components/entity_distance/frontend/*.js) are no-build
// LitElement modules served to the browser as `type: module`. At module load
// each one does:
//     customElements.whenDefined("ha-panel-lovelace").then(() => {
//       const LitElement = Object.getPrototypeOf(customElements.get("ha-panel-lovelace"));
//       const { html, nothing } = LitElement.prototype;
//       ...helpers + card classes defined inside this closure...
//     });
// In node none of those globals exist, so the card can't be imported bare, and
// the pure helpers (_formatMinutes, _formatDistance, _formatTs, _slug, ...) are
// trapped in the .then() closure — not exported, not on any prototype.
//
// Rather than edit the shipped file (it must stay byte-identical to what ships
// to browsers), we read the source TEXT, append a one-line capture of the
// helpers we want to test, and run the augmented text in a vm sandbox with the
// browser globals stubbed. The file on disk is never touched; only the string
// handed to vm is augmented. See captureCard() below.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { setImmediate as flush } from "node:timers/promises";
import vm from "node:vm";

const FRONTEND = fileURLToPath(
  new URL("../../custom_components/entity_distance/frontend/", import.meta.url)
);

export const NOTHING = "__NOTHING__";

// Flatten a tagged-template call to its rendered text. Nested html`` fragments
// (produced by the same stub) carry a __html string; splice those in so a
// rendered card's text is assertable.
function htmlTag(strings, ...values) {
  const flat = values.map((v) =>
    v != null && typeof v === "object" && "__html" in v ? v.__html : v
  );
  return { __html: String.raw({ raw: strings }, ...flat) };
}

// The card does `LitElement = Object.getPrototypeOf(customElements.get("ha-panel-lovelace"))`
// then reads `LitElement.prototype.{html,css,nothing}`. class Sub extends Base
// ⇒ Object.getPrototypeOf(Sub) === Base, so the Lit members must live on
// LitBase.prototype and the stub returned by get() must extend it.
function makeLitStubs() {
  class LitBase {}
  LitBase.prototype.html = htmlTag;
  LitBase.prototype.css = () => ({});
  // ponytail: `nothing` is a plain sentinel string, not Lit's real symbol.
  // These tests only exercise pure helpers off the captured closure, never a
  // live render(). If a future test renders a card and asserts an attribute is
  // OMITTED, note that this stub's html`` stringifies `nothing` into the output
  // (e.g. role="__NOTHING__") rather than dropping the attribute — assert the
  // helper return, or teach htmlTag to skip NOTHING, before relying on that.
  LitBase.prototype.nothing = NOTHING;
  LitBase.prototype.LitElement = LitBase;
  class HaPanelStub extends LitBase {}
  return HaPanelStub;
}

// Run a card's source in a sandbox and return { classes, helpers }.
// `helperNames` are the closure-local function names to capture; we append a
// `globalThis.__caps = { ... }` line just before the closing `});` of the
// whenDefined callback so they escape the closure. The disk file is unchanged.
export function captureCard(filename, helperNames = []) {
  let src = readFileSync(new URL(filename, `file://${FRONTEND}`), "utf8");

  const marker = "}); // end whenDefined";
  const occurrences = src.split(marker).length - 1;
  if (occurrences !== 1) {
    throw new Error(
      `${filename}: expected exactly one "${marker}", found ${occurrences}`
    );
  }
  const capture = helperNames.length
    ? `\n  globalThis.__caps = { ${helperNames.join(", ")} };\n`
    : "";
  src = src.replace(marker, `${capture}${marker}`);

  const defined = {};
  const HaPanelStub = makeLitStubs();
  const sandbox = {
    customElements: {
      // Return the Lit base only for ha-panel-lovelace. The card also calls
      // get(<its-own-name>) as a "already registered?" guard and bails if it's
      // truthy, so every other name must be undefined.
      get: (name) => (name === "ha-panel-lovelace" ? HaPanelStub : undefined),
      define: (name, cls) => {
        defined[name] = cls;
      },
      // whenDefined resolves immediately so the callback (and our capture) runs
      // as a microtask.
      whenDefined: () => Promise.resolve(),
    },
    document: { createElement: () => ({}) },
    window: { customCards: [] },
    console: { info: () => {} },
    Math,
    Date,
    Object,
    JSON,
    isNaN,
    parseFloat,
    parseInt,
    String,
    Number,
    Array,
    Promise,
    Set,
    Map,
    WeakMap,
    Symbol,
    RegExp,
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename });

  // whenDefined().then(cb) schedules cb (and our capture) as a microtask;
  // flush the queue so it has run before we read the captures back.
  return flush().then(() => ({
    classes: defined,
    helpers: sandbox.__caps || {},
  }));
}
