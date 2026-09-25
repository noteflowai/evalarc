// Four annotated screenshots of actual UI states; no evidence is edited.
// Build the site first. SITE_DIR selects that bundle; FFMPEG selects an encoder.
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const { execFileSync } = require("node:child_process");
const { chromium } = require("playwright");
const sha256 = bytes => crypto.createHash("sha256").update(bytes).digest("hex");
async function main() {
  const source = path.resolve(process.env.SITE_DIR || "dist/site");
  const output = path.resolve("docs/assets");
  fs.mkdirSync(output, {recursive:true});
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "ai-first-review-"));
  const browser = await chromium.launch({headless:true});
  const frames = [];
  const inputs = {};
  const read = name => {
    const data = fs.readFileSync(path.join(source, name));
    inputs[name] = sha256(data);
    return data;
  };
  try {
    const page = await browser.newPage({viewport:{width:1280,height:1100},reducedMotion:"reduce"});
    async function open(name) { await page.goto(pathToFileURL(path.join(source,name)).href); }
    async function capture(selectors, title, detail) {
      await page.evaluate(() => window.scrollTo(0,0));
      const clip = await page.evaluate(selectors => {
        const boxes = selectors.map(selector => document.querySelector(selector).getBoundingClientRect());
        const x = Math.min(...boxes.map(box=>box.left));
        const y = Math.min(...boxes.map(box=>box.top));
        return {x:Math.max(0,x-10),y:Math.max(0,y-10),
          width:Math.min(innerWidth-x,Math.max(...boxes.map(box=>box.right))-x+20),
          height:Math.max(...boxes.map(box=>box.bottom))-y+20};
      }, selectors);
      frames.push({title,detail,selectors,image:await page.screenshot({clip,fullPage:true})});
    }

    read("model-upgrade/index.html"); read("model-upgrade/reports/index.html");
    const data = JSON.parse(read("model-upgrade/review.json"));
    read("model-upgrade/protocol.json"); read("model-upgrade/reports/comparison.json");
    read("model-upgrade/reports/baseline.xml"); read("model-upgrade/reports/current.xml");
    assert.deepEqual(data.complete_plans,{baseline:15,current:19});
    await open("model-upgrade/index.html");
    await capture([".intro",".scope"],"Two configurations. All 48 original answers.","Qwen3-8B BF16 and Qwen3.8-27B FP8; three fresh answers per public development case.");
    await capture([".cards","#gate"],"The total improves. The upgrade is blocked.","Complete plans: 15/24 → 19/24. Ten named checks still lose passes.");
    await page.locator("#case").selectOption("already-closed"); await page.locator("#seed").selectOption("17");
    assert.equal(JSON.parse(await page.locator("#current-text").textContent()).actions,undefined);
    assert.deepEqual(JSON.parse(await page.locator("#baseline-text").textContent()),{actions:[]});
    await capture([".controls",".outputs"],"Inspect a regression, not just the total.","already-closed · seed 17: the current answer omits the required actions key.");
    await open("model-upgrade/reports/index.html");
    assert.equal(await page.locator(".number.failed").innerText(),"10");
    await capture([".cards","table thead","table tbody tr:first-child"],"Reproduce the decision from native results.","Compare the downloaded JUnit files with evalarc==0.15.0. Expected gate exit: 1.");

    assert.equal(frames.length,4);
    const canvas = await browser.newPage({viewport:{width:1280,height:960},deviceScaleFactor:1});
    for (const [index, frame] of frames.entries()) {
      await canvas.setContent(`<!doctype html><html lang="en"><meta charset="utf-8"><style>
      *{box-sizing:border-box}body{margin:0;padding:30px 40px;background:#101618;color:#edf5f2;font-family:system-ui,sans-serif}
      .meta{font:14px monospace;color:#80e6cf;letter-spacing:2px}h1{font-size:34px;line-height:1.18;margin:17px 0 12px}
      p{font-size:18px;line-height:1.4;color:#c7d4cd;margin:0 0 20px}img{display:block;width:1200px;height:670px;object-fit:contain;object-position:top center}
      footer{margin-top:18px;font:14px monospace;color:#a4b8ad}</style>
      <div class="meta">EVALARC / FIRST REVIEW / ${index+1} OF 4</div><h1></h1><p></p><img alt="Captured product view"><footer>Saved model generations · Public development cases · No new inference</footer></html>`);
      await canvas.locator("h1").evaluate((node,text)=>{node.textContent=text;},frame.title);
      await canvas.locator("p").evaluate((node,text)=>{node.textContent=text;},frame.detail);
      await canvas.locator("img").evaluate((node,src)=>{node.src=src;},"data:image/png;base64,"+frame.image.toString("base64"));
      await canvas.locator("img").evaluate(node=>node.decode());
      await canvas.screenshot({path:path.join(temporary,`frame-${index}.png`)});
    }
    fs.copyFileSync(path.join(temporary,"frame-0.png"),path.join(output,"ai-first-review.png"));
    const sequence = frames.map((_,i)=>`file '${path.join(temporary,`frame-${i}.png`)}'\nduration 7.5`).join("\n");
    const list = path.join(temporary,"frames.txt");
    fs.writeFileSync(list,sequence+`\nfile '${path.join(temporary,"frame-3.png")}'\n`);
    const ffmpeg = process.env.FFMPEG || "ffmpeg";
    execFileSync(ffmpeg,["-v","error","-y","-f","concat","-safe","0","-i",list,"-t","30",
      "-vf","fps=10,scale=1000:-2:flags=lanczos","-c:v","libx264","-crf","22","-pix_fmt","yuv420p",
      "-movflags","+faststart",path.join(output,"ai-first-review.mp4")],{stdio:"inherit"});
    execFileSync(ffmpeg,["-v","error","-y","-f","concat","-safe","0","-i",list,"-t","30",
      "-filter_complex","fps=2,scale=960:-2:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse",
      "-loop","0",path.join(output,"ai-first-review.gif")],{stdio:"inherit"});
    const cues=["00:00:00.000 --> 00:00:07.500","00:00:07.500 --> 00:00:15.000",
      "00:00:15.000 --> 00:00:22.500","00:00:22.500 --> 00:00:30.000"];
    fs.writeFileSync(path.join(output,"ai-first-review.vtt"),"WEBVTT\n\n"+frames.map((f,i)=>`${cues[i]}\n${f.title}\n${f.detail}\n`).join("\n"));
    const files=Object.fromEntries(["png","gif","mp4","vtt"].map(ext=>{
      const name="ai-first-review."+ext,bytes=fs.readFileSync(path.join(output,name));
      return [name,{bytes:bytes.length,sha256:sha256(bytes)}];
    }));
    assert(files["ai-first-review.mp4"].bytes<1_000_000,"Keep the walkthrough video below 1 MB");
    fs.writeFileSync(path.join(output,"ai-first-review-media.json"),JSON.stringify({
      kind:"Four annotated screenshots of actual UI states",duration_seconds:30,
      source_files:inputs,frames:frames.map(({title,detail,selectors})=>({title,detail,selectors})),files,
      scope:"Selected public support-planning cases. Plans are not executed; configurations differ in size, architecture and quantization. No new inference."
    },null,2)+"\n");
    console.log(JSON.stringify({frames:frames.length,duration_seconds:30,files},null,2));
  } finally { await browser.close(); fs.rmSync(temporary,{recursive:true,force:true}); }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
