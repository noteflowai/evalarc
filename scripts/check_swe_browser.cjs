const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

async function checkSWE(page, app, root, { downloads = false } = {}) {
  await app.locator("#result-count").filter({ hasText: "36 of 36 scheduled attempts" }).waitFor();
  assert.equal(await app.locator("#metrics .metric strong").allTextContents() + "", "0,31,5,8");
  assert.equal(await app.locator("#attempt-rows tr").count(), 36);
  await app.locator("#outcome").selectOption("unavailable");
  assert.equal(await app.locator("#attempt-rows tr").count(), 5);
  await app.locator("#attempt-rows button").first().click();
  await app.locator("#detail-status .unavailable").waitFor();
  assert.match(await app.locator("#native").innerText(), /"infra_failure": true/);
  assert.match(await app.locator("#native").innerText(), /network_unreachable/);
  await app.locator("#close").click();
  await app.locator("#outcome").selectOption("accepted");
  assert.equal(await app.locator("#attempt-rows tr").count(), 0);
  assert(await app.locator("#empty").isVisible());
  await app.locator("#outcome").selectOption("");
  await app.locator("#project").selectOption("pytest-dev/pytest");
  await app.locator("#condition").selectOption("none");
  assert.equal(await app.locator("#attempt-rows tr").count(), 3);
  await app.getByRole("button", { name: /^Inspect attempt 15,/ }).click();
  await app.locator("#detail-status .not_accepted").waitFor();
  assert.match(await app.locator("#detail-method").innerText(), /Usage is incomplete/);
  assert(await app.locator("#timeline > li").count() > 0);
  assert(await app.locator("body").evaluate(() =>
    document.documentElement.scrollWidth <= innerWidth + 1));
  assert.equal(await app.locator("#control-rows tr").count(), 6);
  if (downloads) {
    const pending = page.waitForEvent("download", { timeout: 60000 });
    await app.locator("#zip-link").click();
    const received = await pending;
    assert.equal(await received.failure(), null);
    assert.deepEqual(fs.readFileSync(await received.path()),
      fs.readFileSync(path.join(root, "independent-swe/independent-swe.zip")));
  }
  return { independentSWE: true, attempts: 36, uncertain: 5, filters: true,
    incompleteUsageVisible: true, nativeReportsVisible: true, downloadMatched: downloads };
}

module.exports = { checkSWE };
