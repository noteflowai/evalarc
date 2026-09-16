"use strict";
// Progressive enhancement: the complete review is also readable without scripts.
const checks = [...document.querySelectorAll(".check")];
const buttons = [...document.querySelectorAll("[data-filter]")];
const status = document.getElementById("filter-status");

function filter(kind, clearHash = false) {
  let count = 0;
  for (const check of checks) {
    check.hidden = kind !== "all" && check.dataset.change !== kind;
    if (!check.hidden) count++;
  }
  for (const button of buttons) {
    button.setAttribute("aria-pressed", String(button.dataset.filter === kind));
  }
  status.textContent = `${count} of ${checks.length} checks shown · ${kind === "all" ? "all results" : kind + "s"}.`;
  if (clearHash && location.hash) {
    // Some file:// browser contexts restrict History API calls.
    try { history.replaceState(null, "", location.pathname + location.search); } catch {}
  }
}

function restoreCheck() {
  const target = checks.find(check => `#${check.id}` === location.hash);
  if (!location.hash) { filter("regression"); return; }
  filter("all");
  if (!target) {
    status.textContent = "This link does not identify a check in these reports. All checks are shown.";
    return;
  }
  target.open = true;
  target.querySelector("summary").focus({preventScroll: true});
  target.scrollIntoView({block: "start"});
}

for (const button of buttons) {
  button.addEventListener("click", () => filter(button.dataset.filter, true));
}
document.getElementById("filters").hidden = false;
if (location.protocol === "file:") {
  document.getElementById("archive-link").hidden = true;
  document.getElementById("offline-download").hidden = false;
  for (const link of document.querySelectorAll(".downloads a")) {
    link.setAttribute("href", link.getAttribute("href").split("?")[0]);
  }
}
window.addEventListener("hashchange", restoreCheck);
restoreCheck();
