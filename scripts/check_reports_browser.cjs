// Render every offline report EvalArc writes and check layout and accessibility basics:
// a verdict banner first, landmarks, scoped headers, keyboard-reachable tables,
// no horizontal page overflow at phone width, no console errors, no network requests.
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
const evalarc = process.env.EVALARC || "evalarc";
const out = fs.mkdtempSync(path.join(os.tmpdir(), "evalarc-reports-"));
const inspect = path.join(root, "examples/results-diff/inspect");
const climb = path.join(root, "examples/hillclimb-review");
const run = (...args) => {
  try { execFileSync(evalarc, args, { stdio: "pipe" }); } catch (error) { if (error.status === 2) throw error; }
};
run("diff", `${inspect}/baseline.json`, `${inspect}/current.json`, "--held-out", `${inspect}/split.json`,
    "--harness", `${inspect}/harness`, "--output", `${out}/diff`);
run("eval-health", `${inspect}/baseline.json`, `${inspect}/current.json`, "--cases", `${inspect}/cases.json`,
    "--min-effect", "0.05", "--output", `${out}/health`);
const steps = fs.readdirSync(`${climb}/results`).sort().map(name => `${climb}/results/${name}`);
run("hillclimb-review", ...steps, "--held-out", `${climb}/split.json`, "--objective", "cost", "--output", `${out}/climb`);
run("judge-packet", "grader", `${inspect}/current.json`, "--sample", "6", "--output", `${out}/spot`);
const key = JSON.parse(fs.readFileSync(`${out}/spot/key.json`, "utf8"));
const template = JSON.parse(fs.readFileSync(`${out}/spot/share/verdicts.template.json`, "utf8"));
for (const [id, hidden] of Object.entries(key.items)) template.verdicts[id] = hidden.recorded_passed ? "pass" : "fail";
fs.writeFileSync(`${out}/verdicts.json`, JSON.stringify(template));
run("judge-score", `${out}/spot`, `${out}/verdicts.json`, "--output", `${out}/score`);
run("eval-init", `${out}/proj`);
run("review-inputs", `${out}/proj/cases.jsonl`, "--output", `${out}/review`);

const reports = {
  diff: /Gate failed/, health: /warning\(s\) before tuning|Ready to tune/, climb: /Merge/,
  score: /Grader agrees with the judge/, review: /Inputs ready to run/,
};

(async () => {
  const browser = await chromium.launch();
  for (const [name, verdict] of Object.entries(reports)) {
    for (const width of [1280, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      const problems = [];
      page.on("console", message => message.type() === "error" && problems.push(message.text()));
      page.on("request", request => !request.url().startsWith("file:") && problems.push(request.url()));
      await page.goto(`file://${out}/${name}/index.html`);
      assert.deepEqual(problems, [], `${name}: console errors or network requests`);
      const banner = page.locator("main .verdict").first();
      assert(await banner.isVisible(), `${name}: verdict banner missing`);
      assert.match(await banner.innerText(), verdict, `${name}: unexpected verdict`);
      const first = await page.locator("main > *:not(.eyebrow):not(h1)").first().getAttribute("class");
      assert.match(first || "", /verdict/, `${name}: the verdict is not the first content`);
      assert.equal(await page.locator("th:not([scope])").count(), 0, `${name}: unscoped header`);
      assert.equal(await page.locator(".scroll:not([tabindex='0'])").count(), 0, `${name}: table not focusable`);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
             `${name}: page overflows at ${width}px`);
      assert.equal(await page.locator("html").getAttribute("lang"), "en");
      await page.keyboard.press("Tab");
      assert.equal(await page.evaluate(() => document.activeElement.className), "skip", `${name}: skip link`);
      await page.close();
    }
  }
  await browser.close();
  fs.rmSync(out, { recursive: true, force: true });
  console.log(`Checked ${Object.keys(reports).length} report pages at two widths.`);
})().catch(error => { console.error(error); process.exit(1); });
