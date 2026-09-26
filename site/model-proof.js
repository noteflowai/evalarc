"use strict";
{
  const el = id => document.getElementById(id);
  const data = JSON.parse(el("model-proof-data").textContent);
  let seed = Object.keys(data.outputs)[0];
  for (const button of document.querySelectorAll("[data-model-seed]")) {
    button.addEventListener("click", () => {
      seed = button.dataset.modelSeed;
      el("proof-before").textContent = data.outputs[seed].baseline;
      el("proof-after").textContent = data.outputs[seed].current;
      el("proof-caption").textContent = `Seed ${seed} · The required actions field is missing.`;
      el("proof-open").href = `model-upgrade/index.html#case=already-closed&seed=${seed}`;
      for (const other of document.querySelectorAll("[data-model-seed]")) other.setAttribute("aria-pressed", String(other === button));
    });
  }
  el("proof-image").hidden = false;
  el("proof-image").addEventListener("click", () => {
    const canvas = document.createElement("canvas");
    canvas.width = 1200; canvas.height = 630;
    const ctx = canvas.getContext("2d");
    if (!ctx) { el("proof-image-status").textContent = "Image export is unavailable. Open the full review to download the evidence."; return; }
    const bg = ctx.createLinearGradient(0, 0, 1200, 630);
    bg.addColorStop(0, "#23382e"); bg.addColorStop(1, "#101618");
    ctx.fillStyle = bg; ctx.fillRect(0, 0, 1200, 630);
    ctx.fillStyle = "#afe0b1"; ctx.font = "600 24px system-ui, sans-serif";
    ctx.fillText("EVALARC / RECORDED MODEL UPGRADE", 64, 68);
    ctx.fillStyle = "#e9f0ec"; ctx.font = "600 52px system-ui, sans-serif";
    ctx.fillText("More passing plans. A failed gate.", 64, 156);
    ctx.font = "600 104px system-ui, sans-serif";
    ctx.fillText(`${data.before}/${data.total} → ${data.after}/${data.total}`, 64, 298);
    ctx.fillStyle = "#efad8b"; ctx.font = "600 30px system-ui, sans-serif";
    ctx.fillText(`${data.blocking} named checks lost passes or coverage`, 64, 355);
    ctx.fillStyle = "#b3c3bc"; ctx.font = "22px system-ui, sans-serif";
    ctx.fillText("Qwen3-8B BF16 → Qwen3.8-27B FP8 · 8 cases × 3 generations each", 64, 410);
    ctx.fillText("Two shared format/schema failures. Selected public development cases.", 64, 458);
    ctx.fillText("Plans not executed. Model size, architecture and quantization differ.", 64, 496);
    ctx.font = "20px ui-monospace, monospace";
    ctx.fillText("noteflowai.github.io/evalarc/model-upgrade/index.html", 64, 568);
    canvas.toBlob(blob => {
      if (!blob) { el("proof-image-status").textContent = "Image export failed. Open the full review instead."; return; }
      const url = URL.createObjectURL(blob), link = document.createElement("a");
      link.href = url; link.download = "evalarc-model-upgrade.png"; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
      el("proof-image-status").textContent = "Saved the recorded comparison with its scope and source address.";
    }, "image/png");
  });
}
