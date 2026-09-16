const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

// Shared by local browser checks and the actual public Hub iframe check.
async function checkStrands(page, app, root, { downloads = true } = {}) {
  await app.locator("#filter-status").filter({ hasText: "1 of 8 checks shown" }).waitFor();
  assert.equal(await app.locator("#baseline-mean").innerText(), "75%");
  assert.equal(await app.locator("#current-mean").innerText(), "87.5%");
  assert.equal(await app.locator(".check:visible").count(), 1);
  const regression = app.locator('.check[data-change="regression"]');
  assert.match(await regression.innerText(), /retry-after-commit@17/);
  const states = await regression.locator(".states pre").allTextContents();
  const [expected, baseline, current] = states.map(text => JSON.parse(text));
  assert.deepEqual(baseline, expected);
  assert.equal(current.length, expected.length + 1);
  assert.equal(current.at(-1), current.at(-2));
  const summary = regression.locator("summary");
  await summary.focus();
  await summary.press("Enter");
  assert.equal(await regression.getAttribute("open"), null);
  await summary.press("Enter");
  assert.notEqual(await regression.getAttribute("open"), null);
  await app.getByRole("button", { name: "Improvements (2)", exact: true }).click();
  assert.equal(await app.locator(".check:visible").count(), 2);
  for (const check of await app.locator(".check:visible").all()) {
    assert.match(await check.innerText(), /ticket.status/);
  }
  await app.getByRole("button", { name: "All checks (8)", exact: true }).click();
  assert.equal(await app.locator(".check:visible").count(), 8);
  const unchanged = app.locator('.check[data-change="unchanged"]').first();
  await unchanged.locator("summary").click();
  const hash = await unchanged.getByRole("link", { name: "Link to this check" }).getAttribute("href");
  await app.locator("body").evaluate((element, hash) => { location.hash = hash; }, hash);
  await unchanged.locator("summary:focus").waitFor();
  await app.locator("body").evaluate(() => { location.hash = "#unknown-native-check"; });
  await app.locator("#filter-status").filter({ hasText: "does not identify a check" }).waitFor();
  assert.equal(await app.locator(".check:visible").count(), 8);
  await app.getByRole("button", { name: "Regressions (1)", exact: true }).click();
  assert.equal(await app.locator(".check:visible").count(), 1);
  assert(await app.locator("body").evaluate(() =>
    document.documentElement.scrollWidth <= innerWidth + 1), "Strands review must fit its viewport");
  if (downloads) {
    for (const [name, file] of [
      ["Download Strands review (ZIP)", "strands-review.zip"],
      ["Native current JSON", "strands/current-native.json"],
    ]) {
      const link = app.getByRole("link", { name, exact: true });
      assert.match(await link.getAttribute("href"), /\?download=true$/);
      const pending = page.waitForEvent("download", { timeout: 30000 });
      await link.click();
      const received = await pending;
      assert.equal(await received.failure(), null);
      assert.deepEqual(fs.readFileSync(await received.path()), fs.readFileSync(path.join(root, file)));
    }
  }
  return { nativeStateReview: true, allChecks: 8, keyboard: true, checkLinks: true, downloads };
}

module.exports = { checkStrands };
