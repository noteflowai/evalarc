// Capture actual UI states; annotate them without changing any displayed evidence.
// Run after build_site.py, with SITE_URL pointing to a local HTTP server.
// FFMPEG must name an ffmpeg executable with libx264 and GIF encoding support.
const {chromium} = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const crypto = require("node:crypto");
const {execFileSync} = require("node:child_process");

async function main() {
  const base = process.env.SITE_URL || "http://127.0.0.1:8767/";
  const output = path.resolve("docs/assets");
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "evalarc-tour-"));
  const browser = await chromium.launch({headless:true});
  const frames = [];
  try {
    const page = await browser.newPage({viewport:{width:1280,height:1100}});
    await page.emulateMedia({reducedMotion:"reduce"});
    await page.goto(base, {waitUntil:"networkidle"});
    await page.locator("#suite-workspace").waitFor({state:"visible"});
    assert.equal(await page.locator("#before-score").innerText(), "90%");
    assert.equal(await page.locator("#after-score").innerText(), "93.75%");
    assert.equal(await page.locator("#regression-count").innerText(), "1 REGRESSED CHECK");
    async function capture(selector, title, detail) {
      const image = await page.locator(selector).screenshot();
      frames.push({title,detail,image});
    }
    await capture("#comparison-workspace", "A higher score. A new regression.",
      "90% → 93.75% · Two closure checks improve; the notes check regresses.");
    await page.locator("#next-step").click();
    await page.locator("#next-step").click();
    assert.match(await page.locator("#trace-action").innerText(), /temporarily_unavailable/);
    assert.match(await page.locator("#trace-changes").innerText(), /Reviewed request/);
    await capture("#trace-panel", "The tool returned an error. The note was written.",
      "Recorded step 3 · The state changed before the transient error returned.");
    await page.locator("#next-step").click();
    const change = JSON.parse(await page.locator("#trace-changes").innerText());
    assert.equal(Object.values(change)[0].after.notes.length, 3);
    await capture("#trace-panel", "A new key. A duplicate note.",
      "Recorded step 4 · Retrying the write with a different key adds the note again.");
    assert.equal(await page.locator("#suite-partial-verdict").innerText(), "GATE ACCEPTED");
    assert.equal(await page.locator("#suite-protected-verdict").innerText(), "GATE REJECTED");
    await capture(".suite-comparison", "Keep the score. Check the acceptance rule.",
      "Same 93.75% policy · The strict notes gate rejects what the permissive gate accepts.");
    const canvas = await browser.newPage({viewport:{width:1280,height:960},deviceScaleFactor:1});
    for (const [index,frame] of frames.entries()) {
      await canvas.setContent(`<!doctype html><html lang="en"><meta charset="utf-8">
        <style>*{box-sizing:border-box}body{margin:0;background:#101618;color:#eff8f2;font-family:system-ui,sans-serif;padding:32px 40px}
        .meta{font:14px monospace;color:#86dbaf;letter-spacing:2px}h1{font-size:34px;line-height:1.2;margin:16px 0 10px}
        p{font-size:17px;color:#c7d4cd;margin:0 0 24px}img{display:block;width:1200px;height:670px;object-fit:contain;object-position:top center}
        footer{margin-top:22px;font:14px monospace;color:#9fb3a7;display:flex;justify-content:space-between}</style>
        <div class="meta">EVALARC / FIRST REVIEW / ${index+1} OF 4</div><h1></h1><p></p>
        <img alt="Captured evidence view"><footer><span>Saved scripted Docker controls · Annotated UI walkthrough</span><span>No model call</span></footer>`);
      await canvas.locator("h1").evaluate((node,text) => {node.textContent=text}, frame.title);
      await canvas.locator("p").evaluate((node,text) => {node.textContent=text}, frame.detail);
      await canvas.locator("img").evaluate((node,src) => {node.src=src}, "data:image/png;base64,"+frame.image.toString("base64"));
      await canvas.locator("img").evaluate(node => node.decode());
      await canvas.screenshot({path:path.join(temporary,`frame-${index}.png`)});
    }
    fs.copyFileSync(path.join(temporary,"frame-0.png"),path.join(output,"first-review.png"));
    const sequence = frames.map((_,i) => `file '${path.join(temporary,`frame-${i}.png`)}'\nduration 7.5`).join("\n");
    const list = path.join(temporary,"frames.txt");
    fs.writeFileSync(list,sequence+`\nfile '${path.join(temporary,"frame-3.png")}'\n`);
    const ffmpeg = process.env.FFMPEG || "ffmpeg";
    execFileSync(ffmpeg,["-v","error","-y","-f","concat","-safe","0","-i",list,"-t","30",
      "-vf","fps=10,scale=1000:-2:flags=lanczos","-c:v","libx264","-crf","22","-pix_fmt","yuv420p",
      "-movflags","+faststart",path.join(output,"first-review.mp4")],{stdio:"inherit"});
    execFileSync(ffmpeg,["-v","error","-y","-f","concat","-safe","0","-i",list,"-t","30",
      "-filter_complex","fps=2,scale=960:-2:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse",
      "-loop","0",path.join(output,"first-review.gif")],{stdio:"inherit"});
    const cues = ["00:00:00.000 --> 00:00:07.500","00:00:07.500 --> 00:00:15.000",
      "00:00:15.000 --> 00:00:22.500","00:00:22.500 --> 00:00:30.000"];
    fs.writeFileSync(path.join(output,"first-review.vtt"),"WEBVTT\n\n"+frames.map((f,i) =>
      `${cues[i]}\n${f.title}\n${f.detail}\n`).join("\n"));
    const manifest = await (await page.request.get(new URL("manifest.json",base).href)).json();
    const evidence = ["comparison/baseline.json","comparison/current.json","support/audit.json","suite/suite.json"];
    const files = Object.fromEntries(["png","gif","mp4","vtt"].map(ext => {
      const name="first-review."+ext, bytes=fs.readFileSync(path.join(output,name));
      return [name,{bytes:bytes.length,sha256:crypto.createHash("sha256").update(bytes).digest("hex")}];
    }));
    fs.writeFileSync(path.join(output,"first-review-media.json"),JSON.stringify({
      kind:"annotated screenshots of actual UI states",duration_seconds:30,
      evidence:Object.fromEntries(evidence.map(name => [name,manifest.files[name]])),
      frames:frames.map(({title,detail}) => ({title,detail})),files,
      scope:"Saved scripted Docker controls. No new agent execution or customer evidence.",
    },null,2)+"\n");
    console.log(JSON.stringify({frames:frames.length,duration_seconds:30,files},null,2));
  } finally {
    await browser.close();
    fs.rmSync(temporary,{recursive:true,force:true});
  }
}
main().catch(error => {console.error(error);process.exitCode=1});
