"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
let currentState = null;
let activeMotion = null;
let videoLoaded = false;
let pollBusy = false;

function toast(message, error = false) {
  const node = $("#toast");
  node.textContent = message;
  node.className = `toast show${error ? " error" : ""}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.className = "toast", 2200);
}

async function api(path, body = {}) {
  const response = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const result = await response.json();
  if (result.state) render(result.state);
  if (!result.ok) throw new Error(result.error || "request_failed");
  return result.state;
}

async function act(path, body, label) {
  try { await api(path, body); if (label) toast(label); return true; }
  catch (error) { toast(error.message, true); return false; }
}

function chip(id, online) {
  $(id).classList.toggle("online", Boolean(online));
}

function textState(node, value, online = false, fault = false) {
  node.textContent = String(value).toUpperCase();
  node.classList.toggle("online-text", online);
  node.classList.toggle("fault-text", fault);
}

function formatMeasurement(value) {
  if (!Number.isFinite(value)) return "—";
  const formatted = Number(value).toFixed(3).replace(/\.?0+$/, "");
  return formatted === "-0" ? "0" : formatted;
}

function renderMeasurement(root, labels, values) {
  $$("output", root).forEach((node, index) => {
    const value = Array.isArray(values) ? values[index] : null;
    node.value = formatMeasurement(value);
    node.textContent = `${labels[index]} ${formatMeasurement(value)}`;
    node.title = Number.isFinite(value) ? String(value) : "No measured value";
  });
}

function render(state) {
  currentState = state;
  const c = state.chassis, a = state.arm;
  chip("#video-chip", false);
  $("#video-chip").classList.toggle("configured", state.video.configured);
  chip("#chassis-chip", c.link === "online");
  chip("#arm-chip", a.gateway === "online");
  textState($("#video-state"), state.video.configured ? "route set" : "offline");
  textState($("#chassis-link"), c.link, c.link === "online");
  textState($("#chassis-drive"), c.motion_enabled ? "enabled" : "locked", c.motion_enabled);
  $("#chassis-health").textContent = c.health_age_ms == null ? "—" : `${c.health_age_ms} ms`;
  textState($("#arm-link"), a.gateway, a.gateway === "online");
  textState($("#arm-control"), a.controller, a.controller === "online", a.controller === "fault");
  textState($("#arm-task"), a.task, a.task === "running");
  $("#arm-mode").textContent = a.control_mode.toUpperCase();
  const measurement = a.measurement || {};
  const hasSample = Array.isArray(measurement.joint_deg) && Array.isArray(measurement.pose);
  const feedbackState = measurement.valid ? "LIVE" : (hasSample ? "STALE" : "UNAVAILABLE");
  textState($("#arm-feedback-state"), feedbackState, measurement.valid, hasSample && !measurement.valid);
  $("#arm-feedback-meta").textContent = hasSample
    ? `#${measurement.sample_id} · ${measurement.age_ms == null ? "—" : measurement.age_ms + " ms"} · U${measurement.pose_user}/T${measurement.pose_tool}`
    : String(measurement.error || "no sample").toUpperCase();
  renderMeasurement($("#current-joints"), ["J1","J2","J3","J4","J5","J6"], measurement.joint_deg);
  renderMeasurement($("#current-pose"), ["X","Y","Z","RX","RY","RZ"], measurement.pose);
  $("#requested-vector").textContent = `${c.velocity.vx_mm_s} / ${c.velocity.vy_mm_s} / ${c.velocity.omega_mrad_s}`;
  const online = c.link === "online";
  $("#chassis-connect").textContent = online ? "DISCONNECT" : "CONNECT";
  $("#chassis-enable").disabled = !online || c.motion_enabled || !c.motion_permitted;
  $("#chassis-disable").disabled = !online || !c.motion_enabled;
  $("#chassis-status").disabled = !online;
  const canMove = online && c.authenticated && c.motion_enabled && c.motion_permitted;
  $$('[data-motion], #apply-vector').forEach(node => node.disabled = !canMove);
  $("#arm-connect").textContent = a.gateway === "online" ? "DISCONNECT" : "CONNECT";
  $("#arm-status").disabled = a.gateway !== "online";
  const armMove = a.gateway === "online" && a.controller === "online" && a.motion_permitted && a.task !== "running";
  $$("#device-arm button[data-arm-command], #move-joints, #move-linear, #set-gripper").forEach(node => node.disabled = !armMove);
  $("#fault-count").textContent = state.faults.filter(f => !f.acknowledged).length;
  $("#event-count").textContent = state.events.length;
  renderFaults(state.faults);
  renderEvents(state.events);
  if (!videoLoaded && state.video.webrtc_url) {
    $("#video-frame").src = state.video.webrtc_url;
    $("#no-video").hidden = true;
    videoLoaded = true;
  }
}

