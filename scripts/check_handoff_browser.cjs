// Read the displayed continuation evidence against its original model and tool records.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

async function checkHandoff(page, app, root, {
  downloads = true, interactive = true, skillHandoff = false
} = {}) {
  const folder = path.join(root, skillHandoff ? "skill-handoff" : "funes-handoff");
  const rows = JSON.parse(fs.readFileSync(path.join(folder, "summary.json"))).trials;
  await app.getByRole("heading", { name: skillHandoff
    ? /Carry the reviewed skill.*Check what the next agent delivers/
    : /Retrieve the history.*Check the delivered program/ }).waitFor();
  await app.locator("body").evaluate(() => new Promise(resolve => {
    if (document.readyState !== "loading") resolve();
    else document.addEventListener("DOMContentLoaded", () => resolve(), { once: true });
  }));
  const metrics = app.locator(".metric strong");
  const resolved = rows.filter(row => row.evaluation?.resolved).length;
  const changed = rows.filter(row => row.operations.program_changed).length;
  const retrievals = rows.reduce((sum, row) => sum + row.operations.retrieved_results, 0);
  const expectedMetrics = skillHandoff
    ? [`${rows.filter(row => row.skill_delivery_status === "loaded").length} / ${rows.length}`,
      `${retrievals}`, `${resolved} / ${rows.length}`, `${changed} / ${rows.length}`]
    : [`${resolved} / ${rows.length}`, `${retrievals}`, `${changed} / ${rows.length}`];
  assert.deepEqual(await metrics.allInnerTexts(), expectedMetrics);
  assert.equal(await app.locator("article:visible").count(), rows.length);
  let retrieved = 0;
  for (let index = 0; index < rows.length; index++) {
    const row = rows[index];
    const trial = JSON.parse(fs.readFileSync(path.join(folder, row.path, "trial.json")));
    const card = app.locator(`#attempt-${index + 1}`);
    const tableRow = app.locator("tbody tr").nth(index);
    assert.equal(await tableRow.locator("td").nth(0).innerText(),
      (row.evaluation.score * 100).toFixed(1) + "%");
    assert.equal(await tableRow.locator("td").nth(1).innerText(), "Unresolved");
    assert.match(await card.innerText(), /Program state\s+Unchanged/);
    if (skillHandoff) {
      const delivery = trial.handoff.skill_delivery;
      const receipt = JSON.parse(fs.readFileSync(path.join(folder, delivery.path)));
      assert.equal(receipt.actor, "harness");
      assert.equal(await card.locator(`a[href="${delivery.path}"]`).innerText(), receipt.status);
      assert.deepEqual(receipt.expected_pins, trial.skill_pins);
    }
    const tools = card.locator(":scope > details").first();
    await tools.locator(":scope > summary").focus();
    await page.keyboard.press("Enter");
    assert.equal(await tools.getAttribute("open"), "");
    for (const event of trial.tool_events) {
      if (!["recall_prior_session", "read_prior_turns", "run_command"].includes(event.name)) continue;
      // There is one call for each memory tool; command calls preserve their original order.
      const position = trial.tool_events.filter(item => item.name === event.name).indexOf(event);
      const result = tools.locator(`li[data-tool="${event.name}"]`).nth(position).locator("details");
      await result.locator("summary").click();
      assert.deepEqual(JSON.parse(await result.locator("pre").innerText()), event.result);
      if (event.name !== "run_command") {
        retrieved++;
        await result.locator("pre").focus();
        assert.equal(await result.locator("pre").evaluate(element => element === document.activeElement), true);
      }
    }
    const failed = card.locator(":scope > details").nth(1);
    await failed.locator("summary").click();
    const evaluation = JSON.parse(fs.readFileSync(path.join(folder, row.path, "evaluation.json")));
    const failedCases = evaluation.cases.filter(item => item.status !== "passed");
    assert.equal(await failed.locator("li").count(), failedCases.length);
    const failureText = await failed.innerText();
    for (const item of failedCases) assert(failureText.includes(`seed ${item.seed} / ${item.case_id}`));
    await tools.locator(":scope > summary").click();
  }
  assert.equal(retrieved, retrievals);
  if (skillHandoff) {
    const methods = app.locator("#methods");
    const summary = methods.locator(":scope > summary");
    await summary.focus();
    await page.keyboard.press("Enter");
    assert.equal(await methods.getAttribute("open"), "");
    assert.match(await methods.innerText(), /shared editable Python environment/);
    assert((await summary.boundingBox()).height >= 44);
    await page.keyboard.press("Space");
    assert.equal(await methods.getAttribute("open"), null);
  }
  if (interactive) {
    const selector = app.locator("#condition");
    await selector.focus();
    await page.keyboard.press("End");
    await page.keyboard.press("Enter");
    assert.equal(await selector.inputValue(), "funes-mcp");
    assert.equal(await app.locator("article:visible").count(), 3);
    await app.locator('tbody a[href="#attempt-1"]').click();
    assert.equal(await selector.inputValue(), "all");
    assert.equal(await app.locator("article:visible").count(), 6);
    assert.equal(await app.locator("body").evaluate(() => location.hash), "#attempt-1");
    await selector.selectOption("no-memory");
    await app.locator("body").evaluate(() => { location.hash = "attempt-2"; });
    await app.locator("#attempt-2").waitFor({ state: "visible" });
    assert.equal(await selector.inputValue(), "all");
  } else {
    assert(await app.locator("#filter").isHidden());
  }
  assert(await app.locator("body").evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  if (downloads) {
    for (const [link, filename] of [
      [app.getByRole("link", { name: skillHandoff
        ? "Download complete handoff evidence" : "Download the complete offline evidence", exact: true }),
      skillHandoff ? "skill-handoff.zip" : "funes-handoff.zip"],
      [app.locator("#attempt-2").getByRole("link", { name: "Trial JSON", exact: true }), rows[1].path + "/trial.json"],
    ]) {
      const pending = page.waitForEvent("download");
      await link.click();
      const received = await pending;
      assert.equal(await received.failure(), null);
      assert.deepEqual(fs.readFileSync(await received.path()), fs.readFileSync(path.join(folder, filename)));
    }
  }
  return { funesHandoff: true, skillHandoff, attempts: rows.length, retrievedResultsMatched: retrieved,
    independentFailuresVisible: true, keyboardDetails: true, interactive,
    downloadedBytesMatched: downloads };
}

module.exports = { checkHandoff };
