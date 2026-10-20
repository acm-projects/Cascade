// Runs the REAL showAgentSteps() from flow_C.js against a tiny stand-in DOM (no browser needed).
// Run by tests/test_steps_panel.py, or directly: node tests/steps_panel_check.js
const fs = require("fs");
const path = require("path");
const src = fs.readFileSync(path.join(__dirname, "..", "web", "flow_C.js"), "utf8");
const a = src.indexOf("  function showAgentSteps(job, jobId) {");
const b = src.indexOf("  async function pollJob(jobId) {");
if (a < 0 || b < 0) throw new Error("could not locate showAgentSteps in flow_C.js");
const fnSource = src.slice(a, b);

// ---- minimal DOM
class El {
  constructor(tag) { this.tag = tag; this.children = []; this.style = {}; this.dataset = {}; this.hidden = false; this.open = false;
    this.id = ""; this._text = ""; this.scrollTop = 0; this.clientHeight = 100; this.scrollHeight = 100; this.parent = null; }
  set textContent(v) { this._text = String(v); this.children = []; }
  get textContent() { return this._text; }
  append(...kids) { for (const k of kids) { k.parent = this; this.children.push(k); } }
  replaceChildren(...kids) { this.children = []; this.append(...kids); this.scrollHeight = 100 + this.children.length * 20; }
  after(node) { this.sibling = node; node.parent = this.parent; }
}
const registry = {};
const document = { createElement: (t) => new El(t) };
const status = new El("p"); status.id = "status"; registry.status = status;
const $ = (id) => {
  if (registry[id]) return registry[id];
  if (id === "agent-steps-list") { return registry["agent-steps"]?.children.find(c => c.id === "agent-steps-list") || null; }
  return null;
};
// the real function registers its panel via anchor.after(panel); mirror lookups by id afterwards
const origAfter = El.prototype.after;
El.prototype.after = function (node) { origAfter.call(this, node); if (node.id) registry[node.id] = node; };

const showAgentSteps = new Function("$", "document", fnSource + "; return showAgentSteps;")($, document);

let failures = 0;
const check = (cond, msg) => { if (!cond) { failures++; console.log("FAIL:", msg); } else console.log("ok  :", msg); };

// 1. no steps yet -> panel exists but is hidden
showAgentSteps({ state: "processing", steps_log: [] }, "job-1");
let panel = registry["agent-steps"];
check(panel && panel.hidden === true, "panel is created and hidden while there are no steps");

// 2. steps arrive -> shown, open, rendered as text
showAgentSteps({ state: "processing", steps_log: ["Indexing video", "Agent turn 1/8", "Tool call: search_video(query='<img src=x onerror=alert(1)>')"] }, "job-1");
let list = $("agent-steps-list");
check(panel.hidden === false && panel.open === true, "panel is shown and open while the job runs");
check(list.children.length === 3 && list.children[1].textContent === "Agent turn 1/8", "each step is one list row, in order");
check(list.children[2].textContent.includes("<img src=x"), "tool arguments are shown as text (textContent), not parsed as HTML");
check(list.children.every(c => c.tag === "li"), "rows are <li> elements");
showAgentSteps({ state: "processing", steps_log: ["Indexing video", "Agent turn 1/8", "x"], steps_elapsed: [0.4, 121.26] }, "job-1");
list = $("agent-steps-list");
check(list.children[0].textContent === "[0.4s] Indexing video" && list.children[1].textContent === "[121.3s] Agent turn 1/8", "each step shows its elapsed time");
check(list.children[2].textContent === "x", "a step without a time is shown as plain text");

// 3. new steps follow the bottom when the user is already at the bottom
list.scrollTop = list.scrollHeight - list.clientHeight; // at the bottom
showAgentSteps({ state: "processing", steps_log: ["a", "b", "c", "d"] }, "job-1");
check(list.scrollTop === list.scrollHeight, "auto-scrolls to the newest step when the user was at the bottom");

// 4. user scrolled up -> do not yank them down
list.scrollTop = 0; list.scrollHeight = 5000; list.clientHeight = 100;
showAgentSteps({ state: "processing", steps_log: ["a", "b", "c", "d", "e"] }, "job-1");
check(list.scrollTop === 0, "does not jump to the bottom when the user scrolled up to read");

// 5. done -> collapses once, and stays collapsed if the user reopens it
showAgentSteps({ state: "done", steps_log: ["a", "b", "c", "d", "e"] }, "job-1");
check(panel.open === false, "collapses when the job finishes");
panel.open = true; // the user reopens it to read
showAgentSteps({ state: "done", steps_log: ["a", "b", "c", "d", "e"] }, "job-1");
check(panel.open === true, "a finished job's panel is not force-closed again after the user reopens it");

// 6. a NEW job resets the panel (open again, new steps)
showAgentSteps({ state: "processing", steps_log: ["Indexing video"] }, "job-2");
check(panel.open === true && panel.dataset.job === "job-2" && list.children.length === 1, "a new job reopens the panel with the new job's steps only");

// 7. failure also collapses, and missing/invalid steps_log never throws
showAgentSteps({ state: "error", steps_log: ["x"] }, "job-2");
check(panel.open === false, "collapses on error too");
let threw = false;
try { showAgentSteps({ state: "processing" }, "job-3"); showAgentSteps({ state: "processing", steps_log: "nope" }, "job-3"); } catch (e) { threw = true; }
check(!threw && panel.hidden === true, "a missing or malformed steps_log is tolerated (panel just hidden)");

console.log(failures === 0 ? "\nALL PASSED" : `\n${failures} FAILED`);
process.exit(failures ? 1 : 0);