function renderFaults(faults) {
  const root = $("#fault-list");
  root.replaceChildren();
  if (!faults.length) { const p = document.createElement("p"); p.className = "empty"; p.textContent = "No active faults"; root.append(p); return; }
  faults.forEach(fault => {
    const card = document.createElement("div"); card.className = "fault-card";
    const info = document.createElement("div");
    const title = document.createElement("strong"); title.textContent = fault.code;
    const detail = document.createElement("small"); detail.textContent = `${fault.source} · ${fault.summary}`;
    info.append(title, detail); card.append(info);
    if (!fault.acknowledged) { const button = document.createElement("button"); button.textContent = "ACK"; button.onclick = () => act("/api/faults/ack", {code: fault.code}); card.append(button); }
    root.append(card);
  });
}

function renderEvents(events) {
  const body = $("#event-list"); body.replaceChildren();
  events.forEach(event => {
    const row = document.createElement("tr");
    [event.time, event.target, event.command, event.lifecycle, event.result].forEach(value => { const cell = document.createElement("td"); cell.textContent = value; row.append(cell); });
    body.append(row);
  });
}

async function poll() {
  if (pollBusy) return;
  pollBusy = true;
  try { const response = await fetch("/api/state", {cache: "no-store"}); const result = await response.json(); if (result.ok) render(result.state); }
  catch (_) { chip("#chassis-chip", false); chip("#arm-chip", false); }
  finally { pollBusy = false; }
}

function speeds() { return {linear: Number($("#linear-speed").value), angular: Number($("#angular-speed").value)}; }
function vectorFor(name) {
  const {linear, angular} = speeds();
  return {forward: [linear,0,0], back: [-linear,0,0], left: [0,linear,0], right: [0,-linear,0], ccw: [0,0,angular], cw: [0,0,-angular]}[name];
}

async function startMotion(name) {
  if (activeMotion === name) return;
  const value = vectorFor(name); if (!value) return;
  activeMotion = name;
  try { await api("/api/chassis/motion/start", {vx_mm_s:value[0],vy_mm_s:value[1],omega_mrad_s:value[2]}); }
  catch (error) { activeMotion = null; toast(error.message, true); }
}

function stopMotion(beacon = false) {
  activeMotion = null;
  if (beacon) { fetch("/api/chassis/stop", {method:"POST",headers:{"Content-Type":"application/json"},body:"{}",keepalive:true}).catch(()=>{}); return; }
  act("/api/chassis/stop", {});
}

function armOptions() {
  return {speed_pct:Number($(".arm-speed").value),accel_pct:Number($(".arm-accel").value),user:Number($(".arm-user").value),tool:Number($(".arm-tool").value)};
}

function armCommand(command, payload) { return act("/api/arm/command", {command, payload:{...armOptions(), ...payload}}, command.replaceAll("_", " ")); }

function buildArmControls() {
  [["#current-joints",["J1","J2","J3","J4","J5","J6"]],["#current-pose",["X","Y","Z","RX","RY","RZ"]]].forEach(([selector, labels]) => {
    const root = $(selector);
    labels.forEach(label => { const value = document.createElement("output"); value.textContent = `${label} —`; root.append(value); });
  });
  const jointRoot = $("#joint-jogs");
  for (let i=0;i<6;i++) {
    const row=document.createElement("div"); row.className="jog-row"; row.innerHTML=`<span>J${i+1}</span><button data-arm-command>−</button><button data-arm-command>+</button>`;
    const buttons=$$("button",row); buttons[0].onclick=()=>jogJoint(i,-1); buttons[1].onclick=()=>jogJoint(i,1); jointRoot.append(row);
  }
  const xyzRoot=$("#xyz-jogs"); ["X","Y","Z"].forEach((axis,i)=>{const row=document.createElement("div");row.className="jog-row";row.innerHTML=`<span>${axis}</span><button data-arm-command>−</button><button data-arm-command>+</button>`;const buttons=$$("button",row);buttons[0].onclick=()=>jogXYZ(i,-1);buttons[1].onclick=()=>jogXYZ(i,1);xyzRoot.append(row);});
  const jointTargets=$("#joint-targets"), poseTargets=$("#pose-targets");
  for(let i=0;i<6;i++){const label=document.createElement("label");label.textContent=`J${i+1}`;label.innerHTML+=`<input class="joint-target" type="number" value="0" step="1">`;jointTargets.append(label);}
  ["X","Y","Z","RX","RY","RZ"].forEach(name=>{const label=document.createElement("label");label.textContent=name;label.innerHTML+=`<input class="pose-target" type="number" value="0" step="1">`;poseTargets.append(label);});
}
function jogJoint(index, sign){const values=[0,0,0,0,0,0];values[index]=sign*Number($("#joint-step").value);armCommand("jog_joint",{joint_delta_deg:values});}
function jogXYZ(index, sign){const values=[0,0,0];values[index]=sign*Number($("#xyz-step").value);armCommand("jog_xyz",{translation_mm:values});}

