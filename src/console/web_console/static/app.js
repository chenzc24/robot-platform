"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
let currentState = null;
let chassisInput = null;
let videoLoaded = false;
let pollBusy = false;
let drawingSelectionDirty = false;

function toast(message, error = false) {
  const node = $("#toast");
  node.textContent = message;
  node.className = `toast show${error ? " error" : ""}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.className = "toast", 2200);
}

async function api(path, body = {}, options = {}) {
  const response = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body), ...options});
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

function mapVideoPoint(point, frame, viewport) {
  if (!Array.isArray(point) || frame.width <= 0 || frame.height <= 0 || viewport.width <= 0 || viewport.height <= 0) return null;
  const scale = Math.min(viewport.width / frame.width, viewport.height / frame.height);
  return {
    x: (viewport.width - frame.width * scale) / 2 + point[0] * scale,
    y: (viewport.height - frame.height * scale) / 2 + point[1] * scale,
  };
}

function renderVision(vision) {
  const canvas = $("#vision-canvas");
  const summary = $("#vision-summary");
  const viewport = $("#viewport");
  const context = canvas.getContext("2d");
  const width = viewport.clientWidth, height = viewport.clientHeight;
  const ratio = window.devicePixelRatio || 1;
  if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
  }
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, width, height);
  summary.className = "vision-summary";
  if (!vision?.configured) {
    summary.firstElementChild.textContent = "APRILTAG OFF";
    summary.lastElementChild.textContent = "Observation only";
    $("#vision-foot").textContent = "WEBRTC / APRILTAG OFF";
    return;
  }
  const confidence = Number(vision.confidence || 0);
  const rmse = Number.isFinite(vision.reprojection_rmse_px) ? `${Number(vision.reprojection_rmse_px).toFixed(2)} px` : "—";
  const ids = Array.isArray(vision.used_ids) && vision.used_ids.length ? vision.used_ids.join(",") : "—";
  const state = String(vision.status || "starting").toUpperCase();
  summary.classList.add(vision.accepted ? "accepted" : (vision.status === "error" ? "error" : "rejected"));
  summary.firstElementChild.textContent = `APRILTAG ${state} · C ${confidence.toFixed(2)} · RMSE ${rmse}`;
  const translation = vision.tvec_board_origin_in_camera_mm;
  const readiness = vision.camera_calibration_ready && vision.board_layout_ready ? "" : " · UNVERIFIED DEFAULTS";
  summary.lastElementChild.textContent = Array.isArray(translation)
    ? `IDs ${ids} · board origin in camera [${translation.map(value => Number(value).toFixed(1)).join(", ")}] mm${readiness}`
    : `IDs ${ids} · ${String(vision.error || "waiting")}`;
  $("#vision-foot").textContent = `WEBRTC / TAGS ${vision.known_count || 0} / ${state}`;
  if (!vision.image_width || !vision.image_height || !Array.isArray(vision.observations)) return;
  const frame = {width: vision.image_width, height: vision.image_height};
  vision.observations.forEach(observation => {
    if (!Array.isArray(observation.corners_px) || observation.corners_px.length !== 4) return;
    const points = observation.corners_px.map(point => mapVideoPoint(point, frame, {width, height}));
    if (points.some(point => point == null)) return;
    const color = observation.known ? (vision.accepted ? "#37c990" : "#f0b654") : "#8b98aa";
    context.strokeStyle = color;
    context.fillStyle = color;
    context.lineWidth = 2;
    context.beginPath();
    context.moveTo(points[0].x, points[0].y);
    points.slice(1).forEach(point => context.lineTo(point.x, point.y));
    context.closePath();
    context.stroke();
    context.beginPath();
    context.arc(points[0].x, points[0].y, 4, 0, Math.PI * 2);
    context.fill();
    context.font = "bold 12px ui-monospace, Consolas, monospace";
    context.fillText(`ID ${observation.id}`, points[0].x + 6, points[0].y - 6);
  });
}

function syncSelect(node, values) {
  const selected = node.value;
  const signature = values.join("\n");
  if (node.dataset.options === signature) return;
  node.replaceChildren(...values.map(value => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value.replaceAll("_", " ").toUpperCase();
    return option;
  }));
  node.dataset.options = signature;
  if (values.includes(selected)) node.value = selected;
}

function renderDrawing(drawing, owner) {
  drawing = drawing || {};
  const state = String(drawing.state || "unconfigured");
  const active = state === "running" || state === "stopping";
  syncSelect($("#drawing-job"), drawing.available_jobs || []);
  syncSelect($("#drawing-mode"), drawing.available_modes || ["baseline", "localized_baseline", "advanced"]);
  if (!drawingSelectionDirty && drawing.job_id) $("#drawing-job").value = drawing.job_id;
  if (!drawingSelectionDirty && drawing.mode) $("#drawing-mode").value = drawing.mode;
  textState($("#drawing-state"), state, state === "completed", state === "failed");
  $("#drawing-mode-state").textContent = String(drawing.mode || "—").toUpperCase();
  $("#drawing-phase").textContent = String(drawing.phase || "—").toUpperCase();
  $("#drawing-counts").textContent = drawing.task_id
    ? `${drawing.groups} GROUPS · ${drawing.strokes} STROKES · ${drawing.points} POINTS`
    : "—";
  $("#drawing-task-id").textContent = drawing.task_id || "—";
  $("#drawing-hash").textContent = drawing.job_sha256 || "—";
  const readiness = drawing.readiness || {};
  $("#drawing-readiness").textContent = drawingSelectionDirty
    ? "SELECTION CHANGED · PREPARE REQUIRED"
    : Object.keys(readiness).length
    ? Object.entries(readiness).map(([name, ready]) => `${name}:${ready ? "READY" : "BLOCKED"}`).join(" · ")
    : "—";
  $("#drawing-last-event").textContent = drawing.last_event?.event || drawing.error || "—";
  $("#drawing-job").disabled = active || !drawing.configured;
  $("#drawing-mode").disabled = active || !drawing.configured;
  $("#drawing-prepare").disabled = active || !drawing.configured || !(drawing.available_jobs || []).length;
  $("#drawing-start").disabled = state !== "prepared" || drawingSelectionDirty || !Object.values(readiness).every(Boolean);
  $("#drawing-cancel").disabled = !["prepared", "running", "stopping"].includes(state);
  $$('[data-drawing-confirm]').forEach(node => node.disabled = state !== "prepared");
  document.body.classList.toggle("drawing-owned", owner === "drawing");
}

function render(state) {
  if (currentState && state.revision < currentState.revision) return;
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
  renderVision(state.vision);
  renderDrawing(state.drawing, state.control_owner);
  $("#requested-vector").textContent = c.motion
    ? `${c.velocity.vx_mm_s} / ${c.velocity.vy_mm_s} / ${c.velocity.omega_mrad_s} · ${c.motion.mode.toUpperCase()}`
    : "Restart backend to load updated controls";
  const online = c.link === "online";
  $("#chassis-connect").textContent = online ? "DISCONNECT" : "CONNECT";
  $("#chassis-enable").disabled = !online || c.motion_enabled || !c.motion_permitted;
  $("#chassis-disable").disabled = !online || !c.motion_enabled;
  $("#chassis-status").disabled = !online;
  const canMove = online && c.authenticated && c.motion_enabled && c.motion_permitted && Boolean(c.motion?.epoch);
  $$('[data-motion], #apply-vector').forEach(node => node.disabled = !canMove);
  $("#arm-connect").textContent = a.gateway === "online" ? "DISCONNECT" : "CONNECT";
  $("#arm-status").disabled = a.gateway !== "online";
  const armMove = a.gateway === "online" && a.controller === "online" && a.motion_permitted && a.task !== "running";
  $$("#device-arm button[data-arm-command], #move-joints, #move-linear, #set-gripper").forEach(node => node.disabled = !armMove);
  if (state.control_owner === "drawing") {
    $("#chassis-connect").disabled = true;
    $("#chassis-enable").disabled = true;
    $("#chassis-disable").disabled = true;
    $("#arm-connect").disabled = true;
    $$('[data-motion], #apply-vector').forEach(node => node.disabled = true);
    $$("#device-arm button[data-arm-command], #move-joints, #move-linear, #set-gripper").forEach(node => node.disabled = true);
  }
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

class ChassisInput {
  constructor(request, state, onError) {
    this.request = request;
    this.state = state;
    this.onError = onError;
    this.active = null;
    this.stopping = Promise.resolve(true);
  }

  async begin(name, values, mode, source) {
    if (mode === "momentary" && this.active?.source === source && this.active?.name === name) return;
    if (this.active) this.stop("input_replaced");
    const input = {name, source, mode, epoch: null, busy: false};
    this.active = input;
    // A new press waits for previous releases, not for previous motion replies.
    const stopped = await this.stopping;
    if (this.active !== input) return;
    if (!stopped) { this.active = null; return; }
    try {
      const epoch = this.state()?.chassis.motion?.epoch;
      if (!epoch) throw new Error("Restart backend to load updated controls");
      const result = await this.request("/api/chassis/motion/start", {
        vx_mm_s: values[0], vy_mm_s: values[1], omega_mrad_s: values[2],
        input_mode: mode, motion_epoch: epoch,
      });
      // A late reply cannot re-arm a released/replaced input.
      if (this.active === input) input.epoch = result.chassis.motion.epoch;
    } catch (error) {
      if (this.active === input) {
        this.onError(error.message);
        this.stop("input_failed");
      }
    }
  }

  stop(reason = "operator_stop", keepalive = false) {
    this.active = null;
    // Send immediately, even if the start HTTP request has not returned yet.
    const attempt = this.request("/api/chassis/stop", {reason}, {keepalive})
      .then(() => true, error => { this.onError(error.message); return false; });
    this.stopping = Promise.all([this.stopping, attempt]).then(([, ok]) => ok);
    return this.stopping;
  }

  release(source, reason) {
    if (this.active?.source === source) return this.stop(reason);
  }

  async pulse() {
    const input = this.active;
    if (!input?.epoch || input.busy) return;
    input.busy = true;
    try {
      await this.request("/api/chassis/motion/keepalive", {motion_epoch: input.epoch});
    } catch (error) {
      if (this.active === input) {
        this.onError(error.message);
        this.stop("input_failed");
      }
    } finally { input.busy = false; }
  }
}

function bindChassisInput(controller, root = document, view = window) {
  const one = selector => root.querySelector(selector);
  const all = selector => [...root.querySelectorAll(selector)];
  const start = (name, source) => {
    const linear = Number(one("#linear-speed").value), angular = Number(one("#angular-speed").value);
    const values = {forward:[linear,0,0],back:[-linear,0,0],left:[0,linear,0],right:[0,-linear,0],ccw:[0,0,angular],cw:[0,0,-angular]}[name];
    if (values) controller.begin(name, values, "momentary", source);
  };
  all("[data-motion]").forEach(button => {
    button.onpointerdown = event => {
      if (event.button !== 0 || button.disabled) return;
      button.setPointerCapture(event.pointerId);
      start(button.dataset.motion, `pointer:${event.pointerId}`);
    };
    button.onpointerup = event => controller.release(`pointer:${event.pointerId}`, "pointer_release");
    button.onpointercancel = event => controller.release(`pointer:${event.pointerId}`, "pointer_cancel");
    button.onlostpointercapture = event => controller.release(`pointer:${event.pointerId}`, "capture_lost");
    button.onpointermove = event => { if (event.buttons === 0) controller.release(`pointer:${event.pointerId}`, "pointer_release"); };
  });
  all("[data-stop]").forEach(button => button.onclick = () => controller.stop());
  one("#global-stop").onclick = () => controller.stop();
  one("#apply-vector").onclick = () => controller.begin("exact",
    ["#vx", "#vy", "#omega"].map(selector => Number(one(selector).value)), "hold", "exact");
  view.addEventListener("blur", () => { if (controller.active) controller.stop("page_blur", true); });
  view.addEventListener("pagehide", () => { if (controller.active) controller.stop("page_hidden", true); });
  root.addEventListener("visibilitychange", () => { if (root.hidden && controller.active) controller.stop("page_hidden", true); });
  const keys = {w:"forward",s:"back",a:"left",d:"right",q:"ccw",e:"cw"};
  view.addEventListener("keydown", event => {
    if (event.key === "Escape") { controller.stop(); return; }
    if (event.repeat || event.target.matches("input,textarea,select,[contenteditable=true]") || !one("#device-chassis").classList.contains("active")) return;
    const name = keys[event.key.toLowerCase()];
    if (name && !one(`[data-motion="${name}"]`).disabled) {
      event.preventDefault(); start(name, `key:${event.key.toLowerCase()}`);
    }
  });
  view.addEventListener("keyup", event => controller.release(`key:${event.key.toLowerCase()}`, "key_release"));
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
  $$("[data-device-tab]").forEach(button => button.onclick=()=>{ if(button.dataset.deviceTab!=="chassis"&&chassisInput.active)chassisInput.stop("tab_changed"); $$("[data-device-tab]").forEach(x=>x.classList.toggle("active",x===button)); $$(".device-view").forEach(x=>x.classList.toggle("active",x.id===`device-${button.dataset.deviceTab}`)); });
  $$("[data-arm-tab]").forEach(button => button.onclick=()=>{ $$("[data-arm-tab]").forEach(x=>x.classList.toggle("active",x===button)); $$(".arm-view").forEach(x=>x.classList.toggle("active",x.id===`arm-${button.dataset.armTab}`)); });
  $("#diagnostic-toggle").onclick=()=>$("#diagnostics").classList.toggle("open");
  $("#chassis-connect").onclick=async()=>{const online=currentState?.chassis.link==="online";if(online)await chassisInput.stop("disconnect");act(online?"/api/chassis/disconnect":"/api/chassis/connect",{});};
  $("#chassis-enable").onclick=()=>act("/api/chassis/enable",{},"chassis enabled");
  $("#chassis-disable").onclick=async()=>{await chassisInput.stop("disable");act("/api/chassis/disable",{},"chassis disabled");};
  $("#chassis-status").onclick=()=>act("/api/chassis/status",{});
  $("#arm-connect").onclick=()=>act(currentState?.arm.gateway==="online"?"/api/arm/disconnect":"/api/arm/connect",{});
  $("#arm-status").onclick=()=>act("/api/arm/status",{});
  bindChassisInput(chassisInput);
  $("#linear-speed").oninput=()=>$("#linear-output").textContent=`${$("#linear-speed").value} mm/s`;
  $("#angular-speed").oninput=()=>$("#angular-output").textContent=`${$("#angular-speed").value} mrad/s`;
  $("#move-joints").onclick=()=>armCommand("move_joint",{joint_deg:$$(".joint-target").map(x=>Number(x.value))});
  $("#move-linear").onclick=()=>armCommand("move_linear",{pose:$$(".pose-target").map(x=>Number(x.value))});
  $("#set-gripper").onclick=()=>armCommand("gripper",{width_mm:Number($("#gripper-width").value)});
  $("#drawing-prepare").onclick=async()=>{
    const requestedJob = $("#drawing-job").value;
    const requestedMode = $("#drawing-mode").value;
    drawingSelectionDirty = false;
    const ok = await act("/api/drawing/task", {
      action:"prepare", job_id:requestedJob, mode:requestedMode,
    }, "drawing task prepared");
    if (ok) {
      $$('[data-drawing-confirm]').forEach(node => node.checked = false);
    } else {
      drawingSelectionDirty = true;
      $("#drawing-job").value = requestedJob;
      $("#drawing-mode").value = requestedMode;
      if (currentState) renderDrawing(currentState.drawing, currentState.control_owner);
    }
  };
  [$("#drawing-job"), $("#drawing-mode")].forEach(node => node.onchange=()=>{
    drawingSelectionDirty = true;
    if (currentState) renderDrawing(currentState.drawing, currentState.control_owner);
  });
  $("#drawing-start").onclick=()=>act("/api/drawing/task", {
    action:"start",
    task_id:currentState?.drawing.task_id,
    job_sha256:currentState?.drawing.job_sha256,
    confirmations:Object.fromEntries($$('[data-drawing-confirm]').map(node => [node.dataset.drawingConfirm, node.checked])),
  }, "drawing task started");
  $("#drawing-cancel").onclick=()=>act("/api/drawing/task", {
    action:"cancel", task_id:currentState?.drawing.task_id,
  }, "drawing cancellation requested");
  $("#gripper-width").oninput=()=>$("#gripper-output").textContent=`${$("#gripper-width").value} mm`;
  $("#rotate-video").onclick=()=>{const rotated=$("#viewport").classList.toggle("rotated");$("#video-rotation").textContent=rotated?"ROT 90°":"ROT 0°";if(currentState)renderVision(currentState.vision)};
  $("#open-video").onclick=()=>{if(currentState?.video.webrtc_url)window.open(currentState.video.webrtc_url,"_blank","noopener")};
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {ChassisInput, bindChassisInput, mapVideoPoint};
} else {
  chassisInput = new ChassisInput(api, () => currentState, message => toast(message, true));
  bind(); poll(); window.addEventListener("resize",()=>{if(currentState)renderVision(currentState.vision)}); setInterval(poll,500); setInterval(()=>chassisInput.pulse(),200);
  setInterval(()=>$("#clock").textContent=new Date().toLocaleTimeString("en-GB"),1000);
}
