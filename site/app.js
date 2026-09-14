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
let comparison, baseline, current;
const pretty = (data) => JSON.stringify(data, null, 2);
const percent = (value) => value === null ? "Unassessed" : `${Number((value * 100).toFixed(4))}%`;
const repetitions = {};
async function loadSuite() {
  const response = await fetch("suite/suite.json");
  if (!response.ok) throw new Error("Suite evidence unavailable");
  const suite = await response.json();
  const jobs = {};
  for (const name of ["partial", "protected"]) {
    const job = suite.jobs.find(row => row.id === "support-" + name);
    jobs[name] = job;
    badge($("suite-" + name + "-verdict"), job.decision.accepted, job.decision.accepted ? "GATE ACCEPTED" : "GATE REJECTED");
    $("suite-" + name + "-score").textContent = percent(job.observed.mean_score);
    $("suite-" + name + "-resolution").textContent = `${job.observed.resolved_attempts} / ${job.observed.completed_attempts} attempts fully resolved`;
    $("suite-" + name + "-gate").textContent =
      `Minimum mean score: ${percent(job.gate.min_mean_score)}\nMinimum resolution rate: ${percent(job.gate.min_resolution_rate)}\nRequired dimensions: ${job.gate.required_dimensions.join(", ") || "none"}`;
  }
  $("suite-summary").textContent = `${suite.accepted_jobs} / ${suite.total_jobs} gates accepted. ${suite.fully_resolved_jobs} / ${suite.total_jobs} jobs fully resolved. ${suite.invalid_jobs} invalid jobs. The coding reference passes its default strict gate.`;
  $("suite-provenance").textContent = pretty({
    manifest_sha256: suite.manifest_sha256,
    same_candidate: jobs.partial.candidate_sha256 === jobs.protected.candidate_sha256,
    candidate_sha256: jobs.partial.candidate_sha256,
    grader_sha256: jobs.partial.grader_sha256,
    cases_sha256: jobs.partial.cases_sha256,
    runtime: jobs.partial.runtime,
    permissive_gate: jobs.partial.decision,
    protected_gate: jobs.protected.decision,
    interpretation: suite.interpretation,
  });
  $("suite-status").hidden = true;
  $("suite-workspace").hidden = false;
}
loadSuite().catch(() => {
  $("suite-status").textContent = "Suite evidence could not be loaded. Open the standalone suite report below.";
});
function chooseRepetition(name) {
  const record = repetitions[name];
  if (!record) return;
  for (const control of ["reference", "faulty"]) $("repeat-" + control).setAttribute("aria-pressed", String(control === name));
  $("repeat-resolved").textContent = `${record.resolved_attempts} / ${record.requested_attempts}`;
  $("repeat-score").textContent = percent(record.mean_score);
  $("repeat-invalid").textContent = String(record.invalid_attempts);
  $("repeat-variable").textContent = String(record.variable_checks);
  $("repeat-attempts").replaceChildren();
  for (const attempt of record.attempts) {
    const card = document.createElement("a");
    card.className = `repeat-attempt ${attempt.resolved ? "pass" : "fail"}`;
    card.href = `repeat/${name}/attempts/${String(attempt.attempt).padStart(4, "0")}/index.html`;
    const label = document.createElement("span"); label.textContent = `ATTEMPT ${String(attempt.attempt).padStart(2, "0")}`;
    const score = document.createElement("strong"); score.textContent = percent(attempt.score);
    const verdict = document.createElement("span"); verdict.className = "badge";
    verdict.textContent = !attempt.valid ? "INVALID RUN" : attempt.resolved ? "RESOLVED" : "NOT RESOLVED";
    const link = document.createElement("span"); link.className = "caption"; link.textContent = "Open full evidence \u2197";
    card.append(label, score, verdict, link); $("repeat-attempts").append(card);
  }
  $("repeat-cases").replaceChildren();
  for (const row of record.cases) {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    const title = document.createElement("span"); title.textContent = `${row.case_id} / seed ${row.seed}`;
    const outcome = document.createElement("span"); outcome.className = row.failed ? "fail" : "pass";
    outcome.textContent = `${row.passed} / ${row.assessed} passed`;
    summary.append(title, outcome); details.append(summary);
    const checks = document.createElement("div"); checks.className = "check-list";
    for (const [check, count] of Object.entries(row.checks)) {
      const item = document.createElement("span"); item.className = count.passed < count.assessed ? "fail" : "pass";
      item.textContent = `${check}: ${count.passed} / ${count.assessed}`; checks.append(item);
    }
    details.append(checks);
    const invalid = document.createElement("p"); invalid.className = "caption";
    invalid.textContent = `${row.unassessed} unassessed observations. Check counts use assessed observations only.`;
    details.append(invalid); $("repeat-cases").append(details);
  }
  $("repeat-context").textContent = name === "faulty"
    ? "A stable score can describe a stable defect. All three attempts fail the retry-after-commit note check; none is selected or discarded."
    : "All three reference attempts resolve the same four public cases. This is a functional control; repeated passes do not expand task coverage.";
  for (const [id, file] of [["report", "index.html"], ["json", "repetition.json"], ["events", "events.jsonl"]]) $("repeat-" + id).href = `repeat/${name}/${file}`;
  $("repeat-provenance").textContent = pretty({
    candidate_sha256: record.candidate_sha256, grader_sha256: record.grader_sha256,
    cases_sha256: record.cases_sha256, task: record.task, seeds: record.seeds,
    runtime: record.runtime, completed_attempts: record.completed_attempts,
    assessed_attempts: record.assessed_attempts, invalid_attempts: record.invalid_attempts,
    interpretation: record.interpretation,
  });
}
for (const name of ["reference", "faulty"]) $("repeat-" + name).addEventListener("click", () => chooseRepetition(name));
Promise.all(["reference", "faulty"].map(async (name) => {
  const response = await fetch(`repeat/${name}/repetition.json`);
  if (!response.ok) throw new Error("Repetition evidence unavailable");
  repetitions[name] = await response.json();
})).then(() => {
  chooseRepetition("faulty");
  $("repeat-status").hidden = true;
  $("repeat-workspace").hidden = false;
}).catch(() => {
  $("repeat-status").textContent = "Repetition evidence could not be loaded. Open a standalone report:";
  for (const name of ["reference", "faulty"]) {
    const link = document.createElement("a"); link.href = `repeat/${name}/index.html`; link.textContent = ` ${name} report`;
    $("repeat-status").append(link);
  }
});
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
function chooseTransition(index) {
  const transition = comparison.case_transitions[index];
  [...$("changed-cases").children].forEach((button, i) => button.setAttribute("aria-pressed", String(i === index)));
  $("comparison-result").textContent = transition.regressed_checks.length
    ? `${transition.case_id}: ${transition.regressed_checks.join(", ")} changed from passing to failing. The current policy leaves a duplicate note.`
    : `${transition.case_id}: ${transition.improved_checks.join(", ")} changed from failing to passing. The current policy preserves the open status of this unresolved ticket.`;
  for (const [side, report] of [["before", baseline], ["after", current]]) {
    const row = report.cases.find((item) => item.seed === transition.seed && item.case_id === transition.case_id);
    badge($(side + "-verdict"), row.passed, row.status.toUpperCase());
    $(side + "-checks").replaceChildren();
    for (const [name, passed] of Object.entries(row.checks)) {
      const check = document.createElement("span");
      check.className = passed ? "pass" : "fail";
      check.textContent = `${name}: ${passed ? "pass" : "fail"}`;
      $(side + "-checks").append(check);
    }
    const ticketId = row.trace.find((step) => step.action?.tool === "get_ticket").action.arguments.ticket_id;
    $(side + "-state").textContent = pretty({ticket_id: ticketId, ...row.final_state[ticketId]});
  }
}
async function loadComparison() {
  [comparison, baseline, current] = await Promise.all(["comparison", "baseline", "current"].map(async (name) => {
    const response = await fetch(`comparison/${name}.json`);
    if (!response.ok) throw new Error("Comparison evidence unavailable");
    return response.json();
  }));
  $("before-score").textContent = percent(comparison.baseline.score);
  $("after-score").textContent = percent(comparison.current.score);
  $("regression-count").textContent = `${comparison.regressions.length} REGRESSED CHECK`;
  $("compare-delta").textContent = `+${Number((comparison.score_delta * 100).toFixed(4))} percentage points`;
  comparison.case_transitions.forEach((transition, index) => {
    const button = document.createElement("button"); button.type = "button";
    const tag = document.createElement("span"); tag.className = transition.regressed_checks.length ? "fail" : "pass";
    tag.textContent = transition.regressed_checks.length ? "REGRESSED" : "IMPROVED";
    button.append(tag, document.createTextNode(transition.case_id));
    button.addEventListener("click", () => chooseTransition(index));
    $("changed-cases").append(button);
  });
  chooseTransition(0);
  $("comparison-status").hidden = true;
  $("comparison-workspace").hidden = false;
}
loadComparison().catch(() => {
  $("comparison-status").textContent = "Comparison evidence could not be loaded. Reload the page or open the standalone report.";
  const link = document.createElement("a"); link.href = "comparison/index.html"; link.textContent = "Open comparison report";
  $("comparison-status").append(document.createTextNode(" "), link);
});
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
