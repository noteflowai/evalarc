const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { once } = require("node:events");

async function main() {
  const root = path.resolve(process.env.SITE_DIR || "dist/site");
  let server;
  let base = process.env.SITE_URL;
  if (!base) {
    const mime = {".html":"text/html", ".js":"text/javascript", ".json":"application/json", ".css":"text/css", ".svg":"image/svg+xml"};
    server = http.createServer((req, res) => {
      const route = decodeURIComponent(new URL(req.url, "http://localhost").pathname);
      const filename = path.resolve(root, "." + (route.endsWith("/") ? route + "index.html" : route));
      if (!filename.startsWith(root + path.sep) || !fs.existsSync(filename) || !fs.statSync(filename).isFile()) {
        res.writeHead(404).end(); return;
      }
      res.writeHead(200, {"Content-Type": mime[path.extname(filename)] || "text/plain"});
      fs.createReadStream(filename).pipe(res);
    });
    server.listen(0, "127.0.0.1"); await once(server, "listening");
    base = `http://127.0.0.1:${server.address().port}/`;
  }
  const browser = await chromium.launch({headless:true});
  try {
    const results = [];
    for (const width of [1440, 390]) {
      const page = await browser.newPage({viewport:{width, height:1000}});
      const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      await page.goto(base, {waitUntil:"networkidle", timeout:60000});
      const app = process.env.SITE_HUB === "1" ? page.frameLocator('iframe[src*="hf.space"]') : page;
      await app.locator("#workspace").waitFor({state:"visible"});
      await app.locator("#comparison-workspace").waitFor({state:"visible"});
      await app.locator("#repeat-workspace").waitFor({state:"visible"});
      await app.locator("#suite-workspace").waitFor({state:"visible"});
      await page.waitForLoadState("networkidle");
      for (const name of ["partial", "protected"]) {
        assert.equal(await app.locator("#suite-" + name + "-score").innerText(), "93.75%");
        assert.equal(await app.locator("#suite-" + name + "-resolution").innerText(), "0 / 2 attempts fully resolved");
      }
      assert.equal(await app.locator("#suite-partial-verdict").innerText(), "GATE ACCEPTED");
      assert.equal(await app.locator("#suite-protected-verdict").innerText(), "GATE REJECTED");
      assert.match(await app.locator("#suite-summary").innerText(), /2 \/ 3 gates accepted\. 1 \/ 3 jobs fully resolved\. 0 invalid jobs/);
      await app.locator("#suite-provenance").locator("..").locator("summary").click();
      const suiteProvenance = JSON.parse(await app.locator("#suite-provenance").innerText());
      assert.equal(suiteProvenance.same_candidate, true);
      assert.equal(suiteProvenance.protected_gate.reasons.length, 1);
      await app.locator("#suite-provenance").locator("..").locator("summary").click();
      const suiteBase = await app.locator("body").evaluate(() => location.href);
      const junitResponse = await page.request.get(new URL("suite/junit.xml", suiteBase).href);
      assert.equal(junitResponse.status(), 200);
      const junit = await page.evaluate(xml => {
        const document = new DOMParser().parseFromString(xml, "application/xml");
        return {tests:document.querySelectorAll("testcase").length, failures:document.querySelectorAll("failure").length, errors:document.querySelectorAll("error").length, rejected:document.querySelector("failure")?.parentElement.getAttribute("name"), parserErrors:document.querySelectorAll("parsererror").length};
      }, await junitResponse.text());
      assert.deepEqual(junit, {tests:3,failures:1,errors:0,rejected:"support-protected",parserErrors:0});
      assert.equal(await app.locator("#repeat-resolved").innerText(), "0 / 3");
      assert.equal(await app.locator("#repeat-score").innerText(), "93.75%");
      assert.equal(await app.locator("#repeat-invalid").innerText(), "0");
      assert.equal(await app.locator("#repeat-variable").innerText(), "0");
      await app.locator("#repeat-provenance").locator("..").locator("summary").click();
      for (const control of ["faulty", "reference"]) {
        await app.locator("#repeat-" + control).click();
        assert.equal(await app.locator("#repeat-resolved").innerText(), control === "reference" ? "3 / 3" : "0 / 3");
        assert.equal(await app.locator("#repeat-score").innerText(), control === "reference" ? "100%" : "93.75%");
        assert.equal(await app.locator("#repeat-attempts a").count(), 3);
        assert.equal(await app.locator("#repeat-cases details").count(), 4);
        const retry = app.locator("#repeat-cases details").filter({hasText:"retry-after-commit"});
        await retry.locator("summary").click();
        assert.match(await retry.innerText(), control === "reference" ? /notes: 3 \/ 3/ : /notes: 0 \/ 3/);
        await retry.locator("summary").click();
        const appUrl = await app.locator("body").evaluate(() => location.href);
        const expected = JSON.parse(await app.locator("#repeat-provenance").innerText());
        const response = await page.request.get(new URL(`repeat/${control}/repetition.json`, appUrl).href);
        assert.equal(response.status(), 200);
        const summary = await response.json();
        for (let i=0;i<3;i++) {
          const attempt = `repeat/${control}/attempts/${String(i+1).padStart(4,"0")}/`;
          const recordResponse = await page.request.get(new URL(attempt + "evaluation.json", appUrl).href);
          assert.equal(recordResponse.status(), 200);
          const record = await recordResponse.json();
          assert.equal(record.candidate_sha256, expected.candidate_sha256);
          assert.equal(record.grader_sha256, expected.grader_sha256);
          assert.equal(record.score, summary.attempts[i].score);
          assert.equal(record.resolved, control === "reference");
        }
      }
      await app.locator("#repeat-provenance").locator("..").locator("summary").click();
      await app.locator("#repeat-faulty").click();
      await app.locator("#repeat-attempts a").first().hover();
      assert.equal(await app.locator("#repeat-attempts .badge").first().evaluate(element => getComputedStyle(element).color), "rgb(239, 173, 139)");
      assert.equal(await app.locator("#before-score").innerText(), "90%");
      assert.equal(await app.locator("#after-score").innerText(), "93.75%");
      assert.equal(await app.locator("#regression-count").innerText(), "1 REGRESSED CHECK");
      assert.equal(await app.locator("#compare-delta").innerText(), "+3.75 percentage points");
      assert.equal(await app.locator("#before-verdict").innerText(), "PASSED");
      assert.equal(await app.locator("#after-verdict").innerText(), "FAILED");
      assert.equal(JSON.parse(await app.locator("#before-state").innerText()).notes.length, 2);
      assert.equal(JSON.parse(await app.locator("#after-state").innerText()).notes.length, 3);
      for (let i=1;i<3;i++) {
        await app.locator("#changed-cases button").nth(i).click();
        assert.equal(await app.locator("#before-verdict").innerText(), "FAILED");
        assert.equal(await app.locator("#after-verdict").innerText(), "PASSED");
        assert.equal(JSON.parse(await app.locator("#before-state").innerText()).status, "closed");
        assert.equal(JSON.parse(await app.locator("#after-state").innerText()).status, "open");
      }
      await app.locator("#changed-cases button").first().click();
      assert.equal(await app.locator("#score").innerText(), "93.75%");
      assert.equal(await app.locator("#verdict").innerText(), "NOT RESOLVED");
      assert.match(await app.locator("#case-title").innerText(), /retry-after-commit/);
      // A committed write can accompany a tool error. The next step duplicates it.
      await app.locator("#next-step").click(); await app.locator("#next-step").click();
      assert.match(await app.locator("#trace-action").innerText(), /temporarily_unavailable/);
      assert.match(await app.locator("#trace-changes").innerText(), /Reviewed request/);
      await app.locator("#next-step").click();
      const faulty = JSON.parse(await app.locator("#trace-changes").innerText());
      assert.equal(Object.values(faulty)[0].after.notes.length, 3);
      await app.locator("#control").selectOption("reference");
      assert.equal(await app.locator("#score").innerText(), "100%");
      assert.equal(await app.locator("#verdict").innerText(), "FULLY RESOLVED");
      for (let i=0;i<3;i++) await app.locator("#next-step").click();
      assert.match(await app.locator("#trace-action").innerText(), /replayed/);
      assert.equal(await app.locator("#trace-changes").innerText(), "No state change in this step.");
      await app.locator("#coding-task").click();
      assert.equal(await app.locator("#score").innerText(), "92.5%");
      assert.match(await app.locator("#case-title").innerText(), /cas-type-sensitivity/);
      assert.match(await app.locator("#coding-evidence").innerText(), /response mismatch/);
      for (const task of ["support", "coding"]) {
        await app.locator(`#${task}-task`).click();
        const values = await app.locator("#control option").evaluateAll(options => options.map(o => o.value));
        for (const value of values) {
          await app.locator("#control").selectOption(value);
          assert.equal(await app.locator("#verdict").innerText(), value === "reference" ? "FULLY RESOLVED" : "NOT RESOLVED");
          for (let i=0; i<await app.locator("#cases button").count();i++) {
            await app.locator("#cases button").nth(i).click();
            assert.ok((await app.locator("#case-title").innerText()).includes("seed 17"));
          }
        }
      }
      const overflow = await app.locator("body").evaluate(() => document.documentElement.scrollWidth > innerWidth);
      assert.equal(overflow, false, `Horizontal overflow at ${width}px`);
      await app.locator("#support-task").click();
      if (process.env.SITE_SCREENSHOTS) {
        fs.mkdirSync(process.env.SITE_SCREENSHOTS, {recursive:true});
        await page.evaluate(() => scrollTo(0,0));
        await page.screenshot({path:path.join(process.env.SITE_SCREENSHOTS, `evalarc-${width}.png`), fullPage:true});
        await app.locator("#regression").screenshot({path:path.join(process.env.SITE_SCREENSHOTS, `regression-${width}.png`)});
        await app.locator("#repeat").screenshot({path:path.join(process.env.SITE_SCREENSHOTS, `repeat-${width}.png`)});
        await app.locator("#suite").screenshot({path:path.join(process.env.SITE_SCREENSHOTS, `suite-${width}.png`)});
      }
      const appUrl = await app.locator("body").evaluate(() => location.href);
      await app.getByRole("link", {name:"Full comparison report", exact:false}).click();
      await app.getByRole("heading", {name:"Compare outcomes."}).waitFor();
      assert.match(await app.locator("body").innerText(), /\+0\.0375/);
      assert.equal(await app.locator("body").evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await app.locator("body").evaluate((element, url) => { location.href = new URL("evaluation/index.html", url).href; }, appUrl);
      await app.getByRole("heading", {name:"support-routing", exact:true}).waitFor();
      await app.locator("details").last().locator("summary").click();
      assert.match(await app.locator("details").last().innerText(), /retry-after-commit/);
      assert.match(await app.locator("details").last().innerText(), /temporarily_unavailable/);
      assert.equal(await app.locator("body").evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await app.locator("body").evaluate((element, url) => { location.href = new URL("repeat/faulty/index.html", url).href; }, appUrl);
      await app.getByRole("heading", {name:"See every attempt."}).waitFor();
      const attemptLink = app.locator('a[href="attempts/0001/index.html"]');
      await attemptLink.click();
      await app.getByRole("heading", {name:"support-routing", exact:true}).waitFor();
      assert.match(await app.locator("body").innerText(), /retry-after-commit/);
      assert.equal(await app.locator("body").evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await app.locator("body").evaluate((element, url) => { location.href = new URL("suite/index.html", url).href; }, appUrl);
      await app.getByRole("heading", {name:"Every job, explicit criteria."}).waitFor();
      assert.match(await app.locator("body").innerText(), /Gate accepted with unresolved task outcomes/);
      assert.equal(await app.locator("body").evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      for (const name of ["partial", "protected"]) {
        await app.locator("body").evaluate((element, url) => { location.href = url; }, new URL(`suite/jobs/support-${name}/index.html`, appUrl).href);
        await app.getByRole("heading", {name:"See every attempt."}).waitFor();
        await app.locator('a[href="attempts/0001/index.html"]').click();
        await app.getByRole("heading", {name:"support-routing", exact:true}).waitFor();
        assert.match(await app.locator("body").innerText(), /retry-after-commit/);
      }
      assert.deepEqual(errors, []);
      results.push({width, controls:17, cases:167, comparedCases:3, repeatedControls:2, attempts:6, suiteJobs:3, suiteAttempts:5, junitFailures:1, offlineReports:7, errors});
      await page.close();
    }
    console.log(JSON.stringify({url:base, checks:results}, null, 2));
  } finally {
    await browser.close();
    if (server) server.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
