// Check the displayed cohorts against records and exercise their actual downloads.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

async function checkContextControls(page, app, root, { downloads = true } = {}) {
  const folder = path.join(root, "context-controls");
  const summary = JSON.parse(fs.readFileSync(path.join(folder, "cohorts.json")));
  await app.getByRole("heading", { name: "Check the protocol before interpreting the score." }).waitFor();
  const base = await app.locator("body").evaluate(() => location.href);
  assert.equal(await app.locator("section.card").count(), 2);
  assert.equal(summary.outcomes_are_pooled, false);
  for (let i = 0; i < 2; i++) {
    const card = app.locator("section.card").nth(i);
    const expected = summary.cohorts[i];
    assert.match(await card.innerText(), new RegExp(`${expected.resolved} / ${expected.trials} tasks resolved`));
    assert.equal(await card.locator("tbody a").count(), 6);
    const cohort = JSON.parse(fs.readFileSync(path.join(folder, expected.id, "summary.json")));
    for (const row of cohort.trials) {
      const cell = card.locator(`a[href="${expected.id}/${row.path}/evaluation.json"]`);
      assert.equal(await cell.innerText(), (row.evaluation.score * 100).toFixed(1) + "%");
      assert.match(await cell.locator("..").innerText(), /unresolved/);
    }
  }
  assert(await app.locator("body").evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  if (downloads) {
    const pending = page.waitForEvent("download");
    await app.getByRole("link", { name: "Complete offline evidence", exact: true }).click();
    const downloaded = await pending;
    assert.equal(await downloaded.failure(), null);
    assert.deepEqual(fs.readFileSync(await downloaded.path()), fs.readFileSync(path.join(folder, "experiment.zip")));
  }
  for (const name of ["initial", "protocol"]) {
    await app.locator("body").evaluate((element, url) => { location.href = url; },
      new URL(`${name}/index.html`, base).href);
    // Both pages share their heading. Wait for the requested cohort before
    // interacting, including when an embedded frame is still showing the old one.
    await app.getByText(name === "initial" ? /^Initial cohort:/ : /^Follow-up:/).waitFor();
    await app.getByRole("heading", { name: "Same length. Different guidance." }).waitFor();
    await app.locator("article").first().waitFor();
    assert.equal(await app.locator("article").count(), 6);
    const cards = app.locator("article");
    for (let i = 0; i < 6; i++) {
      assert.equal(await cards.nth(i).locator("dd").nth(1).innerText(), "No");
      assert.equal(await cards.nth(i).locator("dd").nth(2).innerText(), "finished");
    }
    const detail = cards.first().locator("details");
    await detail.locator("summary").focus();
    await page.keyboard.press("Enter");
    assert.equal(await detail.getAttribute("open"), "");
    assert.equal(await detail.locator("li:visible").count(), 8);
    assert(await app.locator("body").evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  }
  return { contextControls: true, cohorts: 2, trials: 12, keyboardCaseDetails: true,
    completeArchiveBytesMatched: downloads };
}

module.exports = { checkContextControls };
