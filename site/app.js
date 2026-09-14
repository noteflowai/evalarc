"use strict";
const $ = (id) => document.getElementById(id);
const packs = {
  support: {path: "support", defaultControl: "new-key-on-retry", defaultCase: "retry-after-commit"},
  coding: {path: "coding", defaultControl: "boolean-equals-one", defaultCase: "cas-type-sensitivity"},
};
const stories = {
  "new-key-on-retry": "The service committed the first note, then returned a retryable error. A new idempotency key on retry created a second note. Move through the trace to see both state changes.",
  "boolean-equals-one": "The implementation treats JSON true and 1 as equal. Compare-and-swap accepts a mismatch: a 92.5% aggregate score still leaves a broken contract.",
  reference: "The known-good control satisfies every recorded check. Compare its behavior with a deliberately faulty implementation to audit the grader.",
};
let audits = {}, pack = "support", evaluation, selectedCase;
const pretty = (data) => JSON.stringify(data, null, 2);
const percent = (value) => value === null ? "Unassessed" : `${Number((value * 100).toFixed(4))}%`;
function badge(element, passed, text) {
  element.className = `badge ${passed ? "pass" : "fail"}`;
  element.textContent = text;
}
function choosePack(nextPack) {
  pack = nextPack;
  for (const name of Object.keys(packs)) $(name + "-task").setAttribute("aria-pressed", String(pack === name));
  const select = $("control");
  select.replaceChildren();
  for (const row of [{name: "reference"}, ...audits[pack].mutants]) {
    const option = document.createElement("option");
    option.value = row.name;
    option.textContent = row.name === "reference" ? "Reference / known-good control" : row.name;
    select.append(option);
  }
  select.value = packs[pack].defaultControl;
  $("report-link").href = `${packs[pack].path}/index.html`;
  $("download-link").href = `${packs[pack].path}/audit.json`;
  chooseControl();
}
function chooseControl() {
  const name = $("control").value;
  const audit = audits[pack];
  const mutant = audit.mutants.find((row) => row.name === name);
  evaluation = name === "reference" ? audit.reference : mutant.evaluation;
  $("score").textContent = percent(evaluation.score);
  badge($("verdict"), evaluation.resolved, evaluation.valid === false ? "INVALID RUN" : evaluation.resolved ? "FULLY RESOLVED" : "NOT RESOLVED");
  $("result-context").textContent = evaluation.valid === false ? "An environment failure is not a scored candidate failure." : "Full resolution requires every case to pass. A partial score is not acceptance.";
  $("checks-count").textContent = `${evaluation.cases.filter((row) => row.passed).length} / ${evaluation.cases.length}`;
  $("story").textContent = stories[name] || `Declared negative control: ${name}. Its intended detection dimension is ${mutant.target_dimension}. Select a failing case to inspect the recorded evidence.`;
  $("dimensions").replaceChildren();
  for (const [key, value] of Object.entries(evaluation.dimensions)) {
    const div = document.createElement("div"); div.className = "dimension";
    const label = document.createElement("div");
    const title = document.createElement("span"); title.textContent = key;
    const score = document.createElement("span"); score.textContent = percent(value.score);
    label.append(title, score);
    const meter = document.createElement("meter"); meter.min = 0; meter.max = 1; meter.value = value.score ?? 0; meter.setAttribute("aria-label", `${key}: ${score.textContent}`);
    div.append(label, meter); $("dimensions").append(div);
  }
  $("cases").replaceChildren();
  evaluation.cases.forEach((row, index) => {
    const button = document.createElement("button"); button.type = "button";
    const status = document.createElement("span"); status.className = row.passed ? "pass" : "fail"; status.textContent = row.passed ? "PASS" : row.status.toUpperCase();
    button.append(status, document.createTextNode(row.case_id));
    button.addEventListener("click", () => chooseCase(index));
    $("cases").append(button);
  });
  $("provenance").textContent = pretty({
    task: evaluation.task, created_at: evaluation.created_at, seeds: evaluation.seeds,
    evalarc_version: evaluation.evalarc_version, candidate_sha256: evaluation.candidate_sha256,
    grader_sha256: evaluation.grader_sha256, cases_sha256: evaluation.cases_sha256,
    runtime: evaluation.runtime, agent_cost_usd: evaluation.agent_cost_usd, agent_tokens: evaluation.agent_tokens,
  });
  let index = evaluation.cases.findIndex((row) => !row.passed);
  if (index < 0) index = evaluation.cases.findIndex((row) => row.case_id === packs[pack].defaultCase);
  chooseCase(Math.max(index, 0));
}
function chooseCase(index) {
  selectedCase = evaluation.cases[index];
  [...$("cases").children].forEach((button, i) => button.setAttribute("aria-pressed", String(i === index)));
  $("case-title").textContent = `${selectedCase.case_id} / seed ${selectedCase.seed}`;
  badge($("case-verdict"), selectedCase.passed, selectedCase.status.toUpperCase());
  $("case-checks").replaceChildren();
  for (const [name, passed] of Object.entries(selectedCase.checks)) {
    const item = document.createElement("span"); item.className = passed ? "pass" : "fail"; item.textContent = `${name}: ${passed ? "pass" : "fail"}`; $("case-checks").append(item);
  }
  $("case-error").textContent = selectedCase.error || "";
  const hasTrace = Array.isArray(selectedCase.trace) && selectedCase.trace.length > 0;
  $("trace-panel").hidden = !hasTrace;
  $("coding-panel").hidden = hasTrace;
  if (hasTrace) {
    $("states").textContent = pretty({initial_state: selectedCase.initial_state, final_state: selectedCase.final_state});
    $("trace-step").max = selectedCase.trace.length - 1;
    $("trace-step").value = 0;
    showStep();
  } else {
    $("coding-evidence").textContent = pretty(selectedCase);
  }
}
function showStep() {
  const index = Number($("trace-step").value);
  const step = selectedCase.trace[index];
  $("step-label").textContent = `${index + 1} / ${selectedCase.trace.length}`;
  $("trace-action").textContent = pretty(Object.fromEntries(Object.entries(step).filter(([key]) => key !== "changes")));
  $("trace-changes").textContent = step.changes && Object.keys(step.changes).length ? pretty(step.changes) : "No state change in this step.";
  $("previous-step").disabled = index === 0;
  $("next-step").disabled = index === selectedCase.trace.length - 1;
}
$("control").addEventListener("change", chooseControl);
$("trace-step").addEventListener("input", showStep);
$("previous-step").addEventListener("click", () => { $("trace-step").stepDown(); showStep(); });
$("next-step").addEventListener("click", () => { $("trace-step").stepUp(); showStep(); });
for (const name of Object.keys(packs)) $(name + "-task").addEventListener("click", () => { if (audits[name]) choosePack(name); });
Promise.all(Object.entries(packs).map(async ([name, config]) => {
  const response = await fetch(`${config.path}/audit.json`);
  if (!response.ok) throw new Error(`Evidence request failed (${response.status})`);
  audits[name] = await response.json();
})).then(() => {
  choosePack("support");
  $("load-status").hidden = true;
  $("workspace").hidden = false;
}).catch(() => {
  $("load-status").textContent = "Evidence could not be loaded. Reload this page, or open the standalone support and coding reports linked below.";
  const links = document.createElement("p");
  for (const [name, config] of Object.entries(packs)) {
    const link = document.createElement("a"); link.href = `${config.path}/index.html`; link.textContent = `Open ${name} report`;
    links.append(link, document.createTextNode("  "));
  }
  $("load-status").after(links);
});
