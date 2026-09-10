"use strict";

// Real production input bindings; no browser, socket or moving device is used.
const test = require("node:test");
const assert = require("node:assert/strict");
const {
  ChassisInput, bindChassisInput, mapVideoPoint, observationPositionText, visionPositionText,
} = require("../../src/console/web_console/static/app.js");
const flush = () => new Promise(resolve => setImmediate(resolve));

test("vision points preserve aspect ratio and letterbox offset", () => {
  const point = mapVideoPoint([640, 360], {width: 1280, height: 720}, {width: 800, height: 800});
  assert.deepEqual(point, {x: 400, y: 400});
  const corner = mapVideoPoint([0, 0], {width: 1280, height: 720}, {width: 800, height: 800});
  assert.deepEqual(corner, {x: 0, y: 175});
});

test("center-delta vision exposes rail, JSON offset, generation, and per-tag millimetres", () => {
  const summary = visionPositionText({
    localization_method: "center_delta", rail_position_mm: 75,
    tag_disagreement_mm: 1.25, max_cross_axis_error_mm: 2.5,
  }, {generation: 4, context: {json_axis_offset_mm: -75}});
  assert.equal(summary, "RAIL 75.0 mm · TAG Δ 1.3 mm · CROSS 2.5 mm · JSON OFFSET -75.0 mm · GEN 4");
  assert.equal(observationPositionText({
    board_center_mm: [250.096, 328.674], mapped_center_mm: [175.096, 328.674], rail_delta_mm: 75,
  }), "B(250.1,328.7) M(175.1,328.7) Δ75.0");
});

function deferred() {
  let resolve, reject;
  const promise = new Promise((ok, fail) => { resolve = ok; reject = fail; });
  return {promise, resolve, reject};
}

function fixture() {
  const calls = [], errors = [];
  let epoch = 0;
  const state = {chassis: {motion: {epoch: "e0"}}};
  const request = async (path, payload, options) => {
    calls.push({path, payload, options});
    if (!path.endsWith("keepalive")) state.chassis.motion.epoch = "e" + ++epoch;
    return structuredClone(state);
  };
  const input = new ChassisInput(request, () => state, error => errors.push(error));
  const nodes = new Map();
  const one = selector => {
    if (!nodes.has(selector)) nodes.set(selector, {
      disabled: false, value: "50", dataset: {}, setPointerCapture() {},
      classList: {contains: () => true},
    });
    return nodes.get(selector);
  };
  const buttons = ["forward", "back", "left", "right", "ccw", "cw"].map(name => {
    const node = one(`[data-motion="${name}"]`);
    node.dataset.motion = name;
    return node;
  });
  const windowEvents = {}, documentEvents = {};
  const root = {hidden: false, querySelector: one,
    querySelectorAll: selector => selector === "[data-motion]" ? buttons : [one("stop")],
    addEventListener: (name, handler) => documentEvents[name] = handler};
  const view = {addEventListener: (name, handler) => windowEvents[name] = handler};
  bindChassisInput(input, root, view);
  const event = (pointerId = 1) => ({pointerId, button: 0, buttons: 1});
  const key = name => ({key: name, repeat: false, target: {matches: () => false}, preventDefault() {}});
  return {input, calls, errors, state, one, buttons, root, windowEvents, documentEvents, event, key};
}

test("all six pointer directions stop on release and do not renew afterwards", async () => {
  const f = fixture();
  for (const button of f.buttons) {
    button.onpointerdown(f.event()); await flush();
    assert.equal(f.calls.at(-1).payload.input_mode, "momentary");
    await f.input.pulse();
    button.onpointerup(f.event()); await flush();
    const count = f.calls.length;
    await f.input.pulse();
    assert.equal(f.calls.length, count);
    assert.equal(f.calls.at(-1).path, "/api/chassis/stop");
    assert.equal(f.input.active, null);
  }
});

test("exact HOLD does not leak into direction input, including later clicks", async () => {
  const f = fixture(), button = f.buttons[0];
  f.one("#apply-vector").onclick(); await flush();
  assert.equal(f.input.active.mode, "hold");
  await f.input.pulse();
  button.onpointerdown(f.event()); await flush();
  assert.equal(f.calls.at(-2).path, "/api/chassis/stop");
  assert.equal(f.calls.at(-1).payload.input_mode, "momentary");
  button.onpointerup(f.event()); await flush();
  assert.equal(f.input.active, null);
  button.onpointerdown(f.event()); await flush();
  button.onpointerup(f.event()); await flush();
  assert.equal(f.input.active, null);
});

test("APPLY & HOLD can update an already held vector", async () => {
  const f = fixture();
  f.one("#apply-vector").onclick(); await flush();
  f.one("#vx").value = "75";
  f.one("#apply-vector").onclick(); await flush();
  assert.equal(f.calls.at(-1).payload.vx_mm_s, 75);
});

test("release, cancel, capture loss and missing mouse-up movement all clear input", async () => {
  const f = fixture(), button = f.buttons[0];
  for (const action of ["onpointerup", "onpointercancel", "onlostpointercapture", "onpointermove"]) {
    button.onpointerdown(f.event()); await flush();
    button[action]({...f.event(), buttons: 0}); await flush();
    assert.equal(f.input.active, null);
  }
});