function bind() {
  buildArmControls();
  $$("[data-device-tab]").forEach(button => button.onclick=()=>{ if(button.dataset.deviceTab!=="chassis"&&activeMotion)stopMotion(); $$("[data-device-tab]").forEach(x=>x.classList.toggle("active",x===button)); $$(".device-view").forEach(x=>x.classList.toggle("active",x.id===`device-${button.dataset.deviceTab}`)); });
  $$("[data-arm-tab]").forEach(button => button.onclick=()=>{ $$("[data-arm-tab]").forEach(x=>x.classList.toggle("active",x===button)); $$(".arm-view").forEach(x=>x.classList.toggle("active",x.id===`arm-${button.dataset.armTab}`)); });
  $("#diagnostic-toggle").onclick=()=>$("#diagnostics").classList.toggle("open");
  $("#chassis-connect").onclick=()=>act(currentState?.chassis.link==="online"?"/api/chassis/disconnect":"/api/chassis/connect",{});
  $("#chassis-enable").onclick=()=>act("/api/chassis/enable",{},"chassis enabled");
  $("#chassis-disable").onclick=()=>act("/api/chassis/disable",{},"chassis disabled");
  $("#chassis-status").onclick=()=>act("/api/chassis/status",{});
  $("#arm-connect").onclick=()=>act(currentState?.arm.gateway==="online"?"/api/arm/disconnect":"/api/arm/connect",{});
  $("#arm-status").onclick=()=>act("/api/arm/status",{});
  $$('[data-motion]').forEach(button=>{button.onpointerdown=event=>{button.setPointerCapture(event.pointerId);startMotion(button.dataset.motion)};button.onpointerup=()=>stopMotion();button.onpointercancel=()=>stopMotion();button.onlostpointercapture=()=>{if(activeMotion===button.dataset.motion)stopMotion()};});
  $$('[data-stop]').forEach(button=>button.onclick=()=>stopMotion()); $("#global-stop").onclick=()=>stopMotion();
  $("#linear-speed").oninput=()=>$("#linear-output").textContent=`${$("#linear-speed").value} mm/s`;
  $("#angular-speed").oninput=()=>$("#angular-output").textContent=`${$("#angular-speed").value} mrad/s`;
  $("#apply-vector").onclick=()=>{activeMotion="exact";act("/api/chassis/motion/start",{vx_mm_s:Number($("#vx").value),vy_mm_s:Number($("#vy").value),omega_mrad_s:Number($("#omega").value)},"vector applied").then(ok=>{if(!ok)activeMotion=null})};
  $("#move-joints").onclick=()=>armCommand("move_joint",{joint_deg:$$(".joint-target").map(x=>Number(x.value))});
  $("#move-linear").onclick=()=>armCommand("move_linear",{pose:$$(".pose-target").map(x=>Number(x.value))});
  $("#set-gripper").onclick=()=>armCommand("gripper",{width_mm:Number($("#gripper-width").value)});
  $("#gripper-width").oninput=()=>$("#gripper-output").textContent=`${$("#gripper-width").value} mm`;
  $("#rotate-video").onclick=()=>{const rotated=$("#viewport").classList.toggle("rotated");$("#video-rotation").textContent=rotated?"ROT 90°":"ROT 0°"};
  $("#open-video").onclick=()=>{if(currentState?.video.webrtc_url)window.open(currentState.video.webrtc_url,"_blank","noopener")};
  window.addEventListener("blur",()=>stopMotion(true)); document.addEventListener("visibilitychange",()=>{if(document.hidden)stopMotion(true)});
  const keys={w:"forward",s:"back",a:"left",d:"right",q:"ccw",e:"cw"};
  window.addEventListener("keydown",event=>{if(event.repeat||event.target.matches("input")||!$("#device-chassis").classList.contains("active"))return;if(event.key==="Escape"){stopMotion();return}const name=keys[event.key.toLowerCase()];if(name){event.preventDefault();startMotion(name)}});
  window.addEventListener("keyup",event=>{if(keys[event.key.toLowerCase()]===activeMotion)stopMotion()});
}

bind(); poll(); setInterval(poll,500); setInterval(()=>$("#clock").textContent=new Date().toLocaleTimeString("en-GB"),1000);
