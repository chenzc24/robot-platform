"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const {renderArmFaults, requestArmRecovery} = require("../../src/console/web_console/static/app.js");

test("unknown/unsupported capabilities disable recovery without hiding fault evidence", () => {
  const nodes = new Map();
  const one = key => { if (!nodes.has(key)) nodes.set(key, {}); return nodes.get(key); };
  const arm = {gateway:"online", task:"idle", fault_capabilities:null,
    fault_diagnostics:{service:{vendor_code:26, sample_time_ms:1234, raw_text:"<script>test</script>"}}};
  renderArmFaults(arm, one);
  assert.equal(one("#arm-clear-errors").disabled, true);
  assert.equal(one("#arm-recover-service").disabled, true);
  assert.equal(one("#arm-diagnostics").disabled, false);
  assert.match(one("#arm-fault-detail").textContent, /1234/);
  assert.equal(one("#arm-fault-detail").innerHTML, undefined);
  arm.fault_capabilities = {xyz_preflight:true, controller_query:false, controller_clear:false, service_recover:false};
  renderArmFaults(arm, one);
  assert.match(one("#arm-fault-capabilities").textContent, /UNSUPPORTED/);
  assert.equal(one("#arm-clear-errors").disabled, true);
});

test("capabilities do not override a running or disconnected state", () => {
  const nodes = {};
  const one = key => nodes[key] ||= {};
  const arm = {gateway:"online", task:"idle", fault_capabilities:{controller_query:true, controller_clear:true, service_recover:true}};
  renderArmFaults(arm, one);
  assert.equal(one("#arm-clear-errors").disabled, false);
  arm.task = "running"; renderArmFaults(arm, one);
  assert.equal(one("#arm-clear-errors").disabled, true);
  arm.task = "idle"; arm.recovery_result = "pending"; renderArmFaults(arm, one);
  assert.equal(one("#arm-clear-errors").disabled, true);
  arm.task = "idle"; arm.gateway = "offline"; renderArmFaults(arm, one);
  assert.equal(one("#arm-recover-service").disabled, true);
});

test("confirmation cancellation sends nothing; acceptance sends only the selected recovery", () => {
  const calls = [], messages = [];
  const request = (path, body) => calls.push({path, body});
  requestArmRecovery("clear_errors", message => { messages.push(message); return false; }, request);
  assert.equal(calls.length, 0);
  requestArmRecovery("recover_service", () => true, request);
  assert.deepEqual(calls, [{path:"/api/arm/recovery", body:{action:"recover_service", confirm:true}}]);
  assert.match(messages[0], /NOT enable or resume/);
});
