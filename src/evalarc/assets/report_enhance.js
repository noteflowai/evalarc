"use strict";
// Progressive enhancement for EvalArc offline reports, compiled to
// src/evalarc/assets/report_enhance.js (committed, so `pip install` needs no Node).
// The Python core inlines the compiled file and allows it by CSP hash; without
// JavaScript every table still renders in full. Sortable columns follow the WAI-ARIA
// APG sortable-table pattern (a button inside each header, aria-sort on the sorted
// column only). Tables with 8+ rows get a labelled row filter with a live count.
// Tables marked data-static are left alone.
(() => {
    const SORTABLE_MIN_ROWS = 3;
    const FILTER_MIN_ROWS = 8;
    function leadingNumber(text) {
        const match = text.replace(/,/g, "").match(/[-+]?\d*\.?\d+/);
        return match ? parseFloat(match[0]) : NaN;
    }
    function cellText(row, column) {
        const cell = row.cells[column];
        return cell ? (cell.textContent ?? "").trim() : "";
    }
    function compare(a, b) {
        const na = leadingNumber(a);
        const nb = leadingNumber(b);
        if (!Number.isNaN(na) && !Number.isNaN(nb))
            return na - nb;
        return a.localeCompare(b, undefined, { numeric: true });
    }
    function makeSortable(body, headers) {
        headers.forEach((th, column) => {
            const label = (th.textContent ?? "").trim();
            if (!label)
                return;
            const button = document.createElement("button");
            button.type = "button";
            const icon = document.createElement("span");
            icon.setAttribute("aria-hidden", "true");
            icon.textContent = "↕";
            button.append(document.createTextNode(`${label} `), icon);
            th.textContent = "";
            th.append(button);
            button.addEventListener("click", () => {
                const direction = th.getAttribute("aria-sort") === "ascending" ? "descending" : "ascending";
                for (const other of headers) {
                    other.removeAttribute("aria-sort");
                    const mark = other.querySelector("button span");
                    if (mark)
                        mark.textContent = "↕";
                }
                th.setAttribute("aria-sort", direction);
                icon.textContent = direction === "ascending" ? "▲" : "▼";
                const sorted = Array.from(body.rows).sort((x, y) => {
                    const order = compare(cellText(x, column), cellText(y, column));
                    return direction === "ascending" ? order : -order;
                });
                for (const row of sorted)
                    body.append(row);
            });
        });
    }
    function addFilter(table, rows, index) {
        const id = `filter-${index}`;
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
            for (const row of rows) {
                const hit = !query || (row.textContent ?? "").toLowerCase().includes(query);
                row.hidden = !hit;
                if (hit)
                    shown += 1;
            }
            count.textContent = `${shown} of ${rows.length} rows`;
        };
        input.addEventListener("input", update);
        tools.append(label, input, count);
        (table.closest(".scroll") ?? table).before(tools);
        update();
    }
    function enhance() {
        let filters = 0;
        document.querySelectorAll("main table").forEach((table) => {
            const body = table.tBodies[0];
            const head = table.tHead;
            if (!body || !head || !head.rows[0])
                return;
            if (body.rows.length < SORTABLE_MIN_ROWS || table.dataset.static !== undefined)
                return;
            const rows = Array.from(body.rows);
            makeSortable(body, Array.from(head.rows[0].cells));
            if (rows.length >= FILTER_MIN_ROWS) {
                filters += 1;
                addFilter(table, rows, filters);
            }
        });
    }
    enhance();
})();