test("release from an old pointer does not cancel the newer pointer", async () => {
  const f = fixture();
  f.buttons[0].onpointerdown(f.event(1)); await flush();
  f.buttons[1].onpointerdown(f.event(2)); await flush();
  f.buttons[0].onpointerup(f.event(1)); await flush();
  assert.equal(f.input.active.source, "pointer:2");
  f.buttons[1].onpointerup(f.event(2)); await flush();
  assert.equal(f.input.active, null);
});

test("all keyboard directions stop on matching release; repeated keydown is ignored", async () => {
  const f = fixture();
  for (const name of ["w", "a", "s", "d", "q", "e"]) {
    f.windowEvents.keydown(f.key(name)); await flush();
    const count = f.calls.length;
    f.windowEvents.keydown({...f.key(name), repeat: true}); await flush();
    assert.equal(f.calls.length, count);
    f.windowEvents.keyup(f.key(name)); await flush();
    assert.equal(f.input.active, null);
  }
});

test("page blur, hide, and pagehide send immediate keepalive STOP", async () => {
  const f = fixture();
  for (const action of [() => f.windowEvents.blur(), () => f.windowEvents.pagehide(),
                        () => { f.root.hidden = true; f.documentEvents.visibilitychange(); }]) {
    f.buttons[0].onpointerdown(f.event()); await flush();
    action(); await flush();
    assert.equal(f.input.active, null);
    assert.equal(f.calls.at(-1).options.keepalive, true);
  }
});

test("page lifecycle does not send STOP without active manual input", async () => {
  const f = fixture();
  f.windowEvents.blur();
  f.windowEvents.pagehide();
  f.root.hidden = true;
  f.documentEvents.visibilitychange();
  await flush();
  assert.equal(f.calls.length, 0);
});

test("late start reply after release cannot re-arm browser input", async () => {
  const f = fixture(), pending = deferred(), original = f.input.request;
  f.input.request = (path, body, options) => path.endsWith("/start") ? pending.promise : original(path, body, options);
  const start = f.input.begin("forward", [50,0,0], "momentary", "key:w"); await flush();
  await f.input.stop("key_release");
  pending.resolve({chassis: {motion: {epoch: "old"}}});
  await start;
  await f.input.pulse();
  assert.equal(f.input.active, null);
  assert.equal(f.calls.filter(call => call.path.endsWith("keepalive")).length, 0);
});

test("a failed old start does not clear newer direction input", async () => {
  const f = fixture(), pending = deferred(), original = f.input.request;
  let first = true;
  f.input.request = (path, body, options) => {
    if (path.endsWith("/start") && first) { first = false; return pending.promise; }
    return original(path, body, options);
  };
  const old = f.input.begin("forward", [50,0,0], "momentary", "key:w"); await flush();
  await f.input.begin("left", [0,50,0], "momentary", "key:a");
  pending.reject(new Error("old request failed")); await old;
  assert.equal(f.input.active.source, "key:a");
});

test("failed start or keepalive sends STOP, is not retried, and clears input", async () => {
  for (const suffix of ["/start", "/keepalive"]) {
    const f = fixture(), original = f.input.request;
    let failed = 0;
    f.input.request = (path, body, options) => {
      if (path.endsWith(suffix)) { failed++; return Promise.reject(new Error("fake failure")); }
      return original(path, body, options);
    };
    await f.input.begin("forward", [50,0,0], "momentary", "key:w");
    await f.input.pulse(); await flush();
    assert.equal(f.input.active, null);
    assert.equal(failed, 1);
    assert.equal(f.calls.at(-1).path, "/api/chassis/stop");
  }
});

test("keepalive requests do not accumulate behind a slow response", async () => {
  const f = fixture(), pending = deferred(), original = f.input.request;
  let count = 0;
  await f.input.begin("forward", [50,0,0], "momentary", "key:w");
  f.input.request = (path, body, options) => {
    if (path.endsWith("keepalive")) { count++; return pending.promise; }
    return original(path, body, options);
  };
  const first = f.input.pulse();
  await f.input.pulse(); await f.input.pulse();
  assert.equal(count, 1);
  pending.resolve(f.state); await first;
});

test("new press waits for every overlapping STOP response", async () => {
  const f = fixture(), first = deferred(), second = deferred(), original = f.input.request;
  let count = 0;
  f.input.request = (path, body, options) => {
    if (path.endsWith("/stop")) return ++count === 1 ? first.promise : second.promise;
    return original(path, body, options);
  };
  f.input.stop(); f.input.stop();
  const next = f.input.begin("forward", [50,0,0], "momentary", "key:w");
  second.resolve(f.state); await flush();
  assert.equal(f.calls.length, 0);
  first.resolve(f.state); await next;
  assert.equal(f.calls.length, 1);
});

test("disabled controls and non-primary pointer cannot start motion", async () => {
  const f = fixture(), button = f.buttons[0];
  button.onpointerdown({...f.event(), button: 2});
  button.disabled = true;
  button.onpointerdown(f.event());
  f.windowEvents.keydown(f.key("w")); await flush();
  assert.equal(f.calls.length, 0);
});
