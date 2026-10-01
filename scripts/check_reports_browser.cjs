// End-to-end usability and accessibility checks for EvalArc's offline reports and the
// `evalarc view` local viewer. Accessibility rules come from axe-core (WCAG 2.2 A/AA)
// in both light and dark color schemes; the task scenarios cover what a reviewer does:
// read the decision on the first screen, move by keyboard, sort and filter tables, read
// on a phone or at 400% zoom (320 px reflow), read without JavaScript, print, and
// browse every report from one index.
const assert = require("node:assert/strict");
const { execFileSync, spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { chromium } = require("playwright");
const { default: AxeBuilder } = require("@axe-core/playwright");

const root = path.resolve(__dirname, "..");
const evalarc = process.env.EVALARC || "evalarc";
const python = process.env.PYTHON || "python3";
const out = fs.mkdtempSync(path.join(os.tmpdir(), "evalarc-reports-"));
const runs = path.join(out, "runs");
const inspect = path.join(root, "examples/results-diff/inspect");
const climb = path.join(root, "examples/hillclimb-review");
const run = (...args) => {
  try { execFileSync(evalarc, args, { stdio: "pipe" }); } catch (error) { if (error.status === 2) throw error; }
};
run("diff", `${inspect}/baseline.json`, `${inspect}/current.json`, "--held-out", `${inspect}/split.json`,
    "--harness", `${inspect}/harness`, "--output", `${runs}/diff`);
run("eval-health", `${inspect}/baseline.json`, `${inspect}/current.json`, "--cases", `${inspect}/cases.json`,
    "--min-effect", "0.05", "--output", `${runs}/health`);
const steps = fs.readdirSync(`${climb}/results`).sort().map(name => `${climb}/results/${name}`);
run("hillclimb-review", ...steps, "--held-out", `${climb}/split.json`, "--objective", "cost", "--output", `${runs}/climb`);
run("judge-packet", "grader", `${inspect}/current.json`, "--sample", "6", "--output", `${out}/spot`);
const key = JSON.parse(fs.readFileSync(`${out}/spot/key.json`, "utf8"));
const template = JSON.parse(fs.readFileSync(`${out}/spot/share/verdicts.template.json`, "utf8"));
for (const [id, hidden] of Object.entries(key.items)) template.verdicts[id] = hidden.recorded_passed ? "pass" : "fail";
fs.writeFileSync(`${out}/verdicts.json`, JSON.stringify(template));
run("judge-score", `${out}/spot`, `${out}/verdicts.json`, "--output", `${runs}/score`);
run("eval-init", `${out}/proj`);
run("review-inputs", `${out}/proj/cases.jsonl`, "--output", `${runs}/review`);
const render = (kind, source, target) => execFileSync(python, ["-c", `
import json, sys
from pathlib import Path
from evalarc import report
data = json.loads(Path(sys.argv[2]).read_text())
getattr(report, "render_" + sys.argv[1])(data, Path(sys.argv[3]))`, kind, source, target]);
for (const [kind, source] of [["audit", "support-audit/audit.json"], ["evaluation", "evaluation/evaluation.json"],
  ["comparison", "comparison/comparison.json"], ["repetition", "repetition/repetition.json"], ["suite", "suite/suite.json"]]) {
  fs.mkdirSync(`${runs}/${kind}`, { recursive: true });
  fs.copyFileSync(`${root}/examples/${source}`, `${runs}/${kind}/${path.basename(source)}`);
  render(kind, `${root}/examples/${source}`, `${runs}/${kind}/index.html`);
}

const reports = {
  diff: /Gate failed/, health: /warning\(s\) before tuning|Ready to tune/, climb: /Merge/,
  score: /Grader agrees with the judge/, review: /Inputs ready to run/,
  audit: /declared faults detected/, evaluation: /Resolved|Not resolved|Unassessed/,
  comparison: /regressed/, repetition: /attempt\(s\) resolved/, suite: /job gate\(s\) accepted/,
};
const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

async function axe(page, label) {
  const result = await new AxeBuilder({ page }).withTags(WCAG).analyze();
  const violations = result.violations.map(v => `${v.id} (${v.nodes.length}): ${v.nodes[0].target}`);
  assert.deepEqual(violations, [], `${label}: axe violations`);
}

async function open(browser, url, options = {}) {
  const context = await browser.newContext(options);
  const page = await context.newPage();
  const problems = [];
  page.on("console", message => message.type() === "error" && problems.push(message.text()));
  page.on("pageerror", error => problems.push(String(error)));
  page.on("request", request => {
    const url = request.url();
    if (!url.startsWith("file:") && !url.startsWith("http://127.0.0.1:")) problems.push(url);
  });
  await page.goto(url);
  return { context, page, problems };
}

async function checkReport(browser, name, verdict) {
  const url = `file://${runs}/${name}/index.html`;
  for (const [scheme, viewport] of [["dark", { width: 1280, height: 800 }], ["light", { width: 390, height: 844 }]]) {
    const { context, page, problems } = await open(browser, url, { colorScheme: scheme, viewport });
    // Task 1: the decision is the first content and fits on the first screen.
    const banner = page.locator("main .verdict").first();
    assert.match(await banner.innerText(), verdict, `${name}: unexpected verdict`);
    const first = await page.locator("main > *:not(.eyebrow):not(h1)").first().getAttribute("class");
    assert.match(first || "", /verdict/, `${name}: the verdict is not the first content`);
    const box = await banner.boundingBox();
    assert(box.y + box.height <= viewport.height, `${name} ${scheme}: verdict below the first screen`);
    // Task 2: keyboard users can skip straight to the content.
    await page.keyboard.press("Tab");
    assert.equal(await page.evaluate(() => document.activeElement.className), "skip", `${name}: skip link`);
    await axe(page, `${name} ${scheme}`);
    assert.deepEqual(problems, [], `${name}: console errors or network requests`);
    await context.close();
  }
  // Task 5: 320 px wide (400% zoom) reflows without horizontal page scrolling.
  const narrow = await open(browser, url, { viewport: { width: 320, height: 640 } });
  assert(await narrow.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
         `${name}: page overflows at 320px`);
  await narrow.context.close();
  // Task 6: without JavaScript every row is still there and nothing is broken.
  const plain = await open(browser, url, { javaScriptEnabled: false });
  assert.equal(await plain.page.locator("th button, .tools").count(), 0, `${name}: no-JS leftovers`);
  assert.equal(await plain.page.locator("tbody tr[hidden]").count(), 0, `${name}: hidden rows without JS`);
  await plain.context.close();
}

async function checkSortAndFilter(browser) {
  // Task 3: sort the hillclimb steps by cost ratio with the keyboard.
  const { context, page, problems } = await open(browser, `file://${runs}/climb/index.html`);
  const header = page.getByRole("columnheader", { name: /Cost ratio/ });
  await header.getByRole("button").focus();
  await page.keyboard.press("Enter");
  assert.equal(await header.getAttribute("aria-sort"), "ascending");
  const table = page.locator("table", { has: header });
  const column = await header.evaluate(th => th.cellIndex);
  const values = async () => (await table.locator(`tbody tr td:nth-child(${column + 1})`).allInnerTexts())
    .map(Number).filter(Number.isFinite);
  const ascending = await values();
  assert.deepEqual(ascending, [...ascending].sort((a, b) => a - b), "ascending sort");
  await page.keyboard.press("Enter");
  assert.equal(await header.getAttribute("aria-sort"), "descending");
  const descending = await values();
  assert.deepEqual(descending, [...descending].sort((a, b) => b - a), "descending sort");
  assert.equal(await page.locator("[aria-sort]").count(), 1, "aria-sort on one header only");
  await axe(page, "climb after sorting");
  await context.close();
  // Task 4: filter the diff's changed checks to the regressions and back.
  const diff = await open(browser, `file://${runs}/diff/index.html`);
  const filter = diff.page.getByLabel("Filter rows").first();
  await filter.fill("regressed");
  const count = diff.page.locator(".count").first();
  assert.match(await count.innerText(), /^2 of \d+ rows$/);
  const visible = await diff.page.locator("table").first().locator("tbody tr:not([hidden])").allInnerTexts();
  assert(visible.every(text => /regressed/.test(text)), "filtered rows match");
  await filter.fill("");
  assert.match(await count.innerText(), /^(\d+) of \1 rows$/);
  await axe(diff.page, "diff with filter");
  // Task 7: printing keeps the verdict and drops interactive controls.
  await diff.page.emulateMedia({ media: "print" });
  assert(await diff.page.locator(".verdict").first().isVisible());
  assert(await diff.page.locator(".tools").first().isHidden());
  assert.deepEqual([...problems, ...diff.problems], []);
  await diff.context.close();
}

async function checkViewer(browser) {
  // Task 8: browse every report from one local index and open one.
  const server = spawn(evalarc, ["view", runs, "--port", "0", "--no-browser"], { stdio: ["ignore", "pipe", "pipe"] });
  const url = await new Promise((resolve, reject) => {
    let text = "";
    server.stdout.on("data", chunk => {
      text += chunk;
      const match = text.match(/http:\/\/127\.0\.0\.1:\d+\//);
      if (match) resolve(match[0]);
    });
    server.on("exit", code => reject(new Error(`evalarc view exited ${code}`)));
    setTimeout(() => reject(new Error("evalarc view did not start")), 15000);
  });
  try {
    const { context, page, problems } = await open(browser, url);
    const rows = page.locator("tbody tr");
    assert.equal(await rows.count(), Object.keys(reports).length, "every report listed");
    assert.match(await page.locator("main").innerText(), /with a failing verdict/);
    await axe(page, "viewer index");
    await page.getByRole("link", { name: "climb", exact: true }).click();
    await page.getByText(/Merge/).first().waitFor();
    assert.match(page.url(), /\/climb\/index\.html$/);
    await page.goBack();
    await page.getByLabel("Filter rows").fill("Hillclimb");
    assert.equal(await page.locator("tbody tr:not([hidden])").count(), 1);
    assert.deepEqual(problems, []);
    await context.close();
  } finally {
    server.kill();
  }
}

(async () => {
  const browser = await chromium.launch();
  try {
    for (const [name, verdict] of Object.entries(reports)) await checkReport(browser, name, verdict);
    await checkSortAndFilter(browser);
    await checkViewer(browser);
  } finally {
    await browser.close();
  }
  fs.rmSync(out, { recursive: true, force: true });
  console.log(`Checked ${Object.keys(reports).length} report kinds (light, dark, 390/320 px, no-JS, print), ` +
              "keyboard sorting and filtering, and the local viewer with axe-core WCAG 2.2 AA.");
})().catch(error => { console.error(error); process.exit(1); });
