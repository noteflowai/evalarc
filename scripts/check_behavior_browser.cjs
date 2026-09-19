const assert = require("node:assert/strict");

async function checkBehavior(page, app, { interactive = true } = {}) {
  async function documentReady() {
    await app.locator("body").evaluate(() => new Promise(resolve => {
      if (document.readyState !== "loading") resolve();
      else document.addEventListener("DOMContentLoaded", () => resolve(), { once: true });
    }));
  }
  await app.getByRole("heading", {
    name: "A correct final file can hide an unauthorized operation."
  }).waitFor();
  await documentReady();
  assert.equal(await app.locator("#cases article:visible").count(), 44);
  const method = app.locator("details.method");
  await method.locator("summary").focus();
  await page.keyboard.press("Enter");
  assert.equal(await method.getAttribute("open"), "");
  assert(await method.locator("summary").evaluate(element =>
    element.getBoundingClientRect().height >= 44));
  await page.keyboard.press("Space");
  assert.equal(await method.getAttribute("open"), null);
  if (interactive) {
    await app.locator("#group").selectOption("pilot");
    assert.equal(await app.locator("#cases article:visible").count(), 12);
    await app.locator("#outcome").selectOption("invalid");
    assert.equal(await app.locator("#cases article:visible").count(), 1);
    assert.match(await app.locator("#cases article:visible").innerText(), /07-composed-41/);
    await app.locator("#query").fill("no matching case");
    assert.equal(await app.locator("#cases article:visible").count(), 0);
    assert(await app.locator("#empty").isVisible());
    await app.locator("#query").fill("");
    await app.locator("#outcome").selectOption("");
    await app.locator("#group").selectOption("");
  } else {
    assert(await app.locator("#filters").isHidden());
  }
  assert(await app.locator("body").evaluate(() =>
    document.documentElement.scrollWidth <= innerWidth + 1));
  await app.getByRole("link", { name: "write-then-delete", exact: true }).click();
  await app.getByRole("heading", {
    name: "write-then-delete", exact: true, level: 1
  }).waitFor();
  await documentReady();
  assert.match(await app.locator(".results").innerText(), /Final file\s+Yes/);
  assert.match(await app.locator(".results").innerText(), /Authorized behavior\s+No/);
  const event = app.locator(".events > li.violation").first();
  assert.match(await event.innerText(), /unrequested\.json/);
  await event.getByRole("link", { name: "System-call source lines" }).click();
  await app.getByRole("heading", { name: "System-call source excerpts" }).waitFor();
  await documentReady();
  assert.match(await app.locator("body").evaluate(() => location.hash), /^#L\d+$/);
  assert.match(await app.locator(":target").innerText(), /unrequested\.json/);
  assert(await app.locator("body").evaluate(() =>
    document.documentElement.scrollWidth <= innerWidth + 1));
  return { behaviorReview: true, records: 44, invalidModelAttempts: 1, interactive };
}

module.exports = { checkBehavior };
