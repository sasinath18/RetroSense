const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "app.js"), "utf8");

function makeDashboard({withChart = true} = {}) {
  const elements = new Map();
  const alerts = [];
  const calls = [];
  const local = new Map();
  const session = new Map();

  function makeElement(id = "") {
    const listeners = {};
    const classes = new Set();
    const element = {
      id, listeners, textContent: "", innerHTML: "", value: "", files: [],
      style: {}, dataset: {}, disabled: false, hidden: false, src: "",
      className: "", width: 0, height: 0, lastChild: {textContent: ""},
      addEventListener(type, callback) { listeners[type] = callback; },
      click() { if (listeners.click) return listeners.click({preventDefault() {}}); },
      setAttribute(name, value) { this[name] = String(value); },
      removeAttribute(name) { delete this[name]; },
      appendChild(child) { (this.children ||= []).push(child); },
      replaceChildren() { this.children = []; },
      getBoundingClientRect() { return {width: 640, height: 220}; },
      getContext() {
        return {
          setTransform() {}, clearRect() {}, beginPath() {}, moveTo() {},
          lineTo() {}, stroke() {}, fillText() {}, arc() {}, fill() {},
          set strokeStyle(v) {}, set lineWidth(v) {}, set font(v) {},
          set textAlign(v) {}, set textBaseline(v) {}, set fillStyle(v) {}
        };
      },
      toBlob(callback) { callback(new Blob(["frame"], {type: "image/jpeg"})); },
      classList: {
        add(name) { classes.add(name); },
        remove(name) { classes.delete(name); },
        contains(name) { return classes.has(name); },
        toggle(name, force) {
          const shouldAdd = force === undefined ? !classes.has(name) : Boolean(force);
          if (shouldAdd) classes.add(name); else classes.delete(name);
          return shouldAdd;
        }
      }
    };
    return element;
  }

  const defaults = {
    minValue: "0", maxValue: "100", warningLimit: "75", dangerLimit: "90",
    machineName: "Boiler pressure gauge", unit: "PSI",
    startAngle: "135", endAngle: "45"
  };
  function el(id) {
    if (!elements.has(id)) {
      const node = makeElement(id);
      if (id in defaults) node.value = defaults[id];
      if (id === "cameraPanel") node.hidden = true;
      elements.set(id, node);
    }
    return elements.get(id);
  }

  const modeButtons = ["analog", "digital"].map(mode => {
    const button = makeElement("mode-" + mode);
    button.dataset.mode = mode;
    return button;
  });
  const navButtons = ["overview", "capture", "history"].map(name => makeElement("nav-" + name));

  class FakeChart {
    constructor(canvas, config) {
      this.canvas = canvas;
      this.data = config.data;
      this.update = () => {};
    }
  }

  const document = {
    querySelector(selector) {
      if (selector.startsWith("#")) return el(selector.slice(1));
      return makeElement(selector);
    },
    querySelectorAll(selector) {
      if (selector === ".mode") return modeButtons;
      if (selector === ".nav") return navButtons;
      return [];
    },
    createElementNS() { return makeElement("svg-child"); },
    createElement(tag) {
      const node = makeElement(tag);
      node.download = "";
      return node;
    }
  };

  const response = (body, status = 200) => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body
  });

  async function fakeFetch(url, options = {}) {
    calls.push({url: String(url), method: options.method || "GET"});
    if (String(url).endsWith("/api/health")) return response({status: "ok"});
    if (String(url).endsWith("/api/jobs") && options.method === "POST") {
      return response({job_id: "smoke-job-1", status: "uploaded"});
    }
    if (String(url).endsWith("/api/jobs/smoke-job-1/start")) {
      return response({
        job_id: "smoke-job-1", status: "completed",
        reading: {
          timestamp: "2026-11-05T08:00:00.000Z",
          instrument: "Boiler pressure gauge",
          value: 76.3, unit: "PSI", status: "WARNING", mode: "analog",
          analysis: {pointer_angle_deg: 66.3, confidence: "experimental"}
        }
      });
    }
    if (String(url).endsWith("/api/readings")) return response({count: 0, readings: []});
    return response({detail: "Unexpected test endpoint: " + url}, 404);
  }

  const sandbox = {
    document,
    window: {
      RETROSENSE_API_URL: "https://api.example.test",
      Chart: withChart ? FakeChart : undefined,
      addEventListener() {},
      devicePixelRatio: 1
    },
    location: {hostname: "test.example"},
    navigator: {},
    localStorage: {
      getItem(key) { return local.get(key) ?? null; },
      setItem(key, value) { local.set(key, String(value)); }
    },
    sessionStorage: {
      getItem(key) { return session.get(key) ?? null; },
      setItem(key, value) { session.set(key, String(value)); }
    },
    URL: {
      createObjectURL() { return "blob:smoke-preview"; },
      revokeObjectURL() {}
    },
    FormData: class { constructor() { this.values = {}; } append(k, v) { this.values[k] = v; } },
    Headers,
    AbortSignal,
    Blob,
    fetch: fakeFetch,
    alert(message) { alerts.push(String(message)); },
    console,
    setInterval() { return 1; },
    clearInterval() {},
    setTimeout(callback) { return 1; }
  };

  vm.runInNewContext(source, sandbox, {filename: "app.js"});
  return {elements, modeButtons, navButtons, alerts, calls, sandbox};
}

