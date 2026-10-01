// Progressive enhancement for EvalArc offline reports. Inlined into every page and
// allowed by a CSP hash; without JavaScript every table still renders in full.
// Sortable columns follow the WAI-ARIA APG sortable table pattern (a button inside
// each header, aria-sort on the sorted column only). Tables with 8+ rows get a
// labelled row filter with a live count. Tables marked data-static are left alone.
(() => {
  const number = text => {
    const match = text.replace(/,/g, "").match(/[-+]?\d*\.?\d+/);
    return match ? parseFloat(match[0]) : NaN;
  };
  let filters = 0;
  document.querySelectorAll("main table").forEach(table => {
    const body = table.tBodies[0];
    const head = table.tHead;
    if (!body || !head || body.rows.length < 3 || table.dataset.static !== undefined) return;
    const rows = [...body.rows];
    const headers = [...head.rows[0].cells];
    headers.forEach((th, column) => {
      const label = th.textContent.trim();
      if (!label) return;
      const button = document.createElement("button");
      button.type = "button";
      const icon = document.createElement("span");
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = "↕";
      button.append(document.createTextNode(label + " "), icon);
      th.textContent = "";
      th.append(button);
      button.addEventListener("click", () => {
        const direction = th.getAttribute("aria-sort") === "ascending" ? "descending" : "ascending";
        headers.forEach(other => {
          other.removeAttribute("aria-sort");
          const mark = other.querySelector("button span");
          if (mark) mark.textContent = "↕";
        });
        th.setAttribute("aria-sort", direction);
        icon.textContent = direction === "ascending" ? "▲" : "▼";
        const key = row => (row.cells[column] ? row.cells[column].textContent.trim() : "");
        const sorted = [...body.rows].sort((x, y) => {
          const a = key(x), b = key(y), na = number(a), nb = number(b);
          const order = !isNaN(na) && !isNaN(nb) ? na - nb
            : a.localeCompare(b, undefined, { numeric: true });
          return direction === "ascending" ? order : -order;
        });
        sorted.forEach(row => body.append(row));
      });
    });
    if (rows.length < 8) return;
    filters += 1;
    const id = "filter-" + filters;
    const tools = document.createElement("div");
    tools.className = "tools";
    const label = document.createElement("label");
    label.htmlFor = id;
    label.textContent = "Filter rows";
    const input = document.createElement("input");
    input.type = "search";
    input.id = id;
    input.autocomplete = "off";
    const count = document.createElement("span");
    count.className = "count";
    count.setAttribute("aria-live", "polite");
    const update = () => {
      const query = input.value.trim().toLowerCase();
      let shown = 0;
      rows.forEach(row => {
        const hit = !query || row.textContent.toLowerCase().includes(query);
        row.hidden = !hit;
        shown += hit;
      });
      count.textContent = `${shown} of ${rows.length} rows`;
    };
    input.addEventListener("input", update);
    tools.append(label, input, count);
    (table.closest(".scroll") || table).before(tools);
    update();
  });
})();
