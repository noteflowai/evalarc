"use strict";
const $ = id => document.getElementById(id);
const names = {none: "No skill", direct: "Direct", mcp: "MCP"};
let lab, selected, current;
function link(label, href) {const a = document.createElement("a"); a.textContent = label; a.href = href; return a;}
function metric(label, value, cls = "") {
  const dt = document.createElement("dt"), dd = document.createElement("dd");
  dt.textContent = label; dd.textContent = value; dd.className = cls; $("metrics").append(dt, dd);
}
function showTrial(row, updateHash = true) {
  selected = row;
  document.querySelectorAll(".trial").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.id === row.id)));
  $("trial-title").textContent = `${names[row.condition]} · seed ${row.seed}`;
  $("metrics").replaceChildren();
  metric("Independent score", `${(row.evaluation.score * 100).toFixed(1)}%`);
  metric("Task fully resolved", row.evaluation.resolved ? "Yes" : "No", row.evaluation.resolved ? "pass" : "fail");
  metric("Workflow", row.workflow_status);
  metric("Valid execution", row.evaluation.valid ? "Yes" : "No");
  metric("Skill opens", String(row.skill_loads));
  metric("Model turns / budget", `${row.steps} / 12`);
  metric("Generated tokens", String(row.completion_tokens));
  $("events").replaceChildren(...row.tool_sequence.map(name => {const li = document.createElement("li"); li.textContent = name; return li;}));
  const files = [["Trial JSON", "trial.json"], ["Independent grade", "evaluation.json"], ["ATIF trajectory", "trajectory.atif.json"]];
  if (row.candidate_sha256) files.push(["Candidate code", "main.py"]);
  $("downloads").replaceChildren(...files.map(([label, file]) => link(label, `${row.path}/${file}`)));
  $("provenance").textContent = JSON.stringify({model:row.model, skill_pins:row.skill_pins, prompt_sha256:row.prompt_sha256, tools_sha256:row.tools_sha256, candidate_sha256:row.candidate_sha256, trial_sha256:row.trial_sha256, atif_sha256:row.atif_sha256, error:row.error}, null, 2);
  if (updateHash) history.replaceState(null, "", `#profile=${current.id}&trial=${row.id}`);
}
function showProfile(id, trialId) {
  current = lab.profiles.find(p => p.id === id) || lab.profiles[2];
  $("profile").value = current.id;
  $("profile-description").textContent = current.description;
  $("chart").replaceChildren();
  const header = document.createElement("div"); header.className = "row";
  header.append(document.createElement("span"));
  for (const seed of [17,41,97]) {const span = document.createElement("span"); span.className = "seed"; span.textContent = `Seed ${seed}`; header.append(span);}
  $("chart").append(header);
  for (const condition of ["none","direct","mcp"]) {
    const line = document.createElement("div"); line.className = "row";
    const label = document.createElement("span"); label.className = "name"; label.textContent = names[condition]; line.append(label);
    for (const seed of [17,41,97]) {
      const row = current.trials.find(r => r.condition === condition && r.seed === seed);
      const button = document.createElement("button"); button.className = "trial"; button.dataset.id = row.id; button.type = "button";
      button.setAttribute("aria-label", `${names[condition]}, seed ${seed}, ${(row.evaluation.score*100).toFixed(1)} percent, ${row.evaluation.resolved ? "resolved" : "unresolved"}`);
      const text = document.createElement("span"); text.textContent = `${(row.evaluation.score*100).toFixed(1)}%`;
      const meter = document.createElement("span"), fill = document.createElement("span"); meter.className = "meter"; fill.className = "fill"; fill.style.width = `${row.evaluation.score*100}%`; meter.append(fill);
      button.append(text, meter); button.addEventListener("click", () => showTrial(row)); line.append(button);
    }
    $("chart").append(line);
  }
  $("profile-totals").textContent = `${current.trials.filter(t=>t.evaluation.resolved).length}/9 fully resolved · ${current.trials.filter(t=>t.workflow_status==="finished").length}/9 workflows finished`;
  $("experiment").href = `profiles/${current.id}/experiment.json`;
  $("atif-check").href = `profiles/${current.id}/atif-validation.json`;
  showTrial(current.trials.find(r=>r.id===trialId) || current.trials.find(r=>r.condition==="mcp"&&r.seed===17));
}
function restore() {const params = new URLSearchParams(location.hash.slice(1)); showProfile(params.get("profile"), params.get("trial"));}
async function load() {
  $("retry").hidden = true; $("status").textContent = "Loading recorded evidence…";
  try {
    const response = await fetch("lab.json"); if (!response.ok) throw new Error(`HTTP ${response.status}`);
    lab = await response.json();
    if (lab.schema !== "evalarc.skill-impact-site.v1" || lab.profiles.length !== 3 || lab.profiles.some(p=>p.trials.length!==9)) throw new Error("Unexpected evidence schema");
    $("profile").replaceChildren(...lab.profiles.map(p => {const option = document.createElement("option"); option.value = p.id; option.textContent = p.title; return option;}));
    restore(); $("workspace").hidden = false; $("status").textContent = "27 recorded trials loaded. Select any score to inspect its evidence.";
  } catch (error) {$("status").textContent = `Evidence could not load: ${error.message}. Retry or download lab.json directly.`; $("retry").hidden = false;}
}
$("retry").addEventListener("click", load);
$("profile").addEventListener("change", () => showProfile($("profile").value));
window.addEventListener("hashchange", () => {if (lab) restore();});
load();