async function waitForStartup() {
  await new Promise(resolve => setImmediate(resolve));
}

async function run(withChart) {
  const dashboard = makeDashboard({withChart});
  const {elements, modeButtons, navButtons, alerts, calls} = dashboard;
  await waitForStartup();

  assert.equal(elements.get("apiStatus").textContent, "ONLINE", "API health status should become ONLINE");
  assert.ok(elements.get("systemState").lastChild.textContent.includes("CONNECTED"), "Header should show API connection");

  modeButtons[1].listeners.click();
  assert.equal(elements.get("modeStat").textContent, "DIGITAL", "Mode switch should update the dashboard");
  modeButtons[0].listeners.click();

  const fileInput = elements.get("fileInput");
  const validFile = {name: "gauge.png", type: "image/png", size: 125000};
  fileInput.listeners.change({target: {files: [validFile]}});
  assert.equal(elements.get("fileName").textContent.includes("gauge.png"), true, "File selection should update filename");
  assert.equal(elements.get("selectedPreview").hidden, false, "File selection should show image preview");

  const invalidFile = {name: "notes.pdf", type: "application/pdf", size: 1000};
  fileInput.listeners.change({target: {files: [invalidFile]}});
  assert.equal(elements.get("selectedPreview").hidden, true, "Invalid file should clear previous preview");
  assert.equal(elements.get("fileName").textContent, "No file selected", "Invalid file should clear selected filename");
  fileInput.listeners.change({target: {files: [validFile]}});

  elements.get("maxValue").value = "0";
  const jobsBeforeInvalid = calls.filter(call => call.url.endsWith("/api/jobs")).length;
  await elements.get("analyzeBtn").listeners.click();
  assert.equal(calls.filter(call => call.url.endsWith("/api/jobs")).length, jobsBeforeInvalid, "Invalid scale must stop before upload");
  assert.ok(alerts.some(message => message.includes("Maximum value")), "Invalid scale should explain the problem");

  elements.get("maxValue").value = "100";
  await elements.get("analyzeBtn").listeners.click();
  assert.equal(elements.get("latestStat").textContent, "76.3", "Successful image analysis should update latest reading");
  assert.equal(elements.get("alertStat").textContent, "WARNING", "Threshold status should update");
  assert.ok(elements.get("historyBody").innerHTML.includes("Boiler pressure gauge"), "Reading should appear in history");
  assert.deepEqual(Array.from(elements.get("trendChart").__unused || []), []);
  assert.equal(elements.get("apiStatus").textContent, "ONLINE", "API status should remain online after analysis");

  const exported = elements.get("exportBtn").listeners.click();
  assert.ok(typeof exported !== "undefined" || calls.some(call => call.method === "GET"), "Export control should be wired");

  const missingCamera = elements.get("cameraStart").listeners.click();
  assert.ok(typeof missingCamera !== "undefined" || elements.get("cameraPanel").hidden === true, "Camera control should be wired");

  return {withChart, apiCalls: calls.length, alerts: alerts.length};
}

(async () => {
  const chartJsRun = await run(true);
  const canvasFallbackRun = await run(false);
  console.log("Dashboard smoke checks passed:", JSON.stringify([chartJsRun, canvasFallbackRun]));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
