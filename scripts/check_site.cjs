const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { once } = require("node:events");
const { checkStrands } = require("./check_strands_browser.cjs");
const { checkContextControls } = require("./check_context_browser.cjs");
const { checkHandoff } = require("./check_handoff_browser.cjs");
const { checkBehavior } = require("./check_behavior_browser.cjs");
const { checkSWE } = require("./check_swe_browser.cjs");

const { checkAIWalkthrough } = require("./check_ai_walkthrough.cjs");

async function main() {
  const root = path.resolve(process.env.SITE_DIR || "dist/site");
  let server;
  let base = process.env.SITE_URL;
  if (!base) {
    const mime = {".html":"text/html", ".js":"text/javascript", ".json":"application/json", ".css":"text/css", ".svg":"image/svg+xml", ".zip":"application/zip", ".png":"image/png", ".gif":"image/gif", ".mp4":"video/mp4", ".vtt":"text/vtt"};
    server = http.createServer((req, res) => {
      const route = decodeURIComponent(new URL(req.url, "http://localhost").pathname);
      // HF static hosting does not resolve subdirectory indexes. Keep that
      // production constraint in the local browser fixture.
      if (route !== "/" && route.endsWith("/")) {
        res.writeHead(404).end(); return;
      }
      const filename = path.resolve(root, "." + (route === "/" ? "/index.html" : route));
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
    for (const width of [1440, 390, 320]) {
      const page = await browser.newPage({viewport:{width, height:1000}});
      await page.emulateMedia({reducedMotion:"reduce"});
      await page.addInitScript(() => {
        Object.defineProperty(navigator, "clipboard", {configurable:true, value:{writeText:async () => { throw new Error("Clipboard denied"); }}});
      });
      const errors = [], requests = [];
      page.on("request", request => requests.push(request.url()));
      page.on("pageerror", error => errors.push(error.message));
      await page.goto(base, {waitUntil:"networkidle", timeout:60000});
      const app = process.env.SITE_HUB === "1" ? page.frameLocator('iframe[src*="hf.space"]') : page;
      await app.locator("#workspace").waitFor({state:"visible"});
      await app.locator('[data-model-seed="29"]').click();
      assert.equal(await app.locator('[data-model-seed="29"]').getAttribute("aria-pressed"), "true");
      assert.match(await app.locator("#proof-open").getAttribute("href"), /case=already-closed&seed=29$/);
      assert.equal((await app.locator("#proof-after").innerText()).trim(), "{}");
      const imageDownload = page.waitForEvent("download");
      await app.locator("#proof-image").click();
      const imageBytes = fs.readFileSync(await (await imageDownload).path());
      assert.equal(imageBytes.readUInt32BE(16), 1200);
      assert.equal(imageBytes.readUInt32BE(20), 630);
      assert(imageBytes.length > 15000, "The result image must contain a rendered comparison");
      await checkAIWalkthrough(app, requests);
      await app.locator("#comparison-workspace").waitFor({state:"visible"});
      await app.locator("#repeat-workspace").waitFor({state:"visible"});
      await app.locator("#suite-workspace").waitFor({state:"visible"});
      await app.getByRole("link", {name:"Find the regression", exact:false}).click();
      assert.equal(await app.locator("body").evaluate(() => location.hash), "#regression");
      const comparisonHeading = await app.locator("#regression h2").boundingBox();
      assert(comparisonHeading && comparisonHeading.y >= 0 && comparisonHeading.y < 1000,
        "The scripted retry entry must expose the recorded regression");
      if (width === 1440) {
        await app.locator(".tour summary").click();
        const video = app.getByLabel("Recorded regression walkthrough");
        assert.equal(await video.getAttribute("autoplay"), null);
        assert.equal(await video.getAttribute("preload"), "none");
        const playback = await video.evaluate(async element => {
          await element.play();
          await new Promise((resolve, reject) => {
            const timer = setTimeout(() => reject(new Error("Walkthrough playback stalled")), 15000);
            element.addEventListener("timeupdate", () => {clearTimeout(timer);resolve()}, {once:true});
          });
          element.pause();
          return {duration:element.duration,time:element.currentTime,width:element.videoWidth};
        });
        assert(Math.abs(playback.duration - 30) < 0.2 && playback.time > 0 && playback.width > 0,
          "The walkthrough must decode and play, not just show its poster");
        await app.locator(".tour summary").click();
      }
      assert.equal(await app.locator(".coverage-card").count(),3);
      assert.equal(await app.locator(".coverage-card li").count(),6);
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
      const downloadLink = app.getByRole("link", {name:"Download suite evidence (ZIP)"});
      assert.equal(await downloadLink.getAttribute("href"), "suite-evidence.zip?download=true");
      const received = page.waitForEvent("download");
      await downloadLink.click();
      const download = await received;
      assert.equal(await download.failure(), null);
      assert.equal(download.suggestedFilename(), "suite-evidence.zip");
      const downloaded = fs.readFileSync(await download.path());
      const manifest = await (await page.request.get(new URL("manifest.json", suiteBase).href)).json();
      assert.equal(require("node:crypto").createHash("sha256").update(downloaded).digest("hex"), manifest.files["suite-evidence.zip"]);
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
      const detailBounds = await app.locator("#case-detail").boundingBox();
      const traceBounds = await app.locator("#trace-action").boundingBox();
      assert(traceBounds.x + traceBounds.width <= detailBounds.x + detailBounds.width, "Trace panel must scroll within its card");
      assert.equal(await app.locator("#trace-step").getAttribute("aria-valuetext"), "Step 4 of 6");
      await app.locator("#share-case").click();
      const shared = await app.locator("#share-url").inputValue();
      const sharedParams = new URLSearchParams(new URL(shared).hash.slice(1));
      assert.equal(sharedParams.get("v"), "2");
      assert.equal(sharedParams.get("audit"), manifest.files["support/audit.json"]);
      assert.equal(sharedParams.get("case"), "retry-after-commit");
      assert.equal(sharedParams.get("step"), "3");
      assert.equal(await app.locator("body").evaluate(() => document.activeElement.id), "share-url");
      await app.locator("body").evaluate(() => location.reload());
      await app.locator("#share-status").filter({hasText:"Shared evidence restored"}).waitFor();
      assert.equal(await app.locator("#trace-step").inputValue(), "3");
      assert.deepEqual(JSON.parse(await app.locator("#trace-changes").innerText()), faulty);
      assert.equal(await app.locator("body").evaluate(() => document.activeElement.id), "case-title");
      await app.locator("#back-to-cases").click();
      assert.equal(await app.locator("body").evaluate(() => document.activeElement.getAttribute("aria-pressed")), "true");
      await app.locator("body").evaluate(() => { location.hash = "v=1&pack=support&control=missing&case=missing&seed=NaN&step=99999"; });
      await app.locator("#share-status").filter({hasText:"Some link values were outside"}).waitFor();
      assert(await app.locator("#next-step").isDisabled());
      await app.locator("body").evaluate(() => history.back());
      await app.locator("#share-status").filter({hasText:"Shared evidence restored"}).waitFor();
      assert.equal(await app.locator("#trace-step").inputValue(), "3");
      await app.locator('nav[aria-label="Evidence sections"] a[href="#suite"]').click();
      assert.equal(await app.locator("#trace-step").inputValue(), "3");
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
      await app.locator("#share-case").click();
      assert.equal(new URLSearchParams(new URL(await app.locator("#share-url").inputValue()).hash.slice(1)).get("step"), "0");
      for (const task of ["support", "coding"]) {
        await app.locator(`#${task}-task`).click();
        const values = await app.locator("#control option").evaluateAll(options => options.map(o => o.value));
        for (const value of values) {
          await app.locator("#control").selectOption(value);
          assert.equal(await app.locator("#verdict").innerText(), value === "reference" ? "FULLY RESOLVED" : "NOT RESOLVED");
          for (let i=0; i<await app.locator("#cases button").count();i++) {
            await app.locator("#cases button").nth(i).click();
            assert.ok((await app.locator("#case-title").innerText()).includes("seed 17"));
            assert.equal(await app.locator("body").evaluate(() => document.activeElement.id), "case-title");
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
      await app.locator("body").evaluate((element, url) => { location.href = new URL("skill-impact/index.html", url).href; }, appUrl);
      await app.locator("#workspace").waitFor({state:"visible"});
      assert.equal(await app.locator(".trial").count(), 9);
      assert.match(await app.locator("#profile-totals").innerText(), /2\/9 fully resolved/);
      await app.getByRole("button", {name:"No skill, seed 41, 100.0 percent, resolved", exact:true}).click();
      assert.match(await app.locator("#metrics").innerText(), /100.0%/);
      const skillShared = await app.locator("body").evaluate(() => location.href);
      await app.locator("body").evaluate((element, url) => { location.href = url; location.reload(); }, skillShared);
      await app.locator("#workspace").waitFor({state:"visible"});
      assert.equal(await app.locator("#trial-title").innerText(), "No skill · seed 41");
      for (const profile of ["skill-impact-matched","skill-impact-contract-inline","skill-impact-catalog-fallback"]) {
        await app.locator("#profile").selectOption(profile);
        assert.equal(await app.locator(".trial").count(),9);
        const href = await app.locator("#downloads a").filter({hasText:"Independent grade"}).getAttribute("href");
        const grade = await app.locator("body").evaluate(async (element, url) => (await fetch(url)).json(), href);
        assert.equal(grade.valid,true);
      }
      assert.equal(await app.locator("body").evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      if (width === 1440 && process.env.RESEARCH_SCREENSHOTS) {
        fs.mkdirSync(process.env.RESEARCH_SCREENSHOTS,{recursive:true});
        await page.screenshot({path:path.join(process.env.RESEARCH_SCREENSHOTS,"skill-impact.png"),fullPage:true});
      }
      await app.locator("body").evaluate((element, url) => { location.href = new URL("research/index.html", url).href; }, appUrl);
      await app.getByRole("heading",{name:"Skill composition: 12 attempts, 3 accepted"}).waitFor();
      assert.equal(await app.locator("tbody tr").count(),18);
      assert.equal(await app.locator("body").evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await app.getByRole("link",{name:"27-trial Skill Impact Lab"}).click();
      await app.locator("#profile").waitFor();
      await app.getByRole("link",{name:"Playground"}).click();
      await app.locator("#workspace").waitFor({state:"visible"});
      const coveragePage = await browser.newPage({viewport:{width,height:1000}});
      try {
        await coveragePage.goto(new URL("robot/index.html#fault-3", suiteBase).href);
        await coveragePage.locator("#fault-3").waitFor({state:"visible"});
        assert.match(await coveragePage.locator("#fault-3").innerText(), /incomplete-recording/);
        assert.equal(await coveragePage.locator(".audit-control").count(),6);
        assert(await coveragePage.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
        await coveragePage.locator("#fault-3 details summary").first().click();
        assert.match(await coveragePage.locator("#fault-3 pre").first().innerText(), /"completeness": false/);
      } finally { await coveragePage.close(); }
      assert.deepEqual(errors, []);
      results.push({width, controls:17, cases:167, comparedCases:3, repeatedControls:2, attempts:6, suiteJobs:3, suiteAttempts:5, junitFailures:1, offlineReports:7, suiteDownloadVerified:true, sharedTraceRestored:true, keyboardCaseReturn:true, realModelTrials:27, supplementaryTrials:18, errors});
      await page.close();
    }
    if (!process.env.SITE_URL) {
      const page = await browser.newPage({viewport:{width:390,height:1000}, reducedMotion:"reduce"});
      const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      const failures = new Set(["suite/suite.json", "repeat/faulty/repetition.json", "comparison/current.json", "coding/audit.json"]);
      await page.route("**/*.json", route => {
        const url = new URL(route.request().url());
        return [...failures].some(file => url.pathname.endsWith("/" + file)) ? route.abort() : route.continue();
      });
      await page.goto(base + "#v=1&pack=coding&control=boolean-equals-one&case=cas-type-sensitivity&seed=17&step=0");
      for (const name of ["suite", "repeat", "comparison", "audit"]) {
        await page.locator("#" + name + "-recovery").waitFor({state:"visible"});
        assert(await page.locator("#" + name + "-retry").isEnabled());
      }
      assert(await page.locator("#workspace").isVisible());
      assert.equal(await page.locator("#score").innerText(), "93.75%");
      assert(await page.locator("#coding-task").isDisabled());
      assert.match(await page.locator("#share-status").innerText(), /linked coding evidence is unavailable/);
      failures.clear();
      for (const name of ["suite", "repeat", "comparison", "audit"]) {
        await page.locator("#" + name + "-retry").click();
        await page.locator("#" + name + "-recovery").waitFor({state:"hidden"});
      }
      assert(await page.locator("#coding-task").isEnabled());
      assert.equal(await page.locator("#score").innerText(), "92.5%");
      assert.equal(await page.locator("#changed-cases button").count(), 3);
      assert.equal(await page.locator("#repeat-attempts a").count(), 3);
      assert.equal(await page.locator("#cases button").count(), 15);
      assert.match(await page.locator("#share-status").innerText(), /Legacy link.*original audit identity was not recorded/);
      assert.equal(await page.locator("body").evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      assert.deepEqual(errors, []);
      failures.add("skill-impact/lab.json");
      await page.goto(new URL("skill-impact/index.html",base).href);
      await page.locator("#retry").waitFor({state:"visible"});
      failures.clear();
      await page.locator("#retry").click();
      await page.locator("#workspace").waitFor({state:"visible"});
      assert.equal(await page.locator(".trial").count(),9);
      results.push({independentSectionRetry:true, partialTaskPack:true, pendingLinkRestored:true, researchRetry:true, errors});
      await page.close();
      const identityPage = await browser.newPage({viewport:{width:390,height:1000}});
      try {
        const auditBytes = fs.readFileSync(path.join(root, "support/audit.json"));
        const digest = require("node:crypto").createHash("sha256").update(auditBytes).digest("hex");
        const link = base + `#v=2&audit=${digest}&pack=support&control=new-key-on-retry&case=retry-after-commit&seed=17&step=3`;
        await identityPage.goto(link);
        await identityPage.locator("#share-status").filter({hasText:"Shared evidence restored"}).waitFor();
        assert.equal(await identityPage.locator("#trace-step").inputValue(), "3");
        const changed = JSON.parse(auditBytes);
        changed.reference.created_at = "2026-09-15T00:00:00+00:00";
        const changedBytes = Buffer.from(JSON.stringify(changed) + "\n");
        const changedDigest = require("node:crypto").createHash("sha256").update(changedBytes).digest("hex");
        assert.notEqual(changedDigest, digest);
        // Same task, controls, cases and step coordinates, but different saved
        // audit bytes. The manifest deliberately stays old, as in a mixed deploy.
        await identityPage.route("**/support/audit.json", route =>
          route.fulfill({status:200, contentType:"application/json", body:changedBytes}));
        await identityPage.reload();
        await identityPage.locator("#share-status").filter({hasText:"Evidence changed"}).waitFor();
        assert.equal(await identityPage.locator("#trace-step").inputValue(), "0");
        assert.match(await identityPage.locator("#share-status").innerText(), /linked view was not restored/);
        assert.equal(JSON.parse(await identityPage.locator("#provenance").textContent()).audit_sha256, changedDigest);
        await identityPage.locator("#next-step").click();
        const fresh = identityPage.url();
        assert.equal(new URLSearchParams(new URL(fresh).hash.slice(1)).get("audit"), changedDigest);
        await identityPage.reload();
        await identityPage.locator("#share-status").filter({hasText:"Shared evidence restored"}).waitFor();
        assert.equal(await identityPage.locator("#trace-step").inputValue(), "1");
        await identityPage.evaluate(hash => { location.hash = hash; },
          new URL(fresh).hash + "&audit=" + digest);
        await identityPage.locator("#share-status").filter({hasText:"not supported"}).waitFor();
        assert.equal(await identityPage.locator("#trace-step").inputValue(), "1");
        await identityPage.goto(base + "#v=1&pack=support&control=new-key-on-retry&case=retry-after-commit&seed=17&step=3");
        await identityPage.locator("#share-status").filter({hasText:"Legacy link"}).waitFor();
        assert.equal(await identityPage.locator("#trace-step").inputValue(), "3");
        await identityPage.addInitScript(() => {
          Object.defineProperty(crypto, "subtle", {value:undefined, configurable:true});
        });
        await identityPage.goto(link);
        await identityPage.reload();
        await identityPage.locator("#workspace").waitFor({state:"visible"});
        assert(await identityPage.locator("#share-case").isDisabled());
        assert.match(await identityPage.locator("#audit-identity").innerText(), /fingerprint unavailable/);
        assert.match(await identityPage.locator("#share-status").innerText(), /linked view was not restored/);
        assert(await identityPage.locator("#suite-workspace").isVisible());
        results.push({auditByteIdentity:true, changedAuditRejected:true, freshLinkRestored:true,
          duplicateHashRejected:true, legacyLinkDisclosed:true, missingCryptoRecovery:true});
      } finally { await identityPage.close(); }
    }
    if (process.env.SITE_HUB !== "1") {
      for (const width of [1440, 390, 320]) {
        const page = await browser.newPage({viewport:{width,height:1000}});
        const errors = [];
        page.on("pageerror", error => errors.push(error.message));
        try {
          await page.goto(base);
          await page.getByRole("link",{name:"Explore five authored review controls"}).click();
          await page.locator("#filter-status").filter({hasText:"5 cases shown"}).waitFor();
          assert.equal(await page.locator("article[data-gate=accepted]").count(),1);
          assert.equal(await page.locator("article[data-gate=rejected]").count(),2);
          assert.equal(await page.locator("article[data-gate=incomplete]").count(),2);
          assert.equal(await page.locator("#case-1 tbody tr").first().locator("td").nth(1).innerText(),"0");
          assert.match(await page.locator("#case-2").innerText(),/SKIPPED/);
          assert.match(await page.locator("#case-3").innerText(),/MISSING/);
          assert.match(await page.locator("#case-4").innerText(),/NOT CALLED/);
          await page.getByRole("button",{name:"Incomplete",exact:true}).click();
          assert.equal(await page.locator("article:visible").count(),2);
          await page.locator("#search").fill("unavailable context");
          assert.equal(await page.locator("article:visible").count(),1);
          await page.locator("#search").fill("nothing matches this phrase");
          assert.equal(await page.locator("#filter-status").innerText(),"0 cases shown");
          await page.locator("#search").fill("");
          await page.getByRole("button",{name:"All",exact:true}).click();
          assert.equal(await page.locator("article:visible").count(),5);
          assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
            `Trace review must fit viewport ${width}`);
          const pending = page.waitForEvent("download");
          await page.getByRole("link",{name:"Download original input",exact:true}).click();
          const download = await pending;
          assert.equal(await download.failure(),null);
          const original = fs.readFileSync(path.join(root,"trace-workbench/input.json"));
          assert.deepEqual(fs.readFileSync(await download.path()),original);
          await page.goto(base);
          await page.getByRole("link",{name:"Inspect an actual MCP delivery"}).click();
          await page.locator("#filter-status").filter({hasText:"1 cases shown"}).waitFor();
          assert.match(await page.locator("body").innerText(),/Actual local stdio MCP/);
          assert.match(await page.locator("article").innerText(),/MATCHED/);
          assert.equal(await page.locator("article[data-gate=incomplete]").count(),1);
          assert.equal(await page.locator("article .badge").filter({hasText:"MISSING"}).count(),2);
          await page.goto(base);
          await page.getByRole("link",{name:"Inspect repeated judge decisions"}).click();
          await page.locator("#filter-status").filter({hasText:"5 targets shown"}).waitFor();
          assert.match(await page.locator("#target-1").innerText(), /0 pass · 3 reject/);
          assert.match(await page.locator("#target-2").innerText(), /Both pass and reject observed/);
          assert.match(await page.locator("#target-3").innerText(), /Score variation: yes/);
          assert.match(await page.locator("#target-3").innerText(), /Same observed gate/);
          assert.match(await page.locator("#target-4").innerText(), /1\/3 expected judgments assessed/);
          assert.match(await page.locator("#target-4").innerText(), /SKIPPED/);
          assert.match(await page.locator("#target-4").innerText(), /MISSING/);
          await page.getByRole("button",{name:"Gate disagreement",exact:true}).click();
          assert.equal(await page.locator("article:visible").count(),1);
          assert(await page.locator("#target-2").isVisible());
          await page.getByRole("button",{name:"Incomplete",exact:true}).click();
          assert(await page.locator("#target-4").isVisible());
          await page.locator("#search").fill("no matching judge target");
          assert.equal(await page.locator("#filter-status").innerText(),"0 targets shown");
          await page.locator("#search").fill("");
          await page.getByRole("button",{name:"All",exact:true}).click();
          assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
            `Judge stability must fit viewport ${width}`);
          const judgePending = page.waitForEvent("download");
          await page.locator("#target-0 a").first().click();
          const judgeDownload = await judgePending;
          assert.equal(await judgeDownload.failure(),null);
          assert.deepEqual(fs.readFileSync(await judgeDownload.path()),
            fs.readFileSync(path.join(root,"judge-stability/inputs/0001.json")));
          assert.deepEqual(errors,[]);
          results.push({traceWorkbench:true,width,zeroSkippedMissingDistinct:true,
            filtersAndEmptyState:true,originalBytesDownload:true,actualMcpUnassessed:true,
            judgeStability:true,scoreAndGateVariationDistinct:true,judgeOriginalDownload:true});
        } finally { await page.close(); }
      }
      if (!process.env.SITE_URL) {
        const page = await browser.newPage({viewport:{width:390,height:1000}});
        try {
          await page.route("http**/*", route => route.abort());
          await page.goto(require("node:url").pathToFileURL(
            path.join(root,"judge-stability/index.html")).href);
          await page.getByRole("button",{name:"Same gate",exact:true}).click();
          assert.equal(await page.locator("article:visible").count(),3);
          assert.match(await page.locator("#target-1").innerText(), /0 pass · 3 reject/);
          results.push({offlineJudgeReport:true,allRejectAgreementDisclosed:true});
        } finally { await page.close(); }
      }
    }
    if (process.env.SITE_HUB !== "1") {
      for (const width of [1440, 390, 320]) {
        const page = await browser.newPage({ viewport: { width, height: 1000 } });
        const errors = [];
        page.on("pageerror", error => errors.push(error.message));
        try {
          await page.goto(base);
          await page.getByRole("link", { name: "Inspect the Strands state review" }).click();
          results.push({ width, ...await checkStrands(page, page, root) });
          if (process.env.SITE_SCREENSHOTS) {
            await page.locator(".intro").screenshot({
              path: path.join(process.env.SITE_SCREENSHOTS, `strands-overview-${width}.png`)
            });
            await page.locator("#checks").screenshot({
              path: path.join(process.env.SITE_SCREENSHOTS, `strands-checks-${width}.png`)
            });
          }
          assert.deepEqual(errors, []);
        } finally { await page.close(); }
      }
      if (!process.env.SITE_URL) {
        for (const javaScriptEnabled of [true, false]) {
          const page = await browser.newPage({
            viewport: { width: 390, height: 1000 }, javaScriptEnabled
          });
          const network = [];
          page.on("request", request => {
            if (/^https?:/.test(request.url())) network.push(request.url());
          });
          await page.route("http**/*", route => route.abort());
          try {
            await page.goto(require("node:url").pathToFileURL(path.join(root, "strands/index.html")).href);
            if (javaScriptEnabled) {
              await checkStrands(page, page, root, { downloads: false });
              assert(await page.locator("#archive-link").isHidden());
            } else {
              assert.equal(await page.locator(".check:visible").count(), 8);
              const unchanged = page.locator('.check[data-change="unchanged"]').first();
              await unchanged.locator("summary").click();
              assert(await unchanged.locator(".states").isVisible());
            }
            assert.deepEqual(network, [], "Offline state review must not request the network");
            results.push({ offlineStrandsReview: true, javaScriptEnabled, networkRequests: 0 });
          } finally { await page.close(); }
        }
      }
    }
    if (process.env.SITE_HUB !== "1") {
      for (const width of [1440, 390, 320]) {
        const page = await browser.newPage({ viewport: { width, height: 1000 } });
        try {
          if (!process.env.SITE_URL) {
            await page.route("**/context-controls/protocol/index.html", async route => {
              // Expose stale-page assertions even on a fast local server.
              await new Promise(resolve => setTimeout(resolve, 400));
              await route.continue();
            });
          }
          await page.goto(base);
          await page.getByRole("link", { name: "Inspect both context-control cohorts" }).click();
          results.push({ width, ...await checkContextControls(page, page, root) });
        } finally { await page.close(); }
      }
      if (!process.env.SITE_URL) {
        const page = await browser.newPage({ viewport: { width: 390, height: 1000 }, javaScriptEnabled: false });
        const network = [];
        page.on("request", request => { if (/^https?:/.test(request.url())) network.push(request.url()); });
        await page.route("http**/*", route => route.abort());
        try {
          await page.goto(require("node:url").pathToFileURL(path.join(root, "context-controls/index.html")).href);
          results.push({ offlineContextControls: true,
            ...await checkContextControls(page, page, root, { downloads: false }) });
          assert.deepEqual(network, []);
        } finally { await page.close(); }
      }
    }
    if (process.env.SITE_HUB !== "1") {
      for (const skillHandoff of [false, true]) {
        const folder = skillHandoff ? "skill-handoff" : "funes-handoff";
        for (const width of [1440, 390, 320]) {
          const page = await browser.newPage({ viewport: { width, height: 1000 } });
          const errors = [];
          page.on("pageerror", error => errors.push(error.message));
          try {
            await page.goto(base);
            const link = page.getByRole("link", { name: skillHandoff
              ? "Inspect the pinned skill handoff" : "Inspect the Funes MCP handoff" });
            if (skillHandoff) {
              await page.locator('section[aria-label="Funes MCP handoff"] details > summary').focus();
              await page.keyboard.press("Enter");
            }
            await link.click();
            results.push({ width, ...await checkHandoff(page, page, root, { skillHandoff }) });
            if (process.env.SITE_SCREENSHOTS) {
              await page.goto(new URL(`${folder}/index.html`, base).href);
              await page.screenshot({ path: path.join(process.env.SITE_SCREENSHOTS, `${folder}-${width}.png`), fullPage: true });
            }
            assert.deepEqual(errors, []);
          } finally { await page.close(); }
        }
        if (!process.env.SITE_URL) {
          for (const javaScriptEnabled of [true, false]) {
            const page = await browser.newPage({ viewport: { width: 390, height: 1000 }, javaScriptEnabled });
            const requests = [];
            page.on("request", request => {
              if (/^https?:/.test(request.url())) requests.push(request.url());
            });
            await page.route("http**/*", route => route.abort());
            try {
              await page.goto(require("node:url").pathToFileURL(path.join(root, folder, "index.html")).href);
              results.push({ offlineHandoff: true, ...await checkHandoff(page, page, root, {
                downloads: false, interactive: javaScriptEnabled, skillHandoff
              }) });
              assert.deepEqual(requests, [], "Offline handoff review must not request the network");
            } finally { await page.close(); }
          }
        }
      }
    }
    if (process.env.SITE_HUB !== "1") {
      for (const width of [1440, 390, 320]) {
        const page = await browser.newPage({ viewport: { width, height: 1000 } });
        try {
          await page.goto(new URL("behavior-audit/index.html", base).href);
          results.push({ width, ...await checkBehavior(page, page) });
        } finally { await page.close(); }
      }
      if (!process.env.SITE_URL) {
        for (const javaScriptEnabled of [true, false]) {
          const page = await browser.newPage({
            viewport: { width: 390, height: 1000 }, javaScriptEnabled
          });
          const requests = [];
          page.on("request", request => {
            if (/^https?:/.test(request.url())) requests.push(request.url());
          });
          await page.route("http**/*", route => route.abort());
          try {
            await page.goto(require("node:url").pathToFileURL(
              path.join(root, "behavior-audit/index.html")).href);
            results.push({ offlineBehavior: true, ...await checkBehavior(page, page, {
              interactive: javaScriptEnabled
            }) });
            assert.deepEqual(requests, [], "Offline behavior review requested the network");
          } finally { await page.close(); }
        }
      }
    }
    if (process.env.SITE_HUB !== "1") {
      for (const width of [1440, 390, 320]) {
        const page = await browser.newPage({ viewport: { width, height: 1000 } });
        try {
          await page.goto(new URL("independent-swe/index.html", base).href);
          results.push({ width, ...await checkSWE(page, page, root, { downloads: true }) });
        } finally { await page.close(); }
      }
      if (!process.env.SITE_URL) {
        const temporary = fs.mkdtempSync(path.join(require("node:os").tmpdir(), "evalarc-swe-"));
        try {
          require("node:child_process").execFileSync("python3", ["-c",
            "import sys,zipfile;zipfile.ZipFile(sys.argv[1]).extract('review/index.html',sys.argv[2])",
            path.join(root, "independent-swe/independent-swe.zip"), temporary]);
          const page = await browser.newPage({ viewport: { width: 390, height: 1000 } });
          const network = [];
          page.on("request", request => {
            if (/^https?:/.test(request.url())) network.push(request.url());
          });
          await page.route("http**/*", route => route.abort());
          try {
            await page.goto(require("node:url").pathToFileURL(
              path.join(temporary, "review/index.html")).href);
            results.push({ offlineSWE: true, ...await checkSWE(page, page, root) });
            assert.deepEqual(network, [], "Offline SWE review requested the network");
          } finally { await page.close(); }
        } finally { fs.rmSync(temporary, { recursive: true, force: true }); }
      }
    }
    console.log(JSON.stringify({url:base, checks:results}, null, 2));
  } finally {
    await browser.close();
    if (server) server.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
