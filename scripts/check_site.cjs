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
      await page.waitForLoadState("networkidle");
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
      }
      assert.deepEqual(errors, []);
      results.push({width, controls:17, cases:167, errors});
      await page.close();
    }
    console.log(JSON.stringify({url:base, checks:results}, null, 2));
  } finally {
    await browser.close();
    if (server) server.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
