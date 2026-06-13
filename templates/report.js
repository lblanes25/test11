
// ==================== EMBEDDED DATA ====================
const auditData = __AUDIT_JSON__;
const detailData = __DETAIL_JSON__;
const findingsData = __FINDINGS_JSON__;
const subRisksData = __SUB_RISKS_JSON__;
const oreData = __ORE_JSON__;
const prsaData = __PRSA_JSON__;
const pgGapData = __PG_GAP_JSON__;
const bmaData = __BMA_JSON__;
const graRapsData = __GRA_RAPS_JSON__;
const legacyRatingsData = __LEGACY_RATINGS_JSON__;
const legacyData = __LEGACY_JSON__;
const applicationsInventory = __APPS_INV_JSON__;
const policiesInventory = __POLICIES_INV_JSON__;
const lawsInventory = __LAWS_INV_JSON__;
const thirdpartiesInventory = __TP_INV_JSON__;
const modelsInventory = __MODELS_INV_JSON__;
const INVENTORY_COLS = __INVENTORY_COLS_JSON__;
const entities = __ENTITIES_JSON__;
const l2Risks = __L2_RISKS_JSON__;
const auditLeaders = __AUDIT_LEADERS_JSON__;
const pgaList = __PGAS_JSON__;
const coreTeams = __CORE_TEAMS_JSON__;
const entityMeta = __ENTITY_META_JSON__;
// Per-entity sets of "key" application / third-party IDs aggregated from
// key risk rows. Per procedure, non-key items do not drive risk; the UI
// marks key IDs in drill-down and Source Data inventory tables.
//   shape: {eid: {keyApps: [...], keyTps: [...], orphanApps: [...], orphanTps: [...]}}
const keyInventory = __KEY_INVENTORY_JSON__;

// Methodology view rows — flat list of [topic, detail] tuples sourced from
// methodology.yaml (tab: "LUminate Methodology"). renderMethodologyView()
// walks the list and emits headings + paragraphs + bullets.
const methodologyRows = __METHODOLOGY_ROWS_JSON__;

function getKeyInv(eid) {
    return keyInventory[eid] || {
        keyApps: [], keyTps: [], orphanApps: [], orphanTps: [],
        keyAppsKpa: {}, keyTpsKpa: {},
    };
}
function isKeyApp(eid, id) {
    return getKeyInv(eid).keyApps.indexOf(String(id)) >= 0;
}
function isKeyTp(eid, id) {
    return getKeyInv(eid).keyTps.indexOf(String(id)) >= 0;
}
// Return the list of KPA IDs where this app/TP is "key" for the entity.
// Empty array if not key or no KPA attribution available.
function keyAppKpas(eid, id) {
    let m = getKeyInv(eid).keyAppsKpa || {};
    return m[String(id)] || [];
}
function keyTpKpas(eid, id) {
    let m = getKeyInv(eid).keyTpsKpa || {};
    return m[String(id)] || [];
}

function getEntityMeta(eid) { return entityMeta[eid] || {}; }

// ==================== STATUS CONFIG ====================
const STATUS_CONFIG = {
    "Applicability Undetermined": {"icon": "\u26A0\uFE0F", "sort": 0},
    "Needs Review": {"icon": "\ud83d\udd0e", "sort": 1},
    "No Evidence Found \u2014 Verify N/A": {"icon": "\ud83d\udd36", "sort": 2},
    "Applicable": {"icon": "\u2705", "sort": 3},
    "Not Applicable": {"icon": "\u2B1C", "sort": 4},
    "Not Assessed": {"icon": "\ud83d\udd35", "sort": 5},
};
const RATING_RANK = {"Low":1,"Medium":2,"High":3,"Critical":4,"low":1,"medium":2,"high":3,"critical":4};
const RANK_LABEL = {1:"Low",2:"Medium",3:"High",4:"Critical"};
const IAG_ACTIVE_STATUSES = new Set(["open", "in validation", "in sustainability"]);
function isActiveIagStatus(status) {
    return IAG_ACTIVE_STATUSES.has(String(status||"").toLowerCase().trim());
}

// Build entity-to-name mapping from hoisted entity metadata
const entityNameMap = {};
Object.keys(entityMeta).forEach(eid => {
    let nm = entityMeta[eid] && entityMeta[eid]["Entity Name"];
    if (nm) entityNameMap[eid] = nm;
});

let _showInactiveEntities = false;
function getEntityStatus(eid) { return getEntityMeta(eid)["Audit Entity Status"] || ""; }
function isActiveEntity(eid) { return String(getEntityStatus(eid)).trim().toLowerCase() === "active"; }

// ==================== TYPEAHEAD COMBOBOX ====================
// Shared factory used for Entity + Risk selectors. Option shape: {value, label}.
// getOptions() returns the live option list; onSelect(value) fires when
// the user picks an item. The input element's `value` holds the current label;
// its `dataset.value` holds the selected option's underlying value.
const _typeaheads = {};

function makeTypeahead(inputId, listId, getOptions, onSelect) {
    const input = document.getElementById(inputId);
    const list = document.getElementById(listId);
    if (!input || !list) return null;
    const state = { options: [], filtered: [], active: -1, getOptions, onSelect, input, list };
    _typeaheads[inputId] = state;

    function render() {
        list.innerHTML = "";
        if (!state.filtered.length) {
            const empty = document.createElement("div");
            empty.className = "typeahead-empty";
            empty.textContent = "No matches";
            list.appendChild(empty);
            return;
        }
        state.filtered.forEach((opt, idx) => {
            const div = document.createElement("div");
            div.className = "typeahead-item" + (idx === state.active ? " active" : "");
            div.textContent = opt.label;
            div.addEventListener("mousedown", (e) => {
                e.preventDefault();
                pick(opt);
            });
            list.appendChild(div);
        });
    }

    function filter(q) {
        const needle = String(q || "").trim().toLowerCase();
        if (!needle) {
            state.filtered = state.options.slice();
        } else {
            state.filtered = state.options.filter(o =>
                String(o.label || "").toLowerCase().includes(needle) ||
                String(o.value || "").toLowerCase().includes(needle)
            );
        }
        state.active = state.filtered.length ? 0 : -1;
        render();
    }

    function open() {
        list.style.display = "block";
        filter(input.value);
    }
    function close() {
        list.style.display = "none";
        state.active = -1;
    }
    function pick(opt) {
        input.value = opt.label;
        input.dataset.value = opt.value;
        close();
        if (state.onSelect) state.onSelect(opt.value);
    }

    input.addEventListener("focus", open);
    input.addEventListener("input", () => { open(); });
    input.addEventListener("keydown", (e) => {
        if (e.key === "ArrowDown") {
            e.preventDefault();
            if (list.style.display !== "block") { open(); return; }
            if (!state.filtered.length) return;
            state.active = (state.active + 1) % state.filtered.length;
            render();
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            if (!state.filtered.length) return;
            state.active = (state.active - 1 + state.filtered.length) % state.filtered.length;
            render();
        } else if (e.key === "Enter") {
            if (state.active >= 0 && state.filtered[state.active]) {
                e.preventDefault();
                pick(state.filtered[state.active]);
            }
        } else if (e.key === "Escape") {
            close();
            input.blur();
        }
    });
    document.addEventListener("mousedown", (e) => {
        if (!list.contains(e.target) && e.target !== input) close();
    });

    // Expose a rebuild hook: call when underlying options change.
    state.rebuild = function(selectValue) {
        state.options = (state.getOptions() || []).map(o => ({
            value: String(o.value),
            label: String(o.label == null ? o.value : o.label),
        }));
        // Preserve current selection if still present; otherwise pick first.
        let current = selectValue != null ? String(selectValue) : (input.dataset.value || "");
        let match = state.options.find(o => o.value === current);
        if (!match && state.options.length) match = state.options[0];
        if (match) {
            input.value = match.label;
            input.dataset.value = match.value;
        } else {
            input.value = "";
            input.dataset.value = "";
        }
        state.filtered = state.options.slice();
        state.active = state.filtered.length ? 0 : -1;
        if (list.style.display === "block") render();
    };

    return state;
}

function getTypeaheadValue(inputId) {
    const input = document.getElementById(inputId);
    return input ? (input.dataset.value || "") : "";
}

function _buildEntityOptions() {
    const opts = [];
    entities.forEach(eid => {
        let active = isActiveEntity(eid);
        if (!active && !_showInactiveEntities) return;
        let name = entityNameMap[eid] || "";
        let label = name ? (eid + " - " + name) : eid;
        if (!active) label += " (Inactive)";
        opts.push({ value: eid, label });
    });
    return opts;
}

function rebuildEntitySelect() {
    const ta = _typeaheads["entity-select"];
    if (ta) ta.rebuild();
}

function toggleShowInactive(el) {
    _showInactiveEntities = el.checked;
    const ta = _typeaheads["entity-select"];
    if (ta) {
        const prev = getTypeaheadValue("entity-select");
        ta.rebuild(prev);
    }
    renderEntityView();
}

// ================================================================
// PILL PALETTES -- single source of truth for all color-coded pills.
// Consumed by makePill(value, paletteName) and pillStyleFor().
// ================================================================
const PILL_PALETTES = {
    severity: {
        "critical": {bg: "#FCEBEB", fg: "#791F1F"},
        "high":     {bg: "#FAD8C1", fg: "#7A2E0F"},
        "medium":   {bg: "#FAEEDA", fg: "#633806"},
        "low":      {bg: "#EAF3DE", fg: "#27500A"},
    },
    oreClass: {
        "class a": {bg: "#FCEBEB", fg: "#791F1F"},
        "class b": {bg: "#FAD8C1", fg: "#7A2E0F"},
        "class c": {bg: "#FAEEDA", fg: "#633806"},
    },
    controlRating: {
        // New terminology (2026-04-21). Three-level baseline.
        "satisfactory":              {bg: "#EAF3DE", fg: "#27500A"},
        "partially effective":       {bg: "#FAEEDA", fg: "#633806"},
        "ineffective":               {bg: "#FCEBEB", fg: "#791F1F"},
        // Legacy terminology (still appears in legacy per-pillar control
        // effectiveness column and older outputs).
        "well controlled":           {bg: "#EAF3DE", fg: "#27500A"},
        "moderately controlled":     {bg: "#FAEEDA", fg: "#633806"},
        "insufficiently controlled": {bg: "#FCEBEB", fg: "#791F1F"},
        "inadequately controlled":   {bg: "#FCEBEB", fg: "#791F1F"},
        "poorly controlled":         {bg: "#FCEBEB", fg: "#791F1F"},
    },
    // iagStatus: "closed" renders neutral; all other non-empty values warn.
    // Handled specially in makePill() below.
    iagStatus: {
        "open":              {bg: "#FAEEDA", fg: "#633806"},
        "in validation":     {bg: "#FAEEDA", fg: "#633806"},
        "in sustainability": {bg: "#FAEEDA", fg: "#633806"},
    },
};

// ==================== HELPERS ====================
function isEmpty(v) { return v === null || v === undefined || v === "" || v === "nan" || v === "None" || (typeof v === "number" && isNaN(v)); }
function esc(s) {
    if (!s) return "";
    let d = document.createElement("div");
    d.textContent = String(s);
    return d.innerHTML;
}
function icon(status) {
    let cfg = STATUS_CONFIG[status];
    return cfg ? cfg.icon : "\u2753";
}
function statusLabel(status) { return icon(status) + " " + status; }
function ratingBar(v) {
    if (isEmpty(v)) return "\u2014";
    let n = parseInt(v);
    return "\u2588".repeat(n) + "\u2591".repeat(4-n) + " " + n + " (" + (RANK_LABEL[n]||"") + ")";
}
function basePillar(s) { return String(s || "").split(" (also")[0].trim(); }
function methodToStatus(m) {
    m = String(m);
    if (m.includes("llm_confirmed_na")) return "Not Applicable";
    if (m.includes("source_not_applicable")) return "Not Applicable";
    if (m.includes("evaluated_no_evidence")) return "No Evidence Found \u2014 Verify N/A";
    if (m.includes("no_evidence_all_candidates")) return "Applicability Undetermined";
    if (m.includes("true_gap_fill") || m.includes("gap_fill")) return "Not Assessed";
    if (m.includes("direct") || m.includes("evidence_match") || m.includes("llm_override") || m.includes("issue_confirmed") || m.includes("dedup")) return "Applicable";
    return "Needs Review";
}

// resolveCol: pick the first candidate column name that exists on row 0 of
// `data`. Consolidates the "snake_case ? snake : TitleCase" pattern used by
// every source-data block. Returns null if none match or data is empty.
function resolveCol(data, candidates) {
    if (!data || !data.length) return null;
    let row = data[0];
    for (let c of candidates) {
        if (row.hasOwnProperty(c)) return c;
    }
    return null;
}

function normId(x){ return String(x==null?"":x).trim().replace(/\.0+$/,""); }

// oreRowEid: per-row entity ID for the mixed IRM + legacy oreData array.
function oreRowEid(o) { return normId(o["entity_id"] || o["Audit Entity (Operational Risk Events)"] || o["Audit Entity ID"] || ""); }

// isAbsence: a value is an "absence" if it conveys that nothing was found /
// is available. Absence values should not render as loud callouts -- they
// render as muted inline text (when meaningful as reassurance) or are
// omitted entirely. Distinct from isEmpty() which just checks for no data.
function isAbsence(v) {
    if (isEmpty(v)) return true;
    let s = String(v).trim().toLowerCase();
    if (s === "n/a" || s === "na" || s === "none" || s === "not available" || s === "not applicable") return true;
    if (s === "no open items") return true;
    if (/^no .+ available$/.test(s)) return true;
    if (/^(n\/a|na)\s*[-–—:]\s*not applicable$/.test(s)) return true;
    return false;
}

// ================================================================
// PILL RENDERING
// ================================================================
// Single pill factory: looks up `value` in the named palette and renders a
// styled <span>. Empty/N/A values render neutral. Unknown values render
// neutral. Handles the IAG "closed is neutral" special case.
function makePill(value, paletteName) {
    let s = String(value || "").trim();
    let lower = s.toLowerCase();
    if (!s || lower === "n/a" || lower === "na" || lower === "not applicable") {
        return '<span class="pill pill-neutral">' + esc(s || "N/A") + '</span>';
    }
    if (paletteName === "iagStatus" && lower === "closed") {
        return '<span class="pill pill-neutral">' + esc(s) + '</span>';
    }
    let palette = PILL_PALETTES[paletteName] || {};
    let entry = palette[lower];
    if (!entry) {
        return '<span class="pill pill-neutral">' + esc(s) + '</span>';
    }
    return '<span class="pill" style="background:' + entry.bg + ';color:' + entry.fg + ';">' + esc(s) + '</span>';
}

// pillStyleFor: returns a raw CSS style string for a palette entry, or "" if
// no match. Used by chip-in-header summaries (where we want to style inline
// rather than rebuild a pill).
function pillStyleFor(value, paletteName) {
    let lower = String(value || "").trim().toLowerCase();
    let palette = PILL_PALETTES[paletteName] || {};
    let entry = palette[lower];
    return entry ? ("background:" + entry.bg + ";color:" + entry.fg + ";") : "";
}

// ==================== TABLE BUILDING / SORTING / PERSIST STATE ====================
//
// Every data table in the report is built through a single entry point:
//
//   buildTableHTML(opts) -> HTML string
//     Produces a .data-table with sortable arrow headers, draggable
//     column-resize handles, optional click-to-expand cells, and
//     (when wrap=true && !minimal) a toolbar with a Columns menu,
//     Clear-filters affordance, and per-column filter dropdowns.
//
// Per-header opt-ins / opt-outs:
//   tool: true      -- blue-tinted header background (decision tools)
//   noSort: true    -- suppress sort arrows + click-to-sort on column
//   noFilter: true  -- suppress filter dropdown on column
//   expand: true    -- show column-wide expand icon on column (opt-IN;
//                       default is no expand icon)
//
// Per-table opts:
//   wrap: false     -- emit only the <table>, no surrounding wrappers
//                       or toolbar. Used for tables rendered inside
//                       cell drill-downs (Impact of Issues nested
//                       tables). Suppresses the filter icon in every
//                       header as a side effect, since no dropdown
//                       host exists for clicks to find.
//   minimal: true   -- skip the toolbar (Columns menu, clear filters,
//                       filter dropdowns) for small reference tables
//                       where those affordances would be pure noise.
//                       Suppresses filter icons for the same reason
//                       as wrap=false.
//
// Sort state is persisted per table ID in _tableSortState and re-applied
// on re-render, alongside column-expand, hidden-column, and filter state
// in their respective maps (all keyed on tableId so they survive entity
// switches).

const _tableSortState = {}; // { tableId: {col: number, dir: "asc"|"desc"} }

// Filter-icon glyph. A three-decreasing-lines SVG ("funnel" in abstract
// form) rather than a U+25BE caret, because the caret was visually
// indistinguishable from the sort-descending arrow (same U+25BE
// character in both places), and the ambiguity was especially bad once
// a sort had been applied -- the collapsed sort arrow sat next to the
// filter caret and read as a single ▴▾ pair. The SVG uses
// currentColor so the .th-filter-btn color rules (default / hover /
// active) keep working as-is.
const _FILTER_ICON_SVG = '<svg width="10" height="10" viewBox="0 0 16 16"'
    + ' fill="none" stroke="currentColor" stroke-width="1.8"'
    + ' stroke-linecap="round" aria-hidden="true"'
    + ' style="vertical-align:middle;">'
    + '<path d="M2 4 L14 4"/>'
    + '<path d="M4 8 L12 8"/>'
    + '<path d="M6 12 L10 12"/>'
    + '</svg>';

// Column-wide expand state. Keyed by tableId, value is a Set of column
// indices currently expanded. State survives sort (sort only re-orders
// rows in place; classes on td stay with their tr) and re-render
// (buildTableHTML re-applies the class to matching cells at build time).
const _tableColExpanded = {};
function _isColExpanded(tableId, colIdx) {
    const s = _tableColExpanded[tableId];
    return !!(s && s.has(colIdx));
}
function toggleColExpanded(tableId, colIdx) {
    const table = document.getElementById(tableId);
    if (!table) return;
    let s = _tableColExpanded[tableId];
    if (!s) { s = new Set(); _tableColExpanded[tableId] = s; }
    const isOn = !s.has(colIdx);
    if (isOn) s.add(colIdx); else s.delete(colIdx);
    // :scope > so nested tables inside expanded Impact-of-Issues cells
    // aren't affected by the outer table's column expand.
    const cells = table.querySelectorAll(
        ':scope > tbody > tr > td:nth-child(' + (colIdx + 1) + ')'
    );
    cells.forEach(td => td.classList.toggle('col-expanded-all', isOn));
    const btn = table.querySelector(
        ':scope > thead > tr > th:nth-child(' + (colIdx + 1) + ') .th-expand-btn'
    );
    if (btn) btn.classList.toggle('active', isOn);
}

// Column hide/show state. Keyed by tableId, value is a Set of hidden
// column indices. Same survival semantics as col-expand state.
const _tableColHidden = {};

// Column width state. Keyed by tableId, value is an object mapping
// column index -> width string (e.g. "180px"). Populated by the
// resize handler on mouseup and by double-click auto-fit, read by
// buildTableHTML when emitting <col> style.width values. Survives
// re-render so drag-resize widths persist across entity switches.
const _tableColWidths = {};
function _isColHidden(tableId, colIdx) {
    const s = _tableColHidden[tableId];
    return !!(s && s.has(colIdx));
}
function toggleColHidden(tableId, colIdx, shouldHide) {
    const table = document.getElementById(tableId);
    if (!table) return;
    let s = _tableColHidden[tableId];
    if (!s) { s = new Set(); _tableColHidden[tableId] = s; }
    if (shouldHide) s.add(colIdx); else s.delete(colIdx);
    // Apply to outer-table th, td, and col — scoped to not leak into nested tables.
    const th = table.querySelector(
        ':scope > thead > tr > th:nth-child(' + (colIdx + 1) + ')'
    );
    if (th) th.classList.toggle('col-hidden', shouldHide);
    const cells = table.querySelectorAll(
        ':scope > tbody > tr > td:nth-child(' + (colIdx + 1) + ')'
    );
    cells.forEach(td => td.classList.toggle('col-hidden', shouldHide));
    const col = table.querySelector(
        ':scope > colgroup > col:nth-child(' + (colIdx + 1) + ')'
    );
    if (col) col.classList.toggle('col-hidden', shouldHide);
}
function resetCols(tableId) {
    const s = _tableColHidden[tableId];
    if (s && s.size) {
        const idxs = Array.from(s);
        idxs.forEach(i => toggleColHidden(tableId, i, false));
    }
    // Clear any user-resized widths so the table falls back to
    // header defaults on the next re-render.
    if (_tableColWidths[tableId]) {
        delete _tableColWidths[tableId];
    }
    // Also clear inline col widths and reset table to auto width
    const table = document.getElementById(tableId);
    if (table) {
        table.querySelectorAll(':scope > colgroup > col').forEach(col => {
            col.style.width = '';
        });
        table.style.width = '';
        delete table.dataset.fixedLayout;
    }
    // Uncheck menu checkboxes to match
    const menu = document.getElementById('cols-menu-' + tableId);
    if (menu) {
        menu.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = true);
    }
}
function toggleColsMenu(tableId) {
    const menu = document.getElementById('cols-menu-' + tableId);
    if (!menu) return;
    const isOpen = menu.classList.contains('open');
    // Close any other open cols menu
    document.querySelectorAll('.table-cols-menu.open').forEach(m => m.classList.remove('open'));
    if (!isOpen) menu.classList.add('open');
}
// Click-outside-closes for cols menu
document.addEventListener('mousedown', function(e) {
    if (e.target.closest('.table-cols-menu') || e.target.closest('.table-cols-btn')) return;
    document.querySelectorAll('.table-cols-menu.open').forEach(m => m.classList.remove('open'));
});

// Column filter state. Keyed by tableId, value is {colIdx: Set<string>}
// where the Set holds ALLOWED values. Absence of a colIdx key = no filter
// on that column (all rows pass).
const _tableColFilters = {};

function _cellDisplayText(td) {
    return (td && td.textContent ? td.textContent : '').trim();
}

// Extract individual chip labels from a cell. Used by both:
//   1. buildTableHTML (at build time, on raw cell data with HTML strings)
//   2. _applyAllRowFilters (at runtime, on rendered <td> elements)
// `source` can be a DOM element (<td>) or a raw cell value (string or
// {html: "..."} object). `chipSelector` is a CSS selector like
// ".decision-chip" or ".signal-summary-chip".
function _extractChipLabels(source, chipSelector) {
    let container;
    if (source && source.nodeType === 1) {
        // DOM element — query directly
        container = source;
    } else {
        // Raw cell data — parse HTML
        let html = '';
        if (source && typeof source === 'object' && source.html !== undefined) html = source.html;
        else if (typeof source === 'string') html = source;
        if (!html) return [];
        container = document.createElement('div');
        container.innerHTML = html;
    }
    const chips = container.querySelectorAll(chipSelector);
    if (!chips.length) return [];
    return Array.from(chips).map(c => {
        // First text node = label (excludes <span class="count">, suffixes)
        for (let n = c.firstChild; n; n = n.nextSibling) {
            if (n.nodeType === 3) {
                let t = n.textContent.trim();
                if (t) return t;
            }
        }
        return c.textContent.trim();
    }).filter(Boolean);
}

function _applyAllRowFilters(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;
    const f = _tableColFilters[tableId];
    // Resolve which columns use tag-based filtering by checking the
    // data-filter-chips attribute on each <th>.
    const ths = table.querySelectorAll(':scope > thead > tr > th');
    const chipSelectors = {};
    ths.forEach((th, i) => {
        const sel = th.dataset.filterChips;
        if (sel) chipSelectors[i] = sel;
    });
    const rows = table.querySelectorAll(':scope > tbody > tr');
    rows.forEach(tr => {
        if (!f || Object.keys(f).length === 0) {
            tr.classList.remove('row-hidden');
            return;
        }
        let passes = true;
        for (const k in f) {
            const allowed = f[k];
            if (!allowed || allowed.size === 0) continue;
            const colIdx = parseInt(k, 10);
            const td = tr.children[colIdx];
            if (!td) continue;
            if (chipSelectors[colIdx]) {
                // Tag-based: pass if ANY chip label is in the allowed set
                const tags = _extractChipLabels(td, chipSelectors[colIdx]);
                if (!tags.length || !tags.some(t => allowed.has(t))) {
                    passes = false; break;
                }
            } else {
                if (!allowed.has(_cellDisplayText(td))) { passes = false; break; }
            }
        }
        tr.classList.toggle('row-hidden', !passes);
    });
}

function toggleFilterDropdown(tableId, colIdx, ev) {
    if (ev) ev.stopPropagation();
    const el = document.getElementById('filter-dropdown-' + tableId + '-' + colIdx);
    if (!el) return;
    // Close any other open dropdowns first.
    document.querySelectorAll('.filter-dropdown.open').forEach(d => {
        if (d !== el) d.classList.remove('open');
    });
    if (el.classList.contains('open')) { el.classList.remove('open'); return; }
    // Position below the filter button (fixed positioning, viewport-relative).
    const btn = document.querySelector('#' + tableId
        + ' > thead > tr > th:nth-child(' + (colIdx+1) + ') .th-filter-btn');
    if (btn) {
        const rect = btn.getBoundingClientRect();
        el.style.top = (rect.bottom + 2) + 'px';
        el.style.left = Math.max(4, Math.min(rect.left, window.innerWidth - 360)) + 'px';
    }
    el.classList.add('open');
}

function filterSearchChange(input) {
    const el = input.closest('.filter-dropdown');
    if (!el) return;
    const q = input.value.toLowerCase();
    el.querySelectorAll('.filter-values label').forEach(lbl => {
        const txt = lbl.textContent.toLowerCase();
        lbl.style.display = (!q || txt.indexOf(q) >= 0) ? 'flex' : 'none';
    });
}

function filterSelectAll(input) {
    const el = input.closest('.filter-dropdown');
    if (!el) return;
    el.querySelectorAll('.filter-values input[type="checkbox"]').forEach(cb => {
        if (cb.closest('label').style.display !== 'none') cb.checked = input.checked;
    });
}

function applyColumnFilter(tableId, colIdx) {
    const el = document.getElementById('filter-dropdown-' + tableId + '-' + colIdx);
    if (!el) return;
    const all = new Set();
    const checked = new Set();
    el.querySelectorAll('.filter-values input[type="checkbox"]').forEach(cb => {
        all.add(cb.value);
        if (cb.checked) checked.add(cb.value);
    });
    let f = _tableColFilters[tableId] || {};
    if (checked.size === all.size) {
        delete f[colIdx];
    } else {
        f[colIdx] = checked;
    }
    if (Object.keys(f).length) _tableColFilters[tableId] = f;
    else delete _tableColFilters[tableId];
    _applyAllRowFilters(tableId);
    const btn = document.querySelector('#' + tableId
        + ' > thead > tr > th:nth-child(' + (colIdx+1) + ') .th-filter-btn');
    if (btn) btn.classList.toggle('active', !!(_tableColFilters[tableId] && _tableColFilters[tableId][colIdx]));
    _updateClearFiltersBtn(tableId);
    el.classList.remove('open');
}

function clearAllFilters(tableId) {
    delete _tableColFilters[tableId];
    _applyAllRowFilters(tableId);
    const table = document.getElementById(tableId);
    if (table) {
        table.querySelectorAll(':scope > thead > tr > th .th-filter-btn.active')
            .forEach(b => b.classList.remove('active'));
    }
    // Re-check all checkboxes across all dropdowns for this table.
    document.querySelectorAll('[id^="filter-dropdown-' + tableId + '-"]').forEach(el => {
        el.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = true);
        el.classList.remove('open');
    });
    _updateClearFiltersBtn(tableId);
}

function _updateClearFiltersBtn(tableId) {
    const btn = document.getElementById('clear-filters-' + tableId);
    if (!btn) return;
    const f = _tableColFilters[tableId];
    const hasAny = f && Object.keys(f).length > 0;
    btn.style.display = hasAny ? '' : 'none';
}

// Close open filter dropdowns on outside click (not on the button itself).
document.addEventListener('mousedown', function(e) {
    if (e.target.closest('.filter-dropdown') || e.target.closest('.th-filter-btn')) return;
    document.querySelectorAll('.filter-dropdown.open').forEach(d => d.classList.remove('open'));
}, true);

// Close open filter dropdowns when the user scrolls the page or any
// scrollable ancestor OUTSIDE the dropdown itself. The dropdown is
// position:fixed relative to its filter-btn, so an outer scroll would
// detach it visually. But scrolling INSIDE the dropdown's own
// .filter-values list (the scroll the user is likely doing to find a
// value) must NOT close it -- we guard against that by checking the
// scroll event's target.
window.addEventListener('scroll', function(e) {
    const t = e.target;
    if (t && t.closest && t.closest('.filter-dropdown')) return;
    document.querySelectorAll('.filter-dropdown.open').forEach(d => d.classList.remove('open'));
}, true);

function _normHeader(h, idx) {
    // Accept: "Label" | {label, tool?, width?, type?, noSort?, noFilter?, expand?, filterChips?}
    //
    //   noSort:      true = no sort arrows / no click-to-sort on this column
    //   noFilter:    true = no column-header filter dropdown on this column
    //                       (does not affect the row-filter AND across other
    //                        columns; that still applies)
    //   expand:      true = show the column-wide expand icon on this column.
    //                       Opt-IN -- columns do NOT get expand by default.
    //                       Long-prose columns (descriptions, rationales,
    //                       signals) are the ones worth opting in.
    //   filterChips: CSS selector (e.g. ".decision-chip") — when set,
    //                the filter dropdown shows individual chip labels
    //                extracted via querySelectorAll, not the full cell text.
    if (typeof h === "string") {
        return {label: h, tool: false, width: null, type: "str",
                noSort: false, noFilter: false, expand: false,
                titleTip: null};
    }
    return {
        label: h.label || "",
        tool: !!h.tool,
        width: h.width || null,
        type: h.type || "str",
        noSort: !!h.noSort,
        noFilter: !!h.noFilter,
        expand: !!h.expand,
        filterChips: h.filterChips || null,
        titleTip: h.titleTip || null,
    };
}

// buildTableHTML({id, headers, rows, wrap?, tableClass?, colgroup?}) -> string
//   headers:  Array of string | {label, tool?, width?, type?, noSort?}
//   rows:     Array of Array of HTML strings (one per column)
//   wrap:     default true -- wrap in <div class="table-wrap">
//   tableClass: extra class(es) appended to "data-table"
//   colgroup: optional Array<string> of class names ("c-id"|"c-sev"|"c-status"
//             |"c-title"|""), one per column. Emits a <colgroup> before
//             <thead> so CSS can pin column widths via table-layout:fixed.
//             Takes precedence over per-header `width` hints.
function buildTableHTML(opts) {
    let id = opts.id;
    let headers = (opts.headers || []).map(_normHeader);
    let rows = opts.rows || [];
    let wrap = opts.wrap !== false;
    let extraClass = opts.tableClass ? (" " + opts.tableClass) : "";
    let colgroup = opts.colgroup || null;

    let saved = _tableSortState[id]; // may be undefined
    if (saved) {
        rows = _sortRowsByState(rows, headers, saved);
    }

    // Column-expand + column-hidden + filter state to re-apply at build
    // time (same pattern sort uses). Declared BEFORE colgroup emission
    // because the loop below references _hiddenCls / savedHidden.
    const savedExpanded = _tableColExpanded[id];
    const savedHidden = _tableColHidden[id];
    const savedFilters = _tableColFilters[id];
    const _hiddenCls = (i) => (savedHidden && savedHidden.has(i)) ? ' col-hidden' : '';

    let parts = [];
    // If there are persisted column widths, the table needs an explicit
    // pixel width so table-layout:fixed actually takes effect. We sum
    // the persisted widths and use that as the table width. Without this,
    // re-rendered tables fall back to width:auto and ignore col widths.
    const savedWidths = _tableColWidths[id];
    let tableStyle = '';
    if (savedWidths && Object.keys(savedWidths).length > 0) {
        let totalW = 0;
        headers.forEach((h, i) => {
            const w = savedWidths[i] || h.width || null;
            if (w && w.endsWith('px')) totalW += parseInt(w, 10);
            else totalW += 150; // fallback for columns without explicit px width
        });
        tableStyle = ' style="width:' + totalW + 'px" data-fixed-layout="1"';
    }
    parts.push('<table id="' + id + '" class="data-table' + extraClass + '"');
    if (saved) {
        parts.push(' data-sort-col="' + saved.col + '" data-sort-dir="' + saved.dir + '"');
    }
    parts.push(tableStyle + '>');
    // Always emit a <colgroup> with one <col> per header. This gives
    // the resize handler a stable target (it sets col.style.width on
    // drag), lets the hide-column feature toggle `.col-hidden` on the
    // col element (display:none on a col cascades to every cell in
    // that column), and lets header configs pass explicit widths.
    parts.push('<colgroup>');
    if (colgroup && colgroup.length) {
        // Caller passed a custom colgroup class list (e.g. drill-findings
        // tables using c-id / c-sev / c-status / c-title for widths).
        const savedW1 = _tableColWidths[id] || {};
        colgroup.forEach((cls, i) => {
            const hid = _hiddenCls(i);
            const classes = [];
            if (cls) classes.push(cls);
            if (hid) classes.push('col-hidden');
            const clsAttr = classes.length ? ' class="' + classes.join(' ') + '"' : '';
            const styleAttr = savedW1[i] ? ' style="width:' + savedW1[i] + '"' : '';
            parts.push('<col' + clsAttr + styleAttr + '>');
        });
    } else {
        // Default: one <col> per header. User-resized widths
        // (_tableColWidths) take priority; then h.width (string like
        // "90px" or "25%"); absence means the column gets the browser's
        // default fixed-layout share until the user manually resizes.
        const savedW2 = _tableColWidths[id] || {};
        headers.forEach((h, i) => {
            const hid = _hiddenCls(i);
            const clsAttr = hid ? ' class="col-hidden"' : '';
            const w = savedW2[i] || h.width || null;
            const styleAttr = w ? ' style="width:' + w + '"' : '';
            parts.push('<col' + clsAttr + styleAttr + '>');
        });
    }
    parts.push('</colgroup>');

    // Distinct values per filterable column, for filter dropdown contents.
    function _cellTextForFilter(cell) {
        let src = cell;
        if (cell && typeof cell === 'object' && cell.html !== undefined) src = cell.html;
        if (typeof src !== 'string') src = String(src == null ? '' : src);
        const tmp = document.createElement('div');
        tmp.innerHTML = src;
        return (tmp.textContent || '').trim();
    }
    const distinctByCol = headers.map((h, i) => {
        if (h.noFilter) return null;
        const s = new Set();
        if (h.filterChips) {
            // Tag-based: extract individual chip labels from each cell
            rows.forEach(r => {
                _extractChipLabels(r[i], h.filterChips).forEach(t => s.add(t));
            });
        } else {
            rows.forEach(r => { s.add(_cellTextForFilter(r[i])); });
        }
        return Array.from(s).filter(v => v !== '' && v != null).sort((a,b) => a.localeCompare(b));
    });

    // Filter UI is only emitted when the wrapper that hosts the
    // filter-dropdown <div> elements is also emitted. With wrap=false
    // (nested drill-findings tables) or minimal=true (small reference
    // tables) there IS no dropdown element for a click handler to find,
    // so we suppress the filter icon itself rather than leave a dead
    // click target that silently does nothing.
    const filterUIEnabled = wrap && !opts.minimal;

    parts.push('<thead><tr>');
    headers.forEach((h, i) => {
        let cls = [];
        if (h.tool) cls.push("th-tool");
        if (h.noSort) cls.push("th-nosort");
        let clsAttr = cls.length ? ' class="' + cls.join(" ") + '"' : '';
        let onClick = h.noSort ? "" : ' onclick="sortTable(\'' + id + '\',' + i + ',\'' + h.type + '\')"';
        // Sort arrow lives in its own <span class="th-arrow"> so
        // sortTable() can update its text via textContent without
        // rewriting the surrounding <th> innerHTML. Rewriting innerHTML
        // would risk dropping the expand/filter span elements and their
        // bound onclick handlers, and would also reorder them visually.
        let arrowText = h.noSort ? "" : " \u25B4\u25BE";
        if (saved && saved.col === i) {
            arrowText = saved.dir === "asc" ? " \u25B4" : " \u25BE";
        }
        const arrowHtml = '<span class="th-arrow">' + arrowText + '</span>';
        // Column-wide expand button. Opt-IN per column via {expand: true}
        // on the header config. stopPropagation prevents the click from
        // bubbling to the <th> onclick (which would trigger sort).
        let expandActive = (savedExpanded && savedExpanded.has(i)) ? ' active' : '';
        let expandBtn = h.expand
            ? '<span class="th-expand-btn' + expandActive
              + '" title="Expand column" onclick="event.stopPropagation();toggleColExpanded(\''
              + id + '\',' + i + ');">\u2195</span>'
            : '';
        // Column filter button. Suppressed when (a) the host wrapper
        // won't emit a dropdown, (b) the column opted out via noFilter,
        // or (c) the distinct-value set for this column is empty.
        const filterActive = (savedFilters && savedFilters[i]) ? ' active' : '';
        const canFilter = filterUIEnabled && !h.noFilter
            && distinctByCol[i] && distinctByCol[i].length > 0;
        const filterBtn = canFilter
            ? '<span class="th-filter-btn' + filterActive
              + '" title="Filter column" onclick="toggleFilterDropdown(\''
              + id + '\',' + i + ',event);">' + _FILTER_ICON_SVG + '</span>'
            : '';
        const hiddenTh = _hiddenCls(i);
        if (hiddenTh) clsAttr = ' class="' + (cls.length ? (cls.join(' ') + ' col-hidden') : 'col-hidden') + '"';
        const chipAttr = h.filterChips ? ' data-filter-chips="' + h.filterChips + '"' : '';
        // Optional hover tooltip on the column header (opt-in via
        // {titleTip: "..."} on the header config). Used to disclose the
        // NLP "Needs Review by design" caveat on mapper Mapping Status
        // columns at point of use.
        const titleTipAttr = h.titleTip
            ? ' title="' + String(h.titleTip).replace(/"/g, '&quot;') + '"'
            : '';
        parts.push('<th' + clsAttr + chipAttr + titleTipAttr + onClick + '>' + h.label + arrowHtml
            + expandBtn + filterBtn
            + '<span class="col-resize" onmousedown="startResize(event)" onclick="event.stopPropagation()"></span></th>');
    });
    parts.push('</tr></thead><tbody>');
    // Row-level filter check at build time (state re-applied on re-render).
    function _rowPassesBuildFilters(r) {
        if (!savedFilters) return true;
        for (const k in savedFilters) {
            const allowed = savedFilters[k];
            if (!allowed || allowed.size === 0) continue;
            const idx = parseInt(k, 10);
            const h = headers[idx];
            if (h && h.filterChips) {
                // Tag-based: pass if ANY chip label is in the allowed set
                const tags = _extractChipLabels(r[idx], h.filterChips);
                if (!tags.length || !tags.some(t => allowed.has(t))) return false;
            } else {
                if (!allowed.has(_cellTextForFilter(r[idx]))) return false;
            }
        }
        return true;
    }
    rows.forEach(r => {
        const passes = _rowPassesBuildFilters(r);
        parts.push(passes ? '<tr>' : '<tr class="row-hidden">');
        r.forEach((cell, colIdx) => {
            // Cell may be a plain HTML string OR an object
            //   {html: "...", tdClass: "cell-signals"}
            // which lets the caller put a class on the <td> itself
            // (used for Risk Profile "Additional Signals" chip cells).
            const expandCls = (savedExpanded && savedExpanded.has(colIdx)) ? 'col-expanded-all' : '';
            const hiddenClsTd = _hiddenCls(colIdx) ? 'col-hidden' : '';
            const extras = [expandCls, hiddenClsTd].filter(Boolean).join(' ');
            if (cell && typeof cell === "object" && cell.html !== undefined) {
                const baseCls = cell.tdClass || '';
                const combined = (baseCls + (extras ? ' ' + extras : '')).trim();
                const cls = combined ? ' class="' + combined + '"' : '';
                parts.push('<td' + cls + '>' + cell.html + '</td>');
            } else {
                const cls = extras ? ' class="' + extras + '"' : '';
                parts.push('<td' + cls + '>' + cell + '</td>');
            }
        });
        parts.push('</tr>');
    });
    parts.push('</tbody></table>');

    let html = parts.join("");
    if (wrap) html = '<div class="table-wrap">' + html + '</div>';

    // Toolbar + Columns menu + per-column filter dropdowns. Skipped
    // when opts.minimal is true (small reference tables where these
    // affordances would be pure noise) or when wrap is false (nested
    // drill-findings tables that render inline inside an expanded
    // cell -- no outer wrapper to host a toolbar).
    if (wrap && !opts.minimal) {
        let menuHtml = '<div class="table-cols-menu" id="cols-menu-' + id + '">';
        menuHtml += '<div class="cols-menu-header">Show/hide columns</div>';
        headers.forEach((h, i) => {
            const isHidden = savedHidden && savedHidden.has(i);
            const checked = isHidden ? '' : ' checked';
            menuHtml += '<label><input type="checkbox"' + checked
                + ' onchange="toggleColHidden(\'' + id + '\',' + i + ',!this.checked)"> '
                + (h.label || ('Col ' + (i+1))) + '</label>';
        });
        menuHtml += '<div class="cols-menu-footer"><button onclick="resetCols(\'' + id + '\')">Reset</button></div>';
        menuHtml += '</div>';

        // Per-column filter dropdowns (one div per filterable column).
        let filterDropdowns = '';
        headers.forEach((h, i) => {
            if (h.noFilter || !distinctByCol[i] || distinctByCol[i].length === 0) return;
            const selected = (savedFilters && savedFilters[i]) || null;
            let body = '<input type="text" class="filter-search" placeholder="Search values..." oninput="filterSearchChange(this)">';
            body += '<label class="filter-select-all"><input type="checkbox" checked onchange="filterSelectAll(this)"> (Select all)</label>';
            body += '<div class="filter-values">';
            distinctByCol[i].forEach(v => {
                const isChecked = !selected || selected.has(v);
                const safeVal = (v + '').replace(/"/g, '&quot;');
                body += '<label><input type="checkbox" value="' + safeVal + '"'
                    + (isChecked ? ' checked' : '') + '> ' + safeVal + '</label>';
            });
            body += '</div>';
            body += '<div class="filter-actions">'
                + '<button onclick="document.getElementById(\'filter-dropdown-' + id + '-' + i + '\').classList.remove(\'open\');">Cancel</button>'
                + '<button class="primary" onclick="applyColumnFilter(\'' + id + '\',' + i + ');">Apply</button>'
                + '</div>';
            filterDropdowns += '<div class="filter-dropdown" id="filter-dropdown-' + id + '-' + i + '">' + body + '</div>';
        });

        const hasAnyFilter = !!(savedFilters && Object.keys(savedFilters).length > 0);
        const clearBtn = '<button class="table-toolbar-btn" id="clear-filters-' + id + '"'
            + ' style="' + (hasAnyFilter ? '' : 'display:none;') + '"'
            + ' onclick="clearAllFilters(\'' + id + '\')">Clear filters</button>';

        const toolbar = '<div class="table-toolbar">'
            + '<button class="table-toolbar-btn table-cols-btn" onclick="toggleColsMenu(\'' + id + '\')">Columns \u25BE</button>'
            + clearBtn
            + menuHtml
            + '</div>';
        html = '<div class="table-outer">' + toolbar + html + filterDropdowns + '</div>';
    }
    return html;
}

// makeTable was the legacy entry point that wrote into a pre-allocated
// <table> element in the static HTML body. It could only emit the
// <table> innerHTML, never the surrounding .table-outer wrapper that
// holds the toolbar + filter dropdowns, so the two flagship tables it
// served (entity-profile-table, risk-entity-table) silently lacked
// filter functionality even though filter icons rendered in their
// headers. Both callers now build into a host <div> via
// buildTableHTML(wrap: true) and this function has been removed.

function _sortRowsByState(rows, headers, state) {
    let col = state.col, dir = state.dir;
    let type = (headers[col] && headers[col].type) || "str";
    let asc = dir === "asc";
    let copy = rows.slice();
    copy.sort((a, b) => {
        let va = _cellSortValue(a[col]);
        let vb = _cellSortValue(b[col]);
        if (type === "num") { va = parseFloat(va) || 0; vb = parseFloat(vb) || 0; }
        if (va < vb) return asc ? -1 : 1;
        if (va > vb) return asc ? 1 : -1;
        return 0;
    });
    return copy;
}

function _cellSortValue(cellHtml) {
    // Strip tags and normalize whitespace so pills/spans sort by their text.
    // Unwrap object-form cells ({html, tdClass}) before extracting text.
    let src = cellHtml;
    if (src && typeof src === "object" && src.html !== undefined) src = src.html;
    let tmp = document.createElement("div");
    tmp.innerHTML = String(src || "");
    return (tmp.textContent || "").trim();
}

function sortTable(tableId, col, type) {
    let table = document.getElementById(tableId);
    if (!table) return;
    let currentCol = table.dataset.sortCol;
    let currentDir = table.dataset.sortDir;
    let dir;
    if (currentCol === String(col)) {
        dir = currentDir === "asc" ? "desc" : "asc";
    } else {
        dir = "asc";
    }
    _tableSortState[tableId] = {col: col, dir: dir};

    // Re-sort the existing DOM rows in place. IMPORTANT: use :scope selectors
    // so we only touch the OUTER table's rows. Cells can contain nested tables
    // (e.g. Risk Profile "Impact of Issues" expands into IAG/ORE/PRSA/RAP
    // tables) and an unscoped "tbody tr" would hoist their rows into the
    // outer sort.
    let tbody = table.querySelector(":scope > tbody");
    if (!tbody) return;
    let bodyRows = Array.from(tbody.children).filter(el => el.tagName === "TR");
    let asc = dir === "asc";
    bodyRows.sort((a, b) => {
        let va = a.cells[col].textContent.trim();
        let vb = b.cells[col].textContent.trim();
        if (type === "num") { va = parseFloat(va) || 0; vb = parseFloat(vb) || 0; }
        if (va < vb) return asc ? -1 : 1;
        if (va > vb) return asc ? 1 : -1;
        return 0;
    });
    table.dataset.sortCol = String(col);
    table.dataset.sortDir = dir;
    bodyRows.forEach(r => tbody.appendChild(r));

    // Update arrow indicators on the OUTER thead only. Nested tables
    // have their own thead which we must not touch, hence the :scope >
    // chain. We target the dedicated .th-arrow span in each <th> so
    // this is a pure textContent update -- no innerHTML rewrite, no
    // risk of stripping the expand/filter button spans or their
    // onclick handlers.
    let ths = table.querySelectorAll(":scope > thead > tr > th");
    ths.forEach((th, i) => {
        let arrowSpan = th.querySelector(":scope > .th-arrow");
        if (!arrowSpan) return;
        let arrow;
        if (i === col) arrow = asc ? " \u25B4" : " \u25BE";
        else if (th.classList.contains("th-nosort")) arrow = "";
        else arrow = " \u25B4\u25BE";
        arrowSpan.textContent = arrow;
    });
}

// ==================== CELL CLICK-TO-EXPAND (scoped to .data-table) ====================
// Two distinct click-to-expand contracts share this listener:
//   .cell-signals  — Risk Profile "Additional Signals" cell. Toggles the
//                    `expanded` class; swaps chip-summary <-> full detail.
//   .cell-expanded — default data-table cell overflow expander. Generic
//                    yellow-highlight toggle for any other wide cell.
// A td.cell-signals NEVER gets .cell-expanded (different styling contracts).
document.addEventListener("click", function(e) {
    if (e.target.tagName === "A") return;
    if (e.target.classList && e.target.classList.contains("col-resize")) return;
    // Tail end of a drag-select: don't yank the cell closed mid-copy.
    const _sel = window.getSelection && window.getSelection();
    if (_sel && _sel.toString().length > 0) return;
    let summaryTd = e.target.closest(
        "td.cell-signals, td.cell-decision-basis, td.cell-impact, td.cell-l2-name"
    );
    if (summaryTd) {
        summaryTd.classList.toggle("expanded");
        return;
    }
    let td = e.target.closest(".data-table td");
    if (!td) return;
    td.classList.toggle("cell-expanded");
});

// ==================== COLUMN RESIZE ====================
// IMPORTANT: the base table CSS uses width:auto, which means
// table-layout:fixed is NOT active by default (per the CSS spec,
// fixed layout requires an explicit width). This is intentional --
// auto lets the browser size columns by content for initial render.
//
// When the user grabs a resize handle, _ensureFixedLayout() converts
// the table to an explicit pixel width, freezes every column's
// rendered width into its <col> element, and only THEN does
// table-layout:fixed take effect. From that point, col.style.width
// changes are authoritative.
//
// During drag, the table's overall width grows by the same delta as
// the column, so other columns keep their widths (Excel-like behavior)
// and .table-wrap shows a horizontal scrollbar if needed.

let _resizeTh = null, _resizeColEl = null, _resizeStartX = 0, _resizeStartW = 0;
let _resizeTableId = null, _resizeColIdx = -1;
let _resizeTable = null, _resizeTableStartW = 0;
// One-shot suppression: when a resize finishes, the browser may still fire
// a click on the underlying <th> (which has onclick=sortTable). This flag
// tells the capture-phase listener below to consume that next click so it
// never reaches the th's sort handler.
let _suppressNextClick = false;

function _resolveResizeTargets(handle) {
    const th = handle.parentElement;
    const tr = th && th.parentElement;
    if (!th || !tr) return null;
    const thIdx = Array.prototype.indexOf.call(tr.children, th);
    const table = th.closest('table');
    const colEl = table && table.querySelector(
        ':scope > colgroup > col:nth-child(' + (thIdx + 1) + ')'
    );
    if (!colEl) return null;
    return { th: th, colEl: colEl, thIdx: thIdx, table: table };
}

// Freeze a table to explicit pixel width + pixel column widths.
// This activates table-layout:fixed (which requires width != auto)
// and locks every column to its current rendered width so switching
// layout mode doesn't cause columns to jump.
function _ensureFixedLayout(table) {
    if (table.dataset.fixedLayout) return; // already frozen
    const ths = table.querySelectorAll(':scope > thead > tr > th');
    const cols = table.querySelectorAll(':scope > colgroup > col');
    // Snapshot rendered widths BEFORE setting explicit table width
    const widths = [];
    ths.forEach(th => widths.push(th.offsetWidth));
    // Set explicit table width (activates table-layout:fixed)
    table.style.width = table.offsetWidth + 'px';
    // Freeze each column to its rendered width
    widths.forEach((w, i) => {
        if (cols[i]) cols[i].style.width = w + 'px';
    });
    table.dataset.fixedLayout = '1';
}

function startResize(e) {
    e.stopPropagation();
    e.preventDefault();
    const info = _resolveResizeTargets(e.target);
    if (!info) return;
    // Activate fixed layout if not already active
    _ensureFixedLayout(info.table);
    _resizeTh = info.th;
    _resizeColEl = info.colEl;
    _resizeColIdx = info.thIdx;
    _resizeTable = info.table;
    _resizeTableId = info.table.id || null;
    _resizeStartX = e.pageX;
    _resizeStartW = info.th.offsetWidth;
    _resizeTableStartW = info.table.offsetWidth;
    e.target.classList.add("active");
    document.body.classList.add("col-resizing");
    document.addEventListener("mousemove", doResize);
    document.addEventListener("mouseup", stopResize);
}
function doResize(e) {
    if (!_resizeColEl || !_resizeTable) return;
    const delta = e.pageX - _resizeStartX;
    const colW = Math.max(40, _resizeStartW + delta);
    _resizeColEl.style.width = colW + "px";
    // Grow table by same delta so other columns don't squeeze
    const tableW = Math.max(_resizeTableStartW, _resizeTableStartW + delta);
    _resizeTable.style.width = tableW + "px";
}
function stopResize(e) {
    // Persist final column width so it survives re-renders
    if (_resizeColEl && _resizeTableId) {
        const finalW = _resizeColEl.style.width;
        if (finalW) {
            if (!_tableColWidths[_resizeTableId]) _tableColWidths[_resizeTableId] = {};
            _tableColWidths[_resizeTableId][_resizeColIdx] = finalW;
        }
    }
    if (_resizeTh) {
        const handle = _resizeTh.querySelector(".col-resize");
        if (handle) handle.classList.remove("active");
    }
    document.body.classList.remove("col-resizing");
    _resizeTh = null;
    _resizeColEl = null;
    _resizeTable = null;
    _resizeTableId = null;
    _resizeColIdx = -1;
    document.removeEventListener("mousemove", doResize);
    document.removeEventListener("mouseup", stopResize);
    // Consume the click event the browser may fire next (target = th, which
    // would trigger sortTable). Reset asynchronously so legitimate clicks
    // afterward still work.
    _suppressNextClick = true;
    setTimeout(function() { _suppressNextClick = false; }, 0);
}

// Capture-phase swallower: catches the post-resize click before it bubbles
// to the th's onclick=sortTable. Only fires once per resize.
document.addEventListener("click", function(e) {
    if (_suppressNextClick) {
        e.stopPropagation();
        e.preventDefault();
        _suppressNextClick = false;
    }
}, true);

// ==================== DOUBLE-CLICK AUTO-FIT ====================
// Double-clicking a resize handle auto-sizes the column to fit its
// widest content, similar to Excel's auto-fit behavior. Activates
// fixed layout, measures natural content widths using an off-screen
// probe, then applies the max to the <col> and grows the table.
function autoFitColumn(e) {
    e.stopPropagation();
    e.preventDefault();
    const info = _resolveResizeTargets(e.target);
    if (!info) return;
    const { th, colEl, thIdx, table } = info;
    const tableId = table.id || null;

    // Activate fixed layout if not already active
    _ensureFixedLayout(table);

    const oldColW = th.offsetWidth;

    // Measure header text width
    const probe = document.createElement('span');
    probe.style.cssText = 'position:absolute;visibility:hidden;white-space:nowrap;'
        + 'font:' + getComputedStyle(th).font + ';padding:0 24px;';
    document.body.appendChild(probe);
    probe.textContent = th.textContent.replace(/[\u25B4\u25BE\u2195]/g, '').trim();
    let maxW = probe.offsetWidth + 8; // +8 for sort/expand/filter icons

    // Measure each visible cell in this column
    const cells = table.querySelectorAll(
        ':scope > tbody > tr:not(.row-hidden) > td:nth-child(' + (thIdx + 1) + ')'
    );
    const cellStyle = cells.length ? getComputedStyle(cells[0]) : null;
    if (cellStyle) {
        probe.style.font = cellStyle.font;
        probe.style.padding = '0 24px';
    }
    cells.forEach(td => {
        probe.textContent = (td.textContent || '').trim();
        if (probe.offsetWidth > maxW) maxW = probe.offsetWidth;
    });
    document.body.removeChild(probe);

    // Clamp to reasonable bounds
    const fitW = Math.max(60, Math.min(maxW, 800));
    colEl.style.width = fitW + 'px';

    // Grow/shrink table by the column width delta
    const tableW = table.offsetWidth + (fitW - oldColW);
    table.style.width = Math.max(tableW, 200) + 'px';

    // Persist
    if (tableId) {
        if (!_tableColWidths[tableId]) _tableColWidths[tableId] = {};
        _tableColWidths[tableId][thIdx] = fitW + 'px';
    }
}

// Attach dblclick handler to all resize handles (event delegation)
document.addEventListener('dblclick', function(e) {
    if (e.target.classList && e.target.classList.contains('col-resize')) {
        autoFitColumn(e);
    }
});

// Expander state persistence. When a caller provides a stable `key`, we
// remember the user's last explicit open/closed choice for that key so it
// survives a re-render (e.g. after a filter change). Expanders without a
// key are stateless and always fall back to their default.
const _expanderUserState = {}; // { key: true (open) | false (closed) }

function toggleExpander(el) {
    let exp = el.closest(".expander");
    let wasOpen = exp.classList.contains("open");
    exp.classList.toggle("open");
    let key = exp.dataset.key;
    if (key) _expanderUserState[key] = !wasOpen;
    if (!wasOpen && exp.dataset.lazy) {
        let bodyEl = exp.querySelector(".expander-body");
        let fn = window["_lazy_" + exp.dataset.lazy];
        if (fn && !exp.dataset.rendered) {
            bodyEl.innerHTML = fn();
            exp.dataset.rendered = "1";
        }
    }
}

// mkExpander(defaultOpen, headerLabel, bodyHtml, key?)
//   defaultOpen: open/closed state used when the user hasn't interacted
//   key:         optional stable ID. When provided, the user's last
//                explicit toggle choice for this key survives re-render.
function mkExpander(defaultOpen, headerLabel, bodyHtml, key) {
    let effectiveOpen = defaultOpen;
    if (key && Object.prototype.hasOwnProperty.call(_expanderUserState, key)) {
        effectiveOpen = _expanderUserState[key];
    }
    let cls = effectiveOpen ? "expander open" : "expander";
    let keyAttr = key ? ' data-key="' + esc(key) + '"' : "";
    return '<div class="' + cls + '"' + keyAttr + '><div class="expander-header" onclick="toggleExpander(this)">'
        + '<span>' + headerLabel + '</span><span class="expander-arrow">\u25B6</span>'
        + '</div><div class="expander-body">' + bodyHtml + '</div></div>';
}

function formatOverview(raw, id) {
    let text = String(raw || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    if (!text.trim()) return "";
    let rawLen = text.length;
    let blocks = text.split(/\n\s*\n+/).map(b => b.trim()).filter(Boolean);
    if (!blocks.length) return "";

    let bulletRe = /^\s*(?:[\u2022\-\*]|\d+[.)])\s+/;
    let mdRowRe = /^\s*\|?\s*([^|]*\|\s*)+\|?\s*$/;
    let mdSepRe = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/;

    function renderProse(block) {
        let joined = block.split("\n").map(l => l.trim()).filter(Boolean).join(" ");
        return "<p>" + esc(joined) + "</p>";
    }

    function tryMarkdownTable(block) {
        let lines = block.split("\n").map(l => l.trim()).filter(Boolean);
        if (lines.length < 2) return null;
        let matches = lines.filter(l => mdRowRe.test(l)).length;
        if (matches / lines.length < 0.6) return null;
        let rows = [];
        for (let l of lines) {
            if (mdSepRe.test(l)) continue;
            if (!mdRowRe.test(l)) continue;
            let parts = l.split("|").map(c => c.trim());
            while (parts.length && parts[0] === "") parts.shift();
            while (parts.length && parts[parts.length - 1] === "") parts.pop();
            if (parts.length) rows.push(parts);
        }
        if (!rows.length) return null;
        let ncols = rows[0].length;
        if (ncols < 2) return null;
        let headers = rows[0];
        let body = rows.slice(1);
        let html = '<table class="overview-table"><thead><tr>';
        for (let h of headers) html += "<th>" + esc(h) + "</th>";
        html += "</tr></thead><tbody>";
        for (let r of body) {
            html += "<tr>";
            for (let i = 0; i < ncols; i++) {
                let cell = i < r.length ? r[i] : "";
                html += "<td>" + esc(cell) + "</td>";
            }
            html += "</tr>";
        }
        html += "</tbody></table>";
        return html;
    }

    function tryBulletList(block) {
        let lines = block.split("\n").map(l => l.trim()).filter(Boolean);
        if (lines.length < 2) return null;
        if (!lines.every(l => bulletRe.test(l))) return null;
        let items = lines.map(l => "<li>" + esc(l.replace(bulletRe, "").trim()) + "</li>").join("");
        return '<ul class="overview-list">' + items + "</ul>";
    }

    function isHeaderLike(s) {
        if (!s) return false;
        let t = s.trim();
        if (!t) return false;
        if (/^\d{4}\b/.test(t)) return true;
        if (/\(.+\)/.test(t)) return true;
        if (/[a-zA-Z]/.test(t) && t === t.toUpperCase() && /[A-Z]/.test(t)) return true;
        if (/^[A-Z]/.test(t) && t.length < 30 && !/[.!?]\s*$/.test(t)) return true;
        return false;
    }

    function classify(block) {
        try {
            let md = tryMarkdownTable(block);
            if (md) return {type: "html", html: md};
        } catch (e) {}
        try {
            let bl = tryBulletList(block);
            if (bl) return {type: "html", html: bl};
        } catch (e) {}
        let lines = block.split("\n").map(l => l.trim()).filter(Boolean);
        if (lines.length === 1) {
            let t = lines[0];
            if (t.length < 80 && !/[.!?]\s*$/.test(t)) {
                return {type: "short-line", text: t, headerLike: isHeaderLike(t)};
            }
        }
        return {type: "prose", block: block};
    }

    function renderExportedTableRun(cells) {
        try {
            for (let n = Math.min(6, cells.length - 1); n >= 2; n--) {
                if (cells.length < 2 * n) continue;
                let firstN = cells.slice(0, n);
                let allHeader = firstN.every(c => isHeaderLike(c));
                if (!allHeader) continue;
                let distinct = new Set(firstN.map(c => c.toLowerCase())).size === n;
                if (!distinct) continue;
                let html = '<table class="overview-table"><thead><tr>';
                for (let h of firstN) html += "<th>" + esc(h) + "</th>";
                html += "</tr></thead><tbody>";
                let body = cells.slice(n);
                for (let i = 0; i < body.length; i += n) {
                    html += "<tr>";
                    for (let j = 0; j < n; j++) {
                        let v = i + j < body.length ? body[i + j] : "";
                        let out = v === "-" ? "\u2014" : v;
                        html += "<td>" + esc(out) + "</td>";
                    }
                    html += "</tr>";
                }
                html += "</tbody></table>";
                return html;
            }
            if (cells.length >= 4 && cells.length % 2 === 0) {
                let html = '<dl class="overview-dl">';
                for (let i = 0; i < cells.length; i += 2) {
                    html += "<dt>" + esc(cells[i]) + "</dt>";
                    html += "<dd>" + esc(cells[i + 1]) + "</dd>";
                }
                html += "</dl>";
                return html;
            }
            let items = cells.map(c => "<li>" + esc(c) + "</li>").join("");
            return '<ul class="overview-list">' + items + "</ul>";
        } catch (e) {
            return "<p>" + esc(cells.join(" \u00b7 ")) + "</p>";
        }
    }

    let classified;
    try {
        classified = blocks.map(classify);
    } catch (e) {
        return "<p>" + esc(text) + "</p>";
    }

    let merged = [];
    let i = 0;
    while (i < classified.length) {
        let item = classified[i];
        if (item.type === "short-line") {
            let j = i;
            let run = [];
            while (j < classified.length && classified[j].type === "short-line") {
                run.push(classified[j].text);
                j++;
            }
            if (run.length >= 6) {
                merged.push({type: "html", html: renderExportedTableRun(run)});
            } else {
                for (let k = 0; k < run.length; k++) {
                    merged.push({type: "html", html: "<p>" + esc(run[k]) + "</p>"});
                }
            }
            i = j;
            continue;
        }
        if (item.type === "html") {
            merged.push(item);
        } else {
            try {
                merged.push({type: "html", html: renderProse(item.block)});
            } catch (e) {
                merged.push({type: "html", html: "<p>" + esc(item.block) + "</p>"});
            }
        }
        i++;
    }

    if (!merged.length) return "";
    let rendered = merged.map(m => m.html);

    let truncate = rawLen > 800 && rendered.length > 2;
    if (!truncate) return rendered.join("");
    let tid = "overview-more-" + id;
    return rendered.slice(0, 2).join("") +
        '<div id="' + tid + '" style="display:none;">' + rendered.slice(2).join("") + '</div>' +
        '<a href="javascript:void(0)" class="overview-toggle" onclick="toggleOverview(\'' + tid + '\', this)">Show more</a>';
}

function toggleOverview(id, el) {
    let div = document.getElementById(id);
    let hidden = div.style.display === "none";
    div.style.display = hidden ? "block" : "none";
    el.textContent = hidden ? "Show less" : "Show more";
}

function severitySummary(rows, getVal, order) {
    let counts = {};
    rows.forEach(r => {
        let v = String(getVal(r) || "").trim();
        if (!v || v.toLowerCase() === "nan") return;
        counts[v] = (counts[v] || 0) + 1;
    });
    if (!Object.keys(counts).length) return "";
    let parts = [];
    order.forEach(label => {
        if (counts[label]) {
            parts.push(counts[label] + " " + label);
            delete counts[label];
        }
    });
    Object.keys(counts).forEach(k => parts.push(counts[k] + " " + k));
    return " \u2014 " + parts.join(", ");
}

// ================================================================
// SIGNAL RENDERING
// ================================================================
// Signals are parsed into: leading [TAG] (rendered as a chip), statement
// body, inline ID lists (rendered mono/tertiary), and a trailing em-dash
// action hint (rendered secondary). Control contradictions ("well controlled
// but ... review whether") get alert styling instead.
// parseSignalsForRender: pure parser. Returns
//   { orderedKeys, groupMap, contradictions }
// or null when signals are empty / yield no groups or contradictions.
// No HTML emission — shared by the drill-down full renderer and the
// Risk Profile cell chip-summary renderer.
function parseSignalsForRender(signals) {
    if (isEmpty(signals)) return null;
    let raw = String(signals);
    if (!raw.trim()) return null;

    // Split by newline-line first, then by " | " inside each line, so we know
    // which atoms share a newline-line and can inherit a leading [TAG].
    let lines = raw.split(/\n/);
    let atoms = [];
    lines.forEach(line => {
        let pieces = line.split(" | ").map(s => s.trim()).filter(Boolean);
        pieces.forEach((piece, idx) => {
            atoms.push({ raw: piece, isContinuation: idx > 0 });
        });
    });

    // Second-pass split: some inputs glue two tagged atoms together without
    // " | " (e.g. "...applicable [Aux] Listed..."). Split at " [Tag] "
    // boundaries. Leading-space requirement avoids matching prose like
    // "see [Exhibit A]".
    let rebuilt = [];
    atoms.forEach(a => {
        let rest = a.raw;
        const tagBoundary = /\s\[[A-Za-z][A-Za-z0-9 \-]*\]\s/g;
        let cuts = [];
        let m;
        while ((m = tagBoundary.exec(rest)) !== null) {
            cuts.push(m.index);
        }
        if (!cuts.length) {
            rebuilt.push(a);
            return;
        }
        let parts = [];
        let lastCut = 0;
        cuts.forEach(idx => {
            let segment = rest.substring(lastCut, idx).trim();
            if (segment) parts.push(segment);
            lastCut = idx + 1;
        });
        let tail = rest.substring(lastCut).trim();
        if (tail) parts.push(tail);
        parts.forEach((p, i) => {
            rebuilt.push({
                raw: p,
                isContinuation: i === 0 ? a.isContinuation : false,
            });
        });
    });
    atoms = rebuilt;

    const ID_LIST_RE = /^[A-Z]{2,5}-?\d+(\s*[;,]\s*[A-Z]{2,5}-?\d+)+$/;
    const ID_TOKEN_RE = /^[A-Z]{2,5}-?\d+$/;

    let parsed = [];
    let lastTagOnLine = null;
    let prevWasContinuation = false;
    atoms.forEach(a => {
        if (!a.isContinuation) lastTagOnLine = null;

        let s = a.raw;
        let lower = s.toLowerCase();
        if (lower.includes("well controlled but") || lower.includes("review whether")) {
            parsed.push({ kind: "contradiction", text: s });
            return;
        }

        let body = s;
        let tag = null;
        let tagMatch = body.match(/^\[([^\]]+)\]\s*/);
        if (tagMatch) {
            tag = tagMatch[1].trim();
            body = body.substring(tagMatch[0].length);
            if (!a.isContinuation) lastTagOnLine = tag;
        } else if (a.isContinuation && lastTagOnLine) {
            tag = lastTagOnLine;
        }

        let hint = "";
        let emIdx = body.indexOf("\u2014");
        if (emIdx >= 0) {
            hint = body.substring(emIdx + 1).trim();
            body = body.substring(0, emIdx).trim();
        }

        // Scan ALL parenthesized groups; collect IDs from any paren whose
        // inner text is a ID-list (2+ ID-shaped tokens separated by ; or ,).
        let ids = [];
        let cleaned = "";
        let i = 0;
        while (i < body.length) {
            let open = body.indexOf("(", i);
            if (open < 0) { cleaned += body.substring(i); break; }
            let close = body.indexOf(")", open);
            if (close < 0) { cleaned += body.substring(i); break; }
            let inner = body.substring(open + 1, close).trim();
            if (ID_LIST_RE.test(inner)) {
                inner.split(/\s*[;,]\s*/).forEach(tok => {
                    tok = tok.trim();
                    if (tok && ID_TOKEN_RE.test(tok)) ids.push(tok);
                });
                // drop the paren (and the single space that may precede it)
                let pre = body.substring(i, open);
                if (pre.endsWith(" ")) pre = pre.slice(0, -1);
                cleaned += pre;
                i = close + 1;
                // also swallow a redundant space immediately after the drop
                if (body[i] === " ") i += 1;
            } else {
                cleaned += body.substring(i, close + 1);
                i = close + 1;
            }
        }
        body = cleaned.replace(/\s+/g, " ").trim();

        parsed.push({ kind: "signal", tag: tag, body: body, hint: hint, ids: ids });
    });

    // Grouping: ordered by priority list, then unknown tags (insertion order),
    // then untagged last.
    const ORDER = ["Applicability", "App", "TP", "Model", "Core", "Aux"];
    let groupMap = {}; // tag -> { tag, label, items }
    let insertionOrder = [];
    parsed.filter(p => p.kind === "signal").forEach(p => {
        let key = p.tag || "__untagged__";
        if (!groupMap[key]) {
            groupMap[key] = { tag: p.tag, items: [] };
            insertionOrder.push(key);
        }
        groupMap[key].items.push(p);
    });

    let orderedKeys = [];
    ORDER.forEach(t => { if (groupMap[t]) orderedKeys.push(t); });
    insertionOrder.forEach(k => {
        if (k === "__untagged__") return;
        if (orderedKeys.indexOf(k) < 0) orderedKeys.push(k);
    });
    if (groupMap["__untagged__"]) orderedKeys.push("__untagged__");

    // Per-group shared-hint hoist
    orderedKeys.forEach(k => {
        let g = groupMap[k];
        if (g.items.length === 0) { g.sharedHint = ""; return; }
        let first = g.items[0].hint;
        if (first && g.items.every(it => it.hint === first)) {
            g.sharedHint = first;
            g.items.forEach(it => { it.hint = ""; });
        } else {
            g.sharedHint = "";
        }
    });

    let contradictions = parsed.filter(p => p.kind === "contradiction");
    if (!contradictions.length && !orderedKeys.length) return null;
    return { orderedKeys: orderedKeys, groupMap: groupMap, contradictions: contradictions };
}

// Emit the drill-down-style inner HTML for a parsed signals payload.
// Does NOT include the outer .drill-section / "Additional Signals" label
// wrapper — that's added only by renderSignalsFullHTML. This inner HTML
// is what the Risk Profile cell reuses inside .signals-detail.
//
// eid (optional): when provided, id-chips under [App] and [TP] groups are
// marked .id-chip-key if they're in the entity's "key" inventory set.
function _renderSignalsInnerHTML(parsed, eid) {
    let html = "";
    parsed.contradictions.forEach(p => {
        html += '<div class="signal-contradiction">\ud83d\udea8 <span>' + esc(p.text) + '</span></div>';
    });
    parsed.orderedKeys.forEach(k => {
        let g = parsed.groupMap[k];
        let isUntagged = (k === "__untagged__");
        html += '<div class="signal-group">';
        html += '<div class="signal-group-header">';
        if (isUntagged) {
            html += '<span class="signal-tag">Other</span>';
        } else {
            let slug = String(g.tag || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
            html += '<span class="signal-tag signal-tag-' + slug + '">' + esc(g.tag) + '</span>';
        }
        if (g.sharedHint) {
            html += '<span class="signal-group-hint">' + esc(g.sharedHint) + '</span>';
        }
        html += '</div>';
        html += '<ul class="signal-list">';
        const tag = g.tag;
        const isApp = tag === "App";
        const isTp = tag === "TP";
        g.items.forEach(it => {
            html += '<li class="signal-item">';
            html += '<span class="signal-body">' + esc(it.body) + '</span>';
            if (it.hint) {
                html += '<span class="signal-hint-inline">\u2014 ' + esc(it.hint) + '</span>';
            }
            if (it.ids && it.ids.length) {
                html += '<span class="signal-ids">';
                it.ids.forEach(id => {
                    let cls = "id-chip";
                    if (eid && isApp && isKeyApp(eid, id)) cls += " id-chip-key";
                    else if (eid && isTp && isKeyTp(eid, id)) cls += " id-chip-key";
                    html += '<span class="' + cls + '">' + esc(id) + '</span>';
                });
                html += '</span>';
            }
            html += '</li>';
        });
        html += '</ul>';
        html += '</div>';
    });
    return html;
}

// Full drill-down renderer: emits the same HTML that the original
// renderSignals returned, wrapped in <div class="drill-section">
// with the "Additional Signals" label.
function renderSignalsFullHTML(parsed, eid) {
    let html = '<div class="drill-section"><span class="label">Additional Signals</span>';
    html += _renderSignalsInnerHTML(parsed, eid);
    html += '</div>';
    return html;
}

// Risk Profile cell renderer: emits a chip summary + a hidden detail
// block. The enclosing <td class="cell-signals"> is added by the caller
// so expand/collapse toggles on the td. Returns "" for empty.
function renderSignalsForCell(parsed, eid) {
    let summaryHtml = '<span class="signals-summary">';
    parsed.orderedKeys.forEach(k => {
        let g = parsed.groupMap[k];
        let label = (k === "__untagged__") ? "Other" : g.tag;
        let slug = String(label || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
        // Collect deduped IDs across all items in this group. The chip count
        // reports distinct IDs (e.g. App x3 when one signal entry references
        // APP-001, APP-002, APP-003), not the number of signal entries.
        let allIds = [];
        g.items.forEach(it => { if (it.ids) allIds = allIds.concat(it.ids); });
        let dedupedIds = Array.from(new Set(allIds));
        let count = dedupedIds.length || g.items.length;
        summaryHtml += '<span class="signal-summary-chip signal-summary-chip-' + slug + '">'
            + esc(label) + '<span class="count">\u00d7' + count + '</span></span>';
    });
    if (parsed.contradictions.length) {
        summaryHtml += '<span class="signal-summary-chip" style="background:#f8d7da;color:#721c24;">'
            + '\u26a0<span class="count">\u00d7' + parsed.contradictions.length + '</span></span>';
    }
    summaryHtml += '<span class="signals-expand-hint">click to expand</span></span>';

    let detailHtml = '<div class="signals-detail">';
    detailHtml += _renderSignalsInnerHTML(parsed, eid);
    detailHtml += '<span class="signals-collapse-hint">click to collapse</span>';
    detailHtml += '</div>';

    return summaryHtml + detailHtml;
}

// Thin back-compat wrapper retained for drill-down callers.
function renderSignals(signals, eid) {
    let parsed = parseSignalsForRender(signals);
    return parsed ? renderSignalsFullHTML(parsed, eid) : "";
}

// ================================================================
// DECISION / CONTEXT SECTION RENDERERS
// ================================================================
function renderDecisionBasis(row, status) {
    let basis = row["Decision Basis"] || "";
    if (isEmpty(basis)) return "";
    // Applicable -> ok banner, Undetermined -> warn banner, other ->
    // info banner, except Not Assessed which gets a muted plain section.
    let cls = "banner-info";
    if (status === "Applicable") cls = "banner-ok";
    else if (status === "Applicability Undetermined") cls = "banner-warn";
    else if (status === "Not Assessed") {
        return '<div class="drill-section"><span class="label">Decision Basis</span><div>' + esc(basis) + '</div></div>';
    }
    return '<div class="banner ' + cls + '"><strong>Decision Basis</strong><br>' + esc(basis) + '</div>';
}

function renderSiblingMatches(row, entityDetailRows) {
    let legacySource = String(row["Legacy Source"] || "");
    if (!entityDetailRows || isEmpty(legacySource)) return "";
    let bp = basePillar(legacySource);
    let matched = entityDetailRows.filter(d =>
        String(d["source_legacy_pillar"]||"").includes(bp) &&
        !String(d["method"]||"").includes("no_evidence_all_candidates") &&
        !String(d["method"]||"").includes("evaluated_no_evidence")
    );
    if (!matched.length) return "";
    let html = '<div class="drill-section"><span class="label">Other L2s from ' + esc(bp) + ' that DID match</span>';
    matched.forEach(m => { html += '<div>\u2022 \u2705 ' + esc(m["new_l2"]) + '</div>'; });
    html += '</div>';
    return html;
}

function renderKeyRiskDescriptions(detailRow, eid, l2) {
    if (!detailRow || isEmpty(eid) || isEmpty(l2)) return "";
    let pillar = basePillar(detailRow["source_legacy_pillar"]||"");
    if (isEmpty(pillar)) return "";
    let es = subRisksData.filter(s => {
        let sEid = String(s["entity_id"]||s["Audit Entity"]||s["Audit Entity ID"]||"");
        let sL1 = String(s["legacy_l1"]||s["Level 1 Risk Category"]||"");
        if (sEid !== String(eid) || sL1 !== pillar) return false;
        let matches = String(s["L2 Keyword Matches"]||s["Contributed To (keyword matches)"]||"");
        let contributedTo = matches.split(";").map(x => x.trim().replace(/\s*\(.*/, ""));
        return contributedTo.includes(l2);
    });
    if (!es.length) return "";
    let html = '<div class="drill-section"><span class="label">Sub-risks that contributed evidence for this L2</span>';
    es.forEach(s => {
        let rid = s["risk_id"]||s["Key Risk ID"]||"";
        let desc = String(s["risk_description"]||s["Key Risk Description"]||"").substring(0,200);
        html += '<div class="subrisk-row"><span class="id-chip">' + esc(String(rid)) + '</span><span class="subrisk-name">' + esc(desc) + '</span></div>';
    });
    html += '</div>';
    return html;
}

function renderSourceRationale(detailRow) {
    if (!detailRow) return "";
    let rat = detailRow["source_rationale"] || "";
    if (isEmpty(rat)) return "";
    return '<div class="drill-section"><span class="label">Source Rationale</span><blockquote>' + esc(rat) + '</blockquote></div>';
}

function renderSectionHeader(labelText, summaryInner) {
    if (!summaryInner) return '<span class="label">' + esc(labelText) + '</span>';
    return '<div class="drill-header-row">'
        + '<span class="label" style="margin-bottom:0;">' + esc(labelText) + '</span>'
        + '<span class="drill-header-summary">' + summaryInner + '</span>'
        + '</div>';
}

function _countBySeverity(items, getSev) {
    let counts = {};
    items.forEach(it => {
        let s = String(getSev(it)||"").trim();
        if (!s) return;
        counts[s] = (counts[s] || 0) + 1;
    });
    return counts;
}

function _orderedSevPills(counts, order, paletteName) {
    let pills = order
        .filter(sev => counts[sev] > 0)
        .map(sev => {
            let style = pillStyleFor(sev, paletteName);
            if (style) {
                return '<span class="pill" style="' + style + '">' + counts[sev] + ' ' + esc(sev) + '</span>';
            }
            return '<span class="pill pill-neutral">' + counts[sev] + ' ' + esc(sev) + '</span>';
        });
    Object.keys(counts).forEach(sev => {
        if (order.includes(sev) || counts[sev] <= 0) return;
        pills.push('<span class="pill pill-neutral">' + counts[sev] + ' ' + esc(sev) + '</span>');
    });
    return pills;
}

// ================================================================
// EVIDENCE SECTION (unified)
// ================================================================
// Replaces renderRelevantFindings / renderRelevantOREs /
// renderRelevantPRSA / renderRelevantRAPs. Callers pre-filter data into a
// normalized shape {id, title, severity?, status?} and pass config here.
//
// cfg fields:
//   label            - section heading ("IAG Issues", etc.)
//   rows             - normalized rows to render
//   idLabel          - table header for ID column (default "ID")
//   titleLabel       - table header for title column (default "Title")
//   severityLabel    - table header for severity column (default "Severity")
//   statusLabel      - table header for status column (default "Status")
//   severityOrder    - array for ordering severity pills in header summary
//   severityPalette  - palette name for severity pills ("severity",
//                      "oreClass", etc.)
//   hasSeverity      - bool (falsy means omit severity column/pill)
//   hasStatus        - bool (falsy means omit status column/pill)
//   emptyMessage     - if provided, render empty section with this note
//                      instead of returning ""
//   contradictionWarning - optional HTML string shown above the content
//                          (used by IAG for the "well controlled" flag)
function renderEvidenceSection(cfg) {
    let rows = cfg.rows || [];
    let label = cfg.label;

    if (!rows.length) {
        if (cfg.emptyMessage) {
            return '<div class="drill-section">'
                + '<span class="label">' + esc(label) + '</span>'
                + '<div class="drill-inline-meta">' + esc(cfg.emptyMessage) + '</div>'
                + '</div>';
        }
        return "";
    }

    let hasSev = cfg.hasSeverity !== false;
    let hasStatus = cfg.hasStatus !== false;
    let sevPalette = cfg.severityPalette || "severity";

    // Sub-section header: label only — count pills removed. The severity
    // column in the table below already communicates the same information,
    // so duplicating it in the header was noisy.
    let html = '<div class="drill-section">' + renderSectionHeader(label, "");

    if (cfg.contradictionWarning) {
        html += cfg.contradictionWarning;
    }

    // Column order: ID, severity, status, title. Rating/status pills sit
    // directly after the ID so the auditor scans them first; the title
    // takes the remaining width. Widths pinned via <colgroup>.
    let headers = [{label: cfg.idLabel || "ID"}];
    let colClasses = ["c-id"];
    if (hasSev) {
        headers.push({label: cfg.severityLabel || "Severity"});
        colClasses.push("c-sev");
    }
    if (hasStatus) {
        headers.push({label: cfg.statusLabel || "Status"});
        colClasses.push("c-status");
    }
    headers.push({label: cfg.titleLabel || "Title"});
    colClasses.push("c-title");

    let tableId = cfg.tableId || ("evtbl-" + Math.random().toString(36).slice(2, 8));
    let tableRows = rows.map(r => {
        let row = ['<span class="id-chip">' + esc(String(r.id || "")) + '</span>'];
        if (hasSev) row.push(makePill(r.severity || "", sevPalette));
        if (hasStatus) row.push(makePill(r.status || "", "iagStatus"));
        row.push(esc(String(r.title || "")));
        return row;
    });
    html += buildTableHTML({
        id: tableId,
        headers: headers,
        rows: tableRows,
        wrap: false,
        tableClass: "drill-findings-table",
        colgroup: colClasses,
    });
    html += '</div>';
    return html;
}

// ================================================================
// EVIDENCE SECTION -- thin wrappers per data source
// Each wrapper: filter + normalize, then delegate to renderEvidenceSection.
// ================================================================

function worstOpenIagSeverity(eid, l2) {
    if (isEmpty(eid) || isEmpty(l2)) return null;
    let ef = findingsData.filter(f => {
        let fEid = String(f["entity_id"]||f["Audit Entity ID"]||"");
        let fL2 = String(f["l2_risk"]||f["Mapped To L2(s)"]||f["Risk Dimension Categories"]||"");
        return fEid === String(eid) && fL2.includes(l2) && isActiveIagStatus(f["status"]||f["Finding Status"]);
    });
    let sevs = ef.map(f => String(f["severity"]||f["Final Reportable Finding Risk Rating"]||"").toLowerCase());
    if (sevs.some(s => s.includes("critical"))) return "Critical";
    if (sevs.some(s => s.includes("high"))) return "High";
    return null;
}

function renderRelevantFindings(row, eid, l2) {
    if (isEmpty(eid) || isEmpty(l2)) return "";
    let ef = findingsData.filter(f => {
        let fEid = String(f["entity_id"]||f["Audit Entity ID"]||"");
        let fL2 = String(f["l2_risk"]||f["Mapped To L2(s)"]||f["Risk Dimension Categories"]||"");
        return fEid === String(eid) && fL2.includes(l2) && isActiveIagStatus(f["status"]||f["Finding Status"]);
    });

    let rows = ef.map(f => ({
        id: f["issue_id"]||f["Finding ID"]||"",
        title: f["issue_title"]||f["Finding Name"]||"",
        severity: f["severity"]||f["Final Reportable Finding Risk Rating"]||"",
        status: f["status"]||f["Finding Status"]||"",
    }));

    // Note: the "Well Controlled but open Critical/High finding" contradiction
    // warning now renders inside renderControlAssessment (next to the rating
    // it questions) rather than above the IAG Issues table.

    return renderEvidenceSection({
        label: "IAG Issues",
        rows: rows,
        severityOrder: ["Critical","High","Medium","Low"],
        severityPalette: "severity",
        emptyMessage: "No IAG issues tagged to this L2.",
    });
}

function renderRelevantOREs(eid, l2) {
    if (isEmpty(eid) || isEmpty(l2) || !oreData.length) return "";
    let seen = new Set();
    let eo = [];
    oreData.forEach(o => {
        if (oreRowEid(o) !== normId(eid)) return;
        let mappedList = String(o["Mapped L2s"]||o["l2_risk"]||"").split(/[;\r\n]+/).map(s => s.trim());
        if (!mappedList.includes(l2)) return;
        let evid = String(o["Event ID"]||"").trim();
        let key = evid || (String(o["Event Title"]||"").trim() + "|" + String(o["Event Description"]||"").trim());
        if (key && key !== "|") {
            if (seen.has(key)) return;
            seen.add(key);
        }
        eo.push(o);
    });
    let rows = eo.map(o => ({
        id: o["Event ID"]||"",
        title: o["Event Title"]||"",
        severity: o["Final Event Classification"]||"",
        status: o["Event Status"]||"",
    }));
    return renderEvidenceSection({
        label: "Operational Risk Events",
        rows: rows,
        severityLabel: "Class",
        severityOrder: ["Class A","Class B","Class C"],
        severityPalette: "oreClass",
    });
}

function renderRelevantPRSA(eid, l2) {
    if (isEmpty(eid) || isEmpty(l2) || !prsaData.length) return "";
    let eidCol = resolveCol(prsaData, ["AE ID", "Audit Entity ID"]);
    if (!eidCol) return "";
    // Deduplicate by Issue ID -- a single issue may appear as multiple
    // control rows.
    let seen = new Set();
    let ep = [];
    prsaData.forEach(p => {
        let pEid = String(p[eidCol]||"").trim();
        if (pEid !== String(eid)) return;
        let mappedList = String(p["Mapped L2s"]||"").split(/[;\r\n]+/).map(s => s.trim());
        if (!mappedList.includes(l2)) return;
        let iid = String(p["Issue ID"]||"").trim();
        if (iid && seen.has(iid)) return;
        if (iid) seen.add(iid);
        ep.push(p);
    });
    let rows = ep.map(p => ({
        id: p["Issue ID"]||"",
        title: p["Issue Title"]||"",
        severity: p["Issue Rating"]||"",
        status: p["Issue Status"]||"",
    }));
    return renderEvidenceSection({
        label: "PRSA Issues",
        rows: rows,
        severityLabel: "Rating",
        severityOrder: ["Critical","High","Medium","Low"],
        severityPalette: "severity",
    });
}

function renderRelevantRAPs(eid, l2) {
    if (isEmpty(eid) || isEmpty(l2) || !graRapsData.length) return "";
    let eidCol = resolveCol(graRapsData, ["Audit Entity ID"]);
    if (!eidCol) return "";
    let er = graRapsData.filter(g => {
        let gEid = String(g[eidCol]||"").trim();
        if (gEid !== String(eid)) return false;
        let mappedList = String(g["Mapped L2s"]||"").split(/[;\r\n]+/).map(s => s.trim());
        return mappedList.includes(l2);
    });
    let rows = er.map(g => ({
        id: g["RAP ID"]||"",
        title: g["RAP Header"]||"",
        status: g["RAP Status"]||"",
    }));
    return renderEvidenceSection({
        label: "GRA RAPs",
        rows: rows,
        idLabel: "ID",
        titleLabel: "Header",
        hasSeverity: false,
    });
}

// ================================================================
// DECISION BASIS + IMPACT OF ISSUES — Risk Profile cell renderers
// ================================================================
// Method substring -> chip slug. Mirrors _derive_decision_type in
// review_builders.py; order is most-specific-first so e.g. "llm_confirmed_na"
// doesn't match inside a method string containing "direct".
const _DECISION_CHIP_MAP = [
    ["llm_confirmed_na",           "ai-na"],
    ["source_not_applicable",      "legacy-na"],
    ["evaluated_no_evidence",      "assumed-na"],
    ["no_evidence_all_candidates", "undetermined"],
    ["true_gap_fill",              "gap"],
    ["gap_fill",                   "gap"],
    ["llm_override",               "ai-applied"],
    ["issue_confirmed",            "issue"],
    ["evidence_match",             "keyword"],
    ["direct",                     "direct"],
];
function decisionChipSlug(method) {
    let m = String(method || "");
    for (let i = 0; i < _DECISION_CHIP_MAP.length; i++) {
        if (m.indexOf(_DECISION_CHIP_MAP[i][0]) >= 0) return _DECISION_CHIP_MAP[i][1];
    }
    return "";
}

// Matching findings for the issue-confirmed chip. Same filter contract as
// renderRelevantFindings so the id-chip row matches what drill-down shows.
function _issueConfirmedFindingIds(eid, l2) {
    if (isEmpty(eid) || isEmpty(l2)) return [];
    return findingsData.filter(f => {
        let fEid = String(f["entity_id"]||f["Audit Entity ID"]||"");
        let fL2 = String(f["l2_risk"]||f["Mapped To L2(s)"]||f["Risk Dimension Categories"]||"");
        return fEid === String(eid) && fL2.indexOf(l2) >= 0
            && isActiveIagStatus(f["status"]||f["Finding Status"]);
    }).map(f => String(f["issue_id"]||f["Finding ID"]||"")).filter(Boolean);
}

// Decision Basis cell: chip summary + full-prose detail.
function renderDecisionBasisCell(row, eid, l2) {
    let prose = String(row["Decision Basis"] || "");
    let method = String(row["Method"] || "");
    let label = String(row["Decision Type"] || "");
    if (isEmpty(prose) && isEmpty(label)) return "";

    let slug = decisionChipSlug(method);
    if (!slug && !label) return prose ? esc(prose) : "";

    let summaryHtml = '<span class="decision-summary">';
    if (slug) {
        summaryHtml += '<span class="decision-chip decision-chip-' + slug + '">'
            + esc(label || slug) + '</span>';
    }

    // Issue Confirmed: append matching finding id-chips
    if (slug === "issue") {
        let ids = _issueConfirmedFindingIds(eid, l2);
        let shown = ids.slice(0, 3);
        shown.forEach(id => {
            summaryHtml += '<span class="id-chip">' + esc(id) + '</span>';
        });
        if (ids.length > shown.length) {
            summaryHtml += '<span class="meta" style="font-size:11px;">+'
                + (ids.length - shown.length) + ' more</span>';
        }
    }

    summaryHtml += '</span>';

    let detailHtml = '<div class="decision-detail">' + esc(prose) + '</div>';
    return { html: summaryHtml + detailHtml, tdClass: "cell-decision-basis" };
}

// L2 name cell renderer: plain L2 name as summary, full L2 Definition
// (with rolled-up L3/L4 sub-definitions where applicable) as the detail.
// Reuses the "L2 Definition" column from Audit_Review, which review_builders
// already populates with the L2 def + L3 sub-entries (e.g. External Fraud
// shows the parent L2 def followed by First Party / Victim Fraud L3 defs).
function renderL2NameCell(row) {
    const l2 = String(row["New L2"] || "").trim();
    if (!l2) return "";
    const definition = String(row["L2 Definition"] || "").trim();
    const summaryHtml = '<span class="l2-name-summary">' + esc(l2) + '</span>';
    // If there's no definition (not yet populated, or reference file missing),
    // fall back to plain text — no click-to-expand affordance.
    if (!definition) return esc(l2);
    const detailHtml = '<div class="l2-name-detail">' + esc(definition) + '</div>';
    return { html: summaryHtml + detailHtml, tdClass: "cell-l2-name" };
}

// Worst severity slug for an Impact of Issues source group. Maps all four
// source types onto a common critical|high|medium|low palette for summary
// chip colouring. ORE classes follow the amendment: A=critical, B=high,
// C=medium, Near Miss=low.
function _worstImpactSeverity(rows, severityGetter, classMap) {
    let best = null;
    let rank = {critical: 4, high: 3, medium: 2, low: 1};
    rows.forEach(r => {
        let raw = String(severityGetter(r) || "").trim();
        let slug = classMap ? classMap[raw.toLowerCase()] : null;
        if (!slug) {
            let lower = raw.toLowerCase();
            if (lower.indexOf("critical") >= 0) slug = "critical";
            else if (lower.indexOf("high") >= 0) slug = "high";
            else if (lower.indexOf("medium") >= 0) slug = "medium";
            else if (lower.indexOf("low") >= 0) slug = "low";
        }
        if (!slug) return;
        if (!best || rank[slug] > rank[best]) best = slug;
    });
    return best || "none";
}

function _iagImpactItems(eid, l2) {
    if (isEmpty(eid) || isEmpty(l2)) return [];
    return findingsData.filter(f => {
        let fEid = String(f["entity_id"]||f["Audit Entity ID"]||"");
        let fL2 = String(f["l2_risk"]||f["Mapped To L2(s)"]||f["Risk Dimension Categories"]||"");
        return fEid === String(eid) && fL2.indexOf(l2) >= 0
            && isActiveIagStatus(f["status"]||f["Finding Status"]);
    });
}
function _oreImpactItems(eid, l2) {
    if (isEmpty(eid) || isEmpty(l2) || !oreData.length) return [];
    let seen = new Set();
    let out = [];
    oreData.forEach(o => {
        if (oreRowEid(o) !== normId(eid)) return;
        // IRM OREs: only those both Open AND Material feed Impact of Issues.
        // Closed and Non-Material OREs stay on the source listing for traceability.
        if (String(o["ore_source"]||"").toUpperCase() === "IRM") {
            if (String(o["ORE Status"]||"").trim().toLowerCase() !== "open") return;
            if (String(o["ORE Materiality"]||"").trim().toLowerCase() === "non-material") return;
        }
        let mapped = String(o["Mapped L2s"]||o["l2_risk"]||"").split(/[;\r\n]+/).map(s => s.trim());
        if (mapped.indexOf(l2) < 0) return;
        let evid = String(o["Event ID"]||"").trim();
        let key = evid || (String(o["Event Title"]||"").trim() + "|" + String(o["Event Description"]||"").trim());
        if (key && key !== "|") {
            if (seen.has(key)) return;
            seen.add(key);
        }
        out.push(o);
    });
    return out;
}
function _prsaImpactItems(eid, l2) {
    if (isEmpty(eid) || isEmpty(l2) || !prsaData.length) return [];
    let eidCol = resolveCol(prsaData, ["AE ID", "Audit Entity ID"]);
    if (!eidCol) return [];
    let seen = new Set();
    let out = [];
    prsaData.forEach(p => {
        if (String(p[eidCol]||"").trim() !== String(eid)) return;
        let pgFlag = String(p["Is PG Gap"]||"").trim().toLowerCase();
        if (pgFlag === "yes" || pgFlag === "true" || pgFlag === "1") return;
        let mapped = String(p["Mapped L2s"]||"").split(/[;\r\n]+/).map(s => s.trim());
        if (mapped.indexOf(l2) < 0) return;
        let id = String(p["Issue ID"]||"").trim();
        if (id && seen.has(id)) return;
        if (id) seen.add(id);
        out.push(p);
    });
    return out;
}
// Track C: PG Gap items keyed off the prsaData source. A PG Gap is any
// Issue whose `Is PG Gap` flag is truthy. We reuse prsaData rather than
// pgGapData here because prsaData is the per-row exploded view that
// participates in the same Mapped L2s / per-entity attribution as the
// other sources. Unmapped PG gaps live only in pgGapData (no AE) and are
// surfaced via the banner + Source - PG Gaps tab.
function _pgGapsImpactItems(eid, l2) {
    if (isEmpty(eid) || isEmpty(l2) || !prsaData.length) return [];
    let eidCol = resolveCol(prsaData, ["AE ID", "Audit Entity ID"]);
    if (!eidCol) return [];
    function _isPg(v) {
        let s = String(v||"").trim().toLowerCase();
        return s === "yes" || s === "true" || s === "1";
    }
    let seen = new Set();
    let out = [];
    prsaData.forEach(p => {
        if (!_isPg(p["Is PG Gap"])) return;
        if (String(p[eidCol]||"").trim() !== String(eid)) return;
        let mapped = String(p["Mapped L2s"]||"").split(/[;\r\n]+/).map(s => s.trim());
        if (mapped.indexOf(l2) < 0) return;
        let id = String(p["Issue ID"]||"").trim();
        if (id && seen.has(id)) return;
        if (id) seen.add(id);
        out.push(p);
    });
    return out;
}
function _rapImpactItems(eid, l2) {
    if (isEmpty(eid) || isEmpty(l2) || !graRapsData.length) return [];
    let eidCol = resolveCol(graRapsData, ["Audit Entity ID"]);
    if (!eidCol) return [];
    return graRapsData.filter(g => {
        if (String(g[eidCol]||"").trim() !== String(eid)) return false;
        let mapped = String(g["Mapped L2s"]||"").split(/[;\r\n]+/).map(s => s.trim());
        return mapped.indexOf(l2) >= 0;
    });
}

// Impact of Issues cell: collapsed = single chip showing total + worst
// severity (colored by worst severity), plus a small per-source breakdown.
// Expanded = unified table where every issue is a row with a Source column,
// PLUS a stacked-row layout for narrow widths (CSS container query in
// .impact-detail picks which to display). This replaces the old design of
// stacking three or four near-identical sub-tables, which made narrow
// columns clip the rightmost columns silently and obscured the existence
// of secondary sources entirely.
function renderImpactForCell(row, eid, l2) {
    let iag = _iagImpactItems(eid, l2);
    let ores = _oreImpactItems(eid, l2);
    let prsa = _prsaImpactItems(eid, l2);
    let raps = _rapImpactItems(eid, l2);
    let pgGaps = _pgGapsImpactItems(eid, l2);
    if (!iag.length && !ores.length && !prsa.length && !raps.length && !pgGaps.length) return "";

    const _ORE_CLASS_MAP = {
        "class a": "critical", "class b": "high",
        "class c": "medium",   "near miss": "low",
    };
    const _RANK = {critical: 4, high: 3, medium: 2, low: 1, none: 0};
    function _slugFor(raw, classMap) {
        let s = String(raw||"").toLowerCase();
        if (classMap && classMap[s]) return classMap[s];
        if (s.indexOf("critical") >= 0) return "critical";
        if (s.indexOf("high") >= 0)     return "high";
        if (s.indexOf("medium") >= 0)   return "medium";
        if (s.indexOf("low") >= 0)      return "low";
        return "none";
    }

    // Normalize all four sources into a single shape so the expanded
    // panel can render them as one unified list. RAPs carry no severity
    // in the source data — their cell renders as an em-dash.
    let items = [];
    iag.forEach(f => {
        let sev = f["severity"] || f["Final Reportable Finding Risk Rating"] || "";
        items.push({
            sourceLabel: "IAG", srcClass: "impact-src-iag",
            id:    f["issue_id"]    || f["Finding ID"]    || "",
            title: f["issue_title"] || f["Finding Name"]  || "",
            severity: sev, sevPalette: "severity",
            sevSlug: _slugFor(sev, null),
            status: f["status"] || f["Finding Status"] || "",
        });
    });
    ores.forEach(o => {
        let sev = o["Final Event Classification"] || "";
        items.push({
            sourceLabel: "ORE", srcClass: "impact-src-ore",
            id:    o["Event ID"]    || "",
            title: o["Event Title"] || "",
            severity: sev, sevPalette: "oreClass",
            sevSlug: _slugFor(sev, _ORE_CLASS_MAP),
            status: o["Event Status"] || "",
        });
    });
    prsa.forEach(p => {
        let sev = p["Issue Rating"] || "";
        // Track B: IRM-Archer-tagged vs mapper-inferred L2 provenance per
        // issue. Excel stores user-facing labels ("IRM Archer" / "Inferred"),
        // but CSS / tooltip logic keys off internal tokens ("source" /
        // "mapper") so we normalize here.
        let l2srcRaw = String(p["L2 Source"]||"").trim().toLowerCase();
        let l2src = "";
        if (l2srcRaw === "irm archer" || l2srcRaw === "source") l2src = "source";
        else if (l2srcRaw === "inferred" || l2srcRaw === "mapper") l2src = "mapper";
        items.push({
            sourceLabel: "PRSA", srcClass: "impact-src-prsa",
            id:    p["Issue ID"]    || "",
            title: p["Issue Title"] || "",
            severity: sev, sevPalette: "severity",
            sevSlug: _slugFor(sev, null),
            status: p["Issue Status"] || "",
            l2Source: l2src,
        });
    });
    raps.forEach(g => {
        items.push({
            sourceLabel: "RAP", srcClass: "impact-src-rap",
            id:    g["RAP ID"]     || "",
            title: g["RAP Header"] || "",
            severity: "", sevPalette: "severity", sevSlug: "none",
            status: g["RAP Status"] || "",
        });
    });
    // Track C: PG Gap items. Carries the data-source attribute (audit-leader
    // picks the visual). Severity follows the issue's Issue Rating, same as
    // the PRSA pill — so a High-rated PG Gap shows up in the high-severity
    // tier of the collapsed-view chip.
    pgGaps.forEach(p => {
        let sev = p["Issue Rating"] || "";
        items.push({
            sourceLabel: "PG", srcClass: "impact-src-pg-gap",
            id:    p["Issue ID"]    || "",
            title: p["Issue Title"] || "",
            severity: sev, sevPalette: "severity",
            sevSlug: _slugFor(sev, null),
            status: p["Issue Status"] || "",
            dataSource: "pg-gap",
        });
    });

    // Sort: severity desc, then source label, then id — gives reviewers
    // the highest-severity issues at the top regardless of source.
    items.sort((a, b) => {
        let ra = _RANK[a.sevSlug] || 0;
        let rb = _RANK[b.sevSlug] || 0;
        if (ra !== rb) return rb - ra;
        if (a.sourceLabel !== b.sourceLabel) return a.sourceLabel < b.sourceLabel ? -1 : 1;
        return String(a.id) < String(b.id) ? -1 : 1;
    });

    // Collapsed view: one chip per source type, colored by that source's
    // worst severity. Restored from the pre-refactor design — auditors
    // wanted to see at a glance which sources contribute issues without
    // expanding the cell.
    let summaryHtml = '<span class="impact-summary">';
    function _sourceChip(label, sourceItems, sevGetter, classMap) {
        if (!sourceItems.length) return;
        let sev = _worstImpactSeverity(sourceItems, sevGetter, classMap);
        summaryHtml += '<span class="signal-summary-chip signal-summary-chip-impact-' + sev + '">'
            + esc(label) + '<span class="count">×' + sourceItems.length + '</span></span>';
    }
    _sourceChip("IAG",  iag,  f => f["severity"] || f["Final Reportable Finding Risk Rating"]);
    _sourceChip("OREs", ores, o => o["Final Event Classification"], _ORE_CLASS_MAP);
    _sourceChip("PRSA", prsa, p => p["Issue Rating"]);
    // Track C: PG Gap collapsed-view chip. Audit-leader picks final wording
    // / styling. Currently uses the same signal-summary-chip class as the
    // others — visual differentiation comes from the data-source attribute
    // on the expanded-row source pill (see _srcPill below).
    _sourceChip("PG Gaps", pgGaps, p => p["Issue Rating"]);
    _sourceChip("RAPs", raps, g => g["severity"] || "");
    summaryHtml += '<span class="signals-expand-hint">click to expand</span></span>';

    // Helpers for both layouts.
    function _sevCell(it) {
        if (!it.severity) return '<span class="sev-empty">\u2014</span>';
        return makePill(it.severity, it.sevPalette);
    }
    function _statusCell(it) {
        if (!it.status) return '<span class="sev-empty">\u2014</span>';
        return makePill(it.status, "iagStatus");
    }
    function _srcPill(it) {
        // Track B: emit data-l2-source on the source pill when available so
        // CSS can paint a solid (IRM Archer) or dashed (mapper-inferred)
        // border. Tooltip explains the distinction on hover. Only PRSA chips
        // carry l2Source; IAG/ORE/RAP have no provenance attribute.
        let dataAttr = it.l2Source ? ' data-l2-source="' + esc(it.l2Source) + '"' : '';
        // Track C: emit data-source on the source pill so audit-leader's CSS
        // pass can target the PG Gap pill specifically. Currently only PG
        // Gap items set this; other sources rely on srcClass.
        let dataSrcAttr = it.dataSource ? ' data-source="' + esc(it.dataSource) + '"' : '';
        let titleAttr = '';
        if (it.l2Source === "source") {
            titleAttr = ' title="L2 from IRM Archer"';
        } else if (it.l2Source === "mapper") {
            titleAttr = ' title="L2 inferred from issue text — re-read the issue to validate"';
        } else if (it.dataSource === "pg-gap") {
            titleAttr = ' title="PG gap — issue flagged with #PG / PG in IRM Archer"';
        }
        return '<span class="impact-src ' + it.srcClass + '"' + dataAttr + dataSrcAttr + titleAttr + '>' + esc(it.sourceLabel) + '</span>';
    }

    // Layout A: unified table (wide).
    let tableRows = items.map(it => {
        let rowAttr = it.l2Source ? ' data-l2-source="' + esc(it.l2Source) + '"' : '';
        // Track C: PG-gap rows carry data-source so styling / filters can
        // target them at the row level (audit-leader pass).
        if (it.dataSource) rowAttr += ' data-source="' + esc(it.dataSource) + '"';
        return '<tr' + rowAttr + '>'
        + '<td class="col-source">' + _srcPill(it) + '</td>'
        + '<td class="col-id">'     + esc(String(it.id))    + '</td>'
        + '<td class="col-sev">'    + _sevCell(it)          + '</td>'
        + '<td class="col-status">' + _statusCell(it)       + '</td>'
        + '<td class="col-title">'  + esc(String(it.title)) + '</td>'
        + '</tr>';
    }).join("");
    let tableHtml = '<div class="impact-table-layout">'
        + '<table class="impact-unified-table">'
        +   '<thead><tr>'
        +     '<th class="col-source">Source</th>'
        +     '<th class="col-id">ID</th>'
        +     '<th class="col-sev">Severity</th>'
        +     '<th class="col-status">Status</th>'
        +     '<th class="col-title">Title</th>'
        +   '</tr></thead>'
        +   '<tbody>' + tableRows + '</tbody>'
        + '</table>'
        + '</div>';

    // Layout B: stacked rows (narrow). Each item is a 2-line entry —
    // pills row on top (wraps), title on the next line (wraps freely).
    let stackHtml = '<div class="impact-stack-layout">'
        + items.map(it => {
            let itemAttr = it.l2Source ? ' data-l2-source="' + esc(it.l2Source) + '"' : '';
            if (it.dataSource) itemAttr += ' data-source="' + esc(it.dataSource) + '"';
            return '<div class="impact-stack-item"' + itemAttr + '>'
            + '<div class="impact-stack-meta">'
                + _srcPill(it)
                + '<span class="id-mono">' + esc(String(it.id)) + '</span>'
                + _sevCell(it)
                + _statusCell(it)
            + '</div>'
            + '<div class="impact-stack-title">' + esc(String(it.title)) + '</div>'
            + '</div>';
        }).join("")
        + '</div>';

    let detailHtml = '<div class="impact-detail">'
        + tableHtml
        + stackHtml
        + '<span class="signals-collapse-hint">click to collapse</span>'
        + '</div>';

    return { html: summaryHtml + detailHtml, tdClass: "cell-impact" };
}

// ================================================================
// CONTROL ASSESSMENT
// ================================================================
function renderControlAssessment(row, eid, l2) {
    let baseline = row["Control Effectiveness Baseline"] || "";
    if (isAbsence(baseline)) return "";

    let m = String(baseline).match(/^(.+?) \(Last audit: (.+?), (.+?) \u00b7 Next planned: (.+?)\)$/);
    let rating = m ? m[1].trim() : String(baseline).trim();
    let auditResult = m ? m[2].trim() : "";
    let auditDate = m ? m[3].trim() : "";
    let nextDate = m ? m[4].trim() : "";
    let isPh = v => !v || v === "date unknown" || v === "not scheduled" || v.toLowerCase() === "nan";

    let html = '<div class="drill-section"><span class="label">Control Assessment</span>';
    let segments = [];
    if (!isPh(auditResult)) segments.push("Last audit " + auditResult);
    if (!isPh(auditDate)) segments.push(auditDate);
    if (!isPh(nextDate)) segments.push("next planned " + nextDate);
    let contextText = segments.join(" \u00b7 ");

    html += '<div>'
        + '<span style="margin-right:8px;">' + makePill(rating, "controlRating") + '</span>'
        + (contextText ? '<span style="font-size:13px;color:var(--gray);">' + esc(contextText) + '</span>' : "")
        + '</div>';

    // Contradiction note: "Well Controlled" rating but an open Critical/High
    // IAG finding on this L2 — nudge the auditor to re-confirm the rating.
    let ratingText = String(baseline).split("(")[0].trim();
    if (/^well controlled/i.test(ratingText) && worstOpenIagSeverity(eid, l2)) {
        html += '<div class="ca-note">Review whether the ' + esc(ratingText)
            + ' rating above still reflects current state</div>';
    }

    html += '</div>';
    return html;
}

function renderControlRatings(row) {
    let controls = [["IAG Control Effectiveness", row["IAG Control Effectiveness"]],
                   ["Aligned Assurance Rating", row["Aligned Assurance Rating"]],
                   ["Management Awareness Rating", row["Management Awareness Rating"]]];
    let valid = controls.filter(([,v]) => !isEmpty(v));
    if (!valid.length) return "";
    let html = '<div class="drill-section"><span class="label">Control Ratings <em style="text-transform:none;letter-spacing:0;font-weight:400;">(starting point)</em></span>';
    html += '<table class="rating-table">';
    valid.forEach(([l,v]) => { html += '<tr><td>' + esc(l) + '</td><td><span class="rating-bar">' + ratingBar(v) + '</span></td></tr>'; });
    html += '</table></div>';
    return html;
}

// ================================================================
// DRILL-DOWN BODY (unified)
// Reading order:
//   1. Outcome: Decision Basis (+ sibling matches for Undetermined rows)
//   2. "Why this risk applies" -- key risks, source rationale, signals
//   3. "How it's controlled" -- control ratings, control assessment, IAG
//      issues (with contradiction warning), OREs, PRSA, RAPs
// Sections self-suppress when empty; super-section headers only render
// when the group has at least one non-empty section.
// ================================================================
function renderDrilldownBody(row, detailRow, entityDetailRows, eid) {
    let status = row["Status"] || "";
    let l2 = row["New L2"] || "";
    let html = "";

    html += renderDecisionBasis(row, status);
    if (status === "Applicability Undetermined") {
        html += renderSiblingMatches(row, entityDetailRows);
    }

    // Group 1: Why this risk applies
    let whyContent = "";
    whyContent += renderKeyRiskDescriptions(detailRow, eid, l2);
    whyContent += renderSourceRationale(detailRow);
    whyContent += renderSignals(row["Additional Signals"], eid);
    if (whyContent) {
        html += '<div class="drill-supersection">Why this risk applies</div>'
            + '<div class="drill-section-inner">' + whyContent + '</div>';
    }

    // Group 2: How it's controlled
    let howContent = "";
    howContent += renderControlRatings(row);
    howContent += renderControlAssessment(row, eid, l2);
    howContent += renderRelevantFindings(row, eid, l2);
    howContent += renderRelevantOREs(eid, l2);
    howContent += renderRelevantPRSA(eid, l2);
    howContent += renderRelevantRAPs(eid, l2);
    if (howContent) {
        html += '<div class="drill-supersection">How it\u2019s controlled</div>'
            + '<div class="drill-section-inner">' + howContent + '</div>';
    }

    return html;
}

// ================================================================
// INVENTORY RENDERERS
// ================================================================
// One focused function per inventory type. Previously all five (apps, TPs,
// models, policies, laws) were inlined inside renderEntityView.

const _tierRank = {Primary:0, Secondary:1, Applicable:0, Additional:1};
function _byTierThenName(a, b) {
    let ta = _tierRank[a.tier] ?? 9, tb = _tierRank[b.tier] ?? 9;
    if (ta !== tb) return ta - tb;
    return String(a.sortKey||"").localeCompare(String(b.sortKey||""));
}
function _plural(n, s, p) { return n + " " + (n === 1 ? s : p); }
function _splitList(v) { return String(v||"").split(/[;\r\n]+/).map(s => s.trim()).filter(Boolean); }
function _splitModels(v) {
    return String(v||"")
        .split(/[;\r\n]+/)
        .map(s => s.trim())
        .filter(s => s && !isAbsence(s))
        .map(raw => ({raw: raw, ids: (raw.match(/\d{2,}/g) || [])}));
}

function renderHandoffsSection(legacyRow, eid) {
    let fromIds = _splitList(legacyRow["Hand-offs from Other Audit Entities"]).filter(x => !isAbsence(x));
    let toIds = _splitList(legacyRow["Hand-offs to Other Audit Entities"]).filter(x => !isAbsence(x));
    let hDesc = legacyRow["Hand-off Description"];
    if (fromIds.length === 0 && toIds.length === 0 && isAbsence(hDesc)) return "";

    let useExpander = Math.max(fromIds.length, toIds.length) > 10;

    function formatHandoffName(id) {
        let name = entityNameMap[id] || "";
        if (!id || isActiveEntity(id)) return esc(name);
        let status = getEntityStatus(id).trim() || "Inactive";
        return esc(name) + ' <span style="color: var(--gray); font-size: 12px;">(' + esc(status) + ')</span>';
    }
    function renderGroup(ids, label, keySuffix) {
        if (ids.length === 0) return "";
        let rows = ids.map(id => [esc(id), formatHandoffName(id)]);
        let tableHtml = buildTableHTML({
            id: "handoff-" + keySuffix + "-" + eid,
            headers: [{label: "ID", width: "90px"}, {label: "Name"}],
            rows: rows,
            wrap: true,
            tableClass: "handoff-table",
            minimal: true,
        });
        let headerText = label + " (" + ids.length + ")";
        if (useExpander) {
            return '<div class="handoff-group">' + mkExpander(false, headerText, tableHtml, "handoff:" + keySuffix + ":" + eid) + '</div>';
        }
        return '<div class="handoff-group">'
            + '<div class="handoff-col-label">' + headerText + '</div>'
            + tableHtml
            + '</div>';
    }

    let fromGroup = renderGroup(fromIds, "\u2190 From", "from");
    let toGroup = renderGroup(toIds, "To \u2192", "to");
    let gridHtml = '<div class="handoff-grid-wrapper"><div class="handoff-grid">' + fromGroup + toGroup + '</div></div>';
    let taggedIds = new Set([...fromIds, ...toIds]);
    let descHtml = renderHandoffDescription(hDesc, eid, taggedIds);
    return gridHtml + descHtml;
}

function annotateHandoffDesc(text, taggedIdSet) {
    const parts = [];
    let lastIdx = 0;
    const re = /\bAE-\d+\b/g;
    let m;
    while ((m = re.exec(text)) !== null) {
        if (m.index > lastIdx) parts.push(esc(text.substring(lastIdx, m.index)));
        const aeId = m[0];
        if (taggedIdSet.has(aeId)) {
            parts.push(esc(aeId));
        } else if (entityMeta && entityMeta[aeId]) {
            parts.push('<span class="ae-flag" '
                + 'title="Referenced in description but not in From/To handoff tables above \u2014 review whether handoff tagging is complete">'
                + esc(aeId) + '</span>');
        } else {
            parts.push('<span class="ae-flag" '
                + 'title="Not in this report \u2014 may be inactive, out of scope, or a typo">'
                + esc(aeId) + '</span>');
        }
        lastIdx = m.index + aeId.length;
    }
    if (lastIdx < text.length) parts.push(esc(text.substring(lastIdx)));
    return parts.join('');
}

function renderHandoffDescription(raw, eid, taggedIds) {
    if (isAbsence(raw)) return "";
    const text = String(raw);

    if (text.length <= 400) {
        return '<div class="handoff-desc">' + annotateHandoffDesc(text, taggedIds) + '</div>';
    }

    let cut = -1;
    for (let i = 400; i >= 200; i--) {
        if (text[i] === '.' && (text[i+1] === ' ' || text[i+1] === '\n' || i+1 === text.length)) {
            cut = i + 1;
            break;
        }
    }
    if (cut < 0) {
        cut = text.lastIndexOf(' ', 400);
        if (cut < 200) cut = 400;
    }

    const visible = text.substring(0, cut).trim();
    const hidden = text.substring(cut).trim();
    const tid = "handoff-desc-more-" + eid;

    return '<div class="handoff-desc">'
        + annotateHandoffDesc(visible, taggedIds)
        + '<span id="' + tid + '" style="display:none;"> '
        + annotateHandoffDesc(hidden, taggedIds)
        + '</span> '
        + '<a href="javascript:void(0)" class="overview-toggle" '
        + 'onclick="toggleOverview(\'' + tid + '\', this)">Show more</a>'
        + '</div>';
}

function renderAppsInventory(primaryIds, secondaryIds, eid) {
    if (!primaryIds.length && !secondaryIds.length) return "";
    let appById = {};
    applicationsInventory.forEach(a => { let k = String(a[INVENTORY_COLS.appId]||"").trim(); if (k) appById[k] = a; });

    let items = [];
    primaryIds.forEach(id => items.push({
        tier: "Primary", id, rec: appById[id], isKey: !!(eid && isKeyApp(eid, id)),
        sortKey: id
    }));
    secondaryIds.forEach(id => items.push({
        tier: "Secondary", id, rec: appById[id], isKey: !!(eid && isKeyApp(eid, id)),
        sortKey: id
    }));
    // Sort: tier first (Primary > Secondary), then key first within each tier
    // (per audit procedure non-key apps do not drive risk), then alphabetical
    // by ID.
    items.sort((a, b) => {
        let ta = _tierRank[a.tier] ?? 9, tb = _tierRank[b.tier] ?? 9;
        if (ta !== tb) return ta - tb;
        if (a.isKey !== b.isKey) return a.isKey ? -1 : 1;
        return String(a.sortKey||"").localeCompare(String(b.sortKey||""));
    });

    // Key column: render the list of KPA IDs where this app is "key" for
    // the entity. Falls back to a solid green dot when no KPA attribution is
    // available (older outputs before KPA ID was ingested).
    let keyCell = (isKey, id) => {
        if (!isKey) return '';
        let kpas = eid ? keyAppKpas(eid, id) : [];
        if (!kpas.length) return '<span style="color:#1e7a3a;font-weight:700;">\u25cf</span>';
        return kpas.map(k => '<span class="id-chip id-chip-key">' + esc(k) + '</span>').join(' ');
    };
    let rows = items.map(r => {
        if (!r.rec) return [
            '<span class="meta">(not found in applications inventory)</span>',
            '\u2014', '\u2014', '\u2014', keyCell(r.isKey, r.id), esc(r.tier), esc(r.id),
        ];
        let rec = r.rec;
        return [
            esc(String(rec[INVENTORY_COLS.appName]||"")),
            makePill(rec[INVENTORY_COLS.appConfidence]||"", "severity"),
            makePill(rec[INVENTORY_COLS.appAvailability]||"", "severity"),
            makePill(rec[INVENTORY_COLS.appIntegrity]||"", "severity"),
            keyCell(r.isKey, r.id),
            esc(r.tier),
            esc(r.id),
        ];
    });

    let keyCount = items.filter(i => i.isKey).length;
    let keyCountText = keyCount > 0 ? ', \u25cf ' + keyCount + ' key' : '';
    return '<p class="meta">' + _plural(items.length, "application", "applications") + ' \u2014 ' + primaryIds.length + ' Primary, ' + secondaryIds.length + ' Secondary' + keyCountText + '</p>'
        + buildTableHTML({
            id: "inv-apps",
            headers: [
                {label: "Name",            noFilter: true},
                {label: "Confidentiality", noFilter: true},
                {label: "Availability",    noFilter: true},
                {label: "Integrity",       noFilter: true},
                {label: "Key",             noFilter: true},
                {label: "Tier",            noFilter: true},
                {label: "ID",              noFilter: true},
            ],
            rows: rows,
        });
}

function renderThirdPartiesInventory(primaryIds, secondaryIds, eid) {
    if (!primaryIds.length && !secondaryIds.length) return "";
    let tpById = {};
    thirdpartiesInventory.forEach(t => { let k = String(t[INVENTORY_COLS.tpId]||"").trim(); if (k) tpById[k] = t; });

    let items = [];
    primaryIds.forEach(id => items.push({
        tier: "Primary", id, rec: tpById[id], isKey: !!(eid && isKeyTp(eid, id)),
        sortKey: id
    }));
    secondaryIds.forEach(id => items.push({
        tier: "Secondary", id, rec: tpById[id], isKey: !!(eid && isKeyTp(eid, id)),
        sortKey: id
    }));
    // Sort: tier first, then key first within each tier, then alphabetical
    // by TLM ID.
    items.sort((a, b) => {
        let ta = _tierRank[a.tier] ?? 9, tb = _tierRank[b.tier] ?? 9;
        if (ta !== tb) return ta - tb;
        if (a.isKey !== b.isKey) return a.isKey ? -1 : 1;
        return String(a.sortKey||"").localeCompare(String(b.sortKey||""));
    });

    let keyCell = (isKey, id) => {
        if (!isKey) return '';
        let kpas = eid ? keyTpKpas(eid, id) : [];
        if (!kpas.length) return '<span style="color:#1e7a3a;font-weight:700;">\u25cf</span>';
        return kpas.map(k => '<span class="id-chip id-chip-key">' + esc(k) + '</span>').join(' ');
    };
    let rows = items.map(r => {
        if (!r.rec) return [
            '<span class="meta">(not found in third parties inventory)</span>',
            '\u2014', keyCell(r.isKey, r.id), esc(r.tier), esc(r.id),
        ];
        let nm = r.rec[INVENTORY_COLS.tpName] || "";
        let risk = r.rec[INVENTORY_COLS.tpOverallRisk] || "";
        return [
            esc(String(nm)),
            makePill(risk, "severity"),
            keyCell(r.isKey, r.id),
            esc(r.tier),
            esc(r.id),
        ];
    });

    let keyCount = items.filter(i => i.isKey).length;
    let keyCountText = keyCount > 0 ? ', \u25cf ' + keyCount + ' key' : '';
    return '<p class="meta">' + _plural(items.length, "third party", "third parties") + ' \u2014 ' + primaryIds.length + ' Primary, ' + secondaryIds.length + ' Secondary' + keyCountText + '</p>'
        + buildTableHTML({
            id: "inv-tps",
            headers: [
                {label: "Name",         noFilter: true},
                {label: "Overall Risk", noFilter: true},
                {label: "Key",          noFilter: true},
                {label: "Tier",         noFilter: true},
                {label: "TLM ID",       noFilter: true},
            ],
            rows: rows,
        });
}

function renderModelsInventory(modelList) {
    if (!modelList.length) return "";
    let modelById = {};
    modelsInventory.forEach(m => { let k = String(m[INVENTORY_COLS.modelId]||"").trim(); if (k) modelById[k] = m; });

    let items = modelList.map(entry => {
        let id = "";
        for (let candidate of entry.ids) {
            if (modelById[candidate]) { id = candidate; break; }
        }
        let rec = id ? modelById[id] : null;
        return {id: id, raw: entry.raw, rec: rec, sortKey: (rec && rec[INVENTORY_COLS.modelName]) || entry.raw};
    });
    items.sort((a, b) => String(a.sortKey).localeCompare(String(b.sortKey)));

    let rows = items.map(r => {
        if (!r.rec) return [
            '<span class="meta">(not in inventory)</span> ' + esc(r.raw),
            '—', '—', '—', '—',
        ];
        let rec = r.rec;
        return [
            esc(String(rec[INVENTORY_COLS.modelName]||"")),
            makePill(rec[INVENTORY_COLS.modelImpact]||"", "severity"),
            esc(String(rec[INVENTORY_COLS.modelClass]||"")),
            esc(String(rec[INVENTORY_COLS.modelMarkets]||"")),
            esc(r.id),
        ];
    });

    return '<p class="meta">' + _plural(items.length, "model", "models") + '</p>'
        + buildTableHTML({
            id: "inv-models",
            headers: [
                {label: "Name",    noFilter: true},
                {label: "Impact",  noFilter: true},
                {label: "Class",   noFilter: true},
                {label: "Markets", noFilter: true},
                {label: "ID",      noFilter: true},
            ],
            rows: rows,
        });
}

function renderPoliciesInventory(policyIds) {
    if (!policyIds.length) return "";
    let pspById = {};
    policiesInventory.forEach(p => { let k = String(p[INVENTORY_COLS.pspId]||"").trim(); if (k) pspById[k] = p; });

    let items = policyIds.map(id => {
        let rec = pspById[id];
        return {id, rec, sortKey: (rec && rec[INVENTORY_COLS.pspName]) || id};
    });
    items.sort((a,b) => String(a.sortKey).localeCompare(String(b.sortKey)));

    let rows = items.map(r => {
        if (!r.rec) return ['<span class="meta">(not found in policies inventory)</span>', esc(r.id)];
        return [esc(String(r.rec[INVENTORY_COLS.pspName]||"")), esc(r.id)];
    });

    return '<p class="meta">' + _plural(items.length, "policy", "policies") + '</p>'
        + buildTableHTML({
            id: "inv-policies",
            headers: ["Name", "ID"],
            rows: rows,
            minimal: true,
        });
}

function renderLawsInventory(applicIds, additionalIds) {
    if (!applicIds.length && !additionalIds.length) return "";
    let manById = {};
    lawsInventory.forEach(m => { let k = String(m[INVENTORY_COLS.manId]||"").trim(); if (k) manById[k] = m; });

    let seen = new Set();
    let ids = [];
    [...applicIds, ...additionalIds].forEach(id => { if (id && !seen.has(id)) { seen.add(id); ids.push(id); } });

    let items = ids.map(id => {
        let rec = manById[id];
        return {id, rec, sortKey: (rec && rec[INVENTORY_COLS.manTitle]) || id};
    });
    items.sort((a, b) => String(a.sortKey).localeCompare(String(b.sortKey)));

    let rows = items.map(r => {
        if (!r.rec) return ['<span class="meta">(not found in mandates inventory)</span>', '\u2014', esc(r.id)];
        return [
            esc(String(r.rec[INVENTORY_COLS.manTitle]||"")),
            esc(String(r.rec[INVENTORY_COLS.manApplicability]||"\u2014")),
            esc(r.id),
        ];
    });

    return '<p class="meta">' + _plural(items.length, "mandate", "mandates") + '</p>'
        + buildTableHTML({
            id: "inv-laws",
            headers: ["Name", "Applicability", "ID"],
            rows: rows,
            minimal: true,
        });
}

// Build the inventories section as five separate per-type expanders plus an
// optional orphan-warning banner that sits above the expander group.
// Returns: {bannerHtml, sections: [{header, body, key}, ...]}
// Each section always renders (even when empty) so reviewers can see at a
// glance whether each inventory type has data \u2014 mirrors the issues-&-events
// pattern at lines 4657 / 4702 / etc.
function renderInventoriesSection(legacyRow, eid) {
    let primaryApps = [], secondaryApps = [], primaryTPs = [], secondaryTPs = [];
    let modelList = [], policyList = [], lawsApplic = [], lawsAdd = [];
    if (legacyRow) {
        primaryApps = _splitList(legacyRow[INVENTORY_COLS.legacyPrimaryIT]).filter(x => !isAbsence(x));
        secondaryApps = _splitList(legacyRow[INVENTORY_COLS.legacySecondaryIT]).filter(x => !isAbsence(x));
        primaryTPs = _splitList(legacyRow[INVENTORY_COLS.legacyPrimaryTP]).filter(x => !isAbsence(x));
        secondaryTPs = _splitList(legacyRow[INVENTORY_COLS.legacySecondaryTP]).filter(x => !isAbsence(x));
        modelList = _splitModels(legacyRow[INVENTORY_COLS.legacyModels]);
        policyList = _splitList(legacyRow[INVENTORY_COLS.legacyPolicies]).filter(x => !isAbsence(x));
        lawsApplic = _splitList(legacyRow[INVENTORY_COLS.legacyLawsApplic]).filter(x => !isAbsence(x));
        lawsAdd = _splitList(legacyRow[INVENTORY_COLS.legacyLawsAdd]).filter(x => !isAbsence(x));
    }

    let appsCount = primaryApps.length + secondaryApps.length;
    let tpsCount = primaryTPs.length + secondaryTPs.length;
    let modelsCount = modelList.length;
    let policiesCount = policyList.length;
    let lawsCount = lawsApplic.length + lawsAdd.length;

    // Orphan warning: key IDs flagged in key risks but not present in the
    // entity PRIMARY/SECONDARY inventory columns. Sits above the expander
    // group so it's always visible without expanding any section.
    let bannerHtml = "";
    let ki = eid ? getKeyInv(eid) : null;
    if (ki && (ki.orphanApps.length || ki.orphanTps.length)) {
        let parts = [];
        if (ki.orphanApps.length) parts.push('<strong>' + ki.orphanApps.length + ' application' + (ki.orphanApps.length === 1 ? '' : 's') + '</strong> (' + ki.orphanApps.map(esc).join(', ') + ')');
        if (ki.orphanTps.length) parts.push('<strong>' + ki.orphanTps.length + ' third part' + (ki.orphanTps.length === 1 ? 'y' : 'ies') + '</strong> (' + ki.orphanTps.map(esc).join(', ') + ')');
        bannerHtml = '<div class="banner banner-danger" style="margin-bottom:10px;">'
            + '<strong>Entity inventory gap:</strong> '
            + parts.join(' and ')
            + ' flagged as key in key risks but not in entity PRIMARY/SECONDARY inventory. Review whether the entity inventory is complete.'
            + '</div>';
    }

    let modelsInvSet = new Set();
    modelsInventory.forEach(m => { let k = String(m[INVENTORY_COLS.modelId]||"").trim(); if (k) modelsInvSet.add(k); });
    let unmatchedModels = modelList.filter(entry => !entry.ids.some(id => modelsInvSet.has(id)));
    let unmatchedModelsCount = unmatchedModels.length;
    if (unmatchedModelsCount > 0) {
        bannerHtml += '<div class="banner banner-danger" style="margin-bottom:10px;">'
            + '<strong>Models inventory gap:</strong> '
            + '<strong>' + unmatchedModelsCount + ' model' + (unmatchedModelsCount === 1 ? '' : 's') + '</strong>'
            + ' referenced in legacy data but not present in the models inventory file. Review whether the models team\'s inventory is complete.'
            + '</div>';
    }

    // Header pluralization helper specific to per-type expander labels.
    function _hdr(label, n) { return label + " \u2014 " + _plural(n, "item", "items"); }

    let sections = [
        {
            header: _hdr("Applications", appsCount),
            body: appsCount
                ? renderAppsInventory(primaryApps, secondaryApps, eid)
                : "<p class='meta'>No applications for this entity.</p>",
            key: "src-apps-inv",
            hasItems: !!appsCount,
        },
        {
            header: _hdr("Third Parties", tpsCount),
            body: tpsCount
                ? renderThirdPartiesInventory(primaryTPs, secondaryTPs, eid)
                : "<p class='meta'>No third parties for this entity.</p>",
            key: "src-tps-inv",
            hasItems: !!tpsCount,
        },
        {
            header: unmatchedModelsCount > 0
                ? "Models — " + _plural(modelsCount, "item", "items") + " (" + unmatchedModelsCount + " not in inventory)"
                : _hdr("Models", modelsCount),
            body: modelsCount
                ? renderModelsInventory(modelList)
                : "<p class='meta'>No models for this entity.</p>",
            key: "src-models-inv",
            hasItems: !!modelsCount,
        },
        {
            header: _hdr("Policies / Standards / Procedures", policiesCount),
            body: policiesCount
                ? renderPoliciesInventory(policyList)
                : "<p class='meta'>No policies for this entity.</p>",
            key: "src-policies-inv",
            hasItems: !!policiesCount,
        },
        {
            header: _hdr("Laws & Mandates", lawsCount),
            body: lawsCount
                ? renderLawsInventory(lawsApplic, lawsAdd)
                : "<p class='meta'>No laws or mandates for this entity.</p>",
            key: "src-laws-inv",
            hasItems: !!lawsCount,
        },
    ];

    return {bannerHtml, sections};
}

// ==================== FILTERING ====================
let currentView = "entity";

function applyFilters() {
    if (currentView === "entity") renderEntityView();
    else if (currentView === "risk") renderRiskView();
}

function getFilteredAuditData(baseFilter) {
    let data = baseFilter || auditData;
    if (currentView !== "entity") {
        let al = document.getElementById("filter-al").value;
        let pga = document.getElementById("filter-pga").value;
        let team = document.getElementById("filter-team").value;
        if (al) data = data.filter(r => String(getEntityMeta(r["Entity ID"])["Audit Leader"] || "") === al);
        if (pga) data = data.filter(r => String(getEntityMeta(r["Entity ID"])["PGA"] || "") === pga);
        if (team) data = data.filter(r => String(getEntityMeta(r["Entity ID"])["Core Audit Team"] || "") === team);
    }
    return data;
}

// ==================== VIEW SWITCHING ====================
function switchView(name) {
    currentView = name;
    document.querySelectorAll(".tab-content").forEach(t => t.classList.remove("active"));
    document.getElementById("tab-" + name).classList.add("active");
    document.getElementById("sidebar-entity-select").style.display = name === "entity" ? "block" : "none";
    document.getElementById("sidebar-risk-select").style.display = name === "risk" ? "block" : "none";
    // Methodology view is read-only prose — hide AL/PGA/Team filters too.
    document.getElementById("sidebar-org-filters").style.display =
        (name !== "entity" && name !== "methodology") ? "block" : "none";
    if (name === "entity") renderEntityView();
    if (name === "risk") renderRiskView();
    if (name === "methodology") renderMethodologyView();
}

function switchEntityTab(name) {
    document.querySelectorAll(".sub-tab-content").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".sub-tab").forEach(t => t.classList.remove("active"));
    document.getElementById("entity-tab-" + name).classList.add("active");
    let idx = ["profile","legacy","source","trace"].indexOf(name);
    document.querySelectorAll(".sub-tab")[idx].classList.add("active");
}

// ==================== ENTITY VIEW ====================
function renderEntityView() {
    let eid = getTypeaheadValue("entity-select");
    if (!eid) return;
    let baseRows = auditData.filter(r => r["Entity ID"] === eid);
    let rows = getFilteredAuditData(baseRows);
    if (!rows.length) {
        document.getElementById("entity-title").innerHTML = '<h2 style="border:none;margin-top:0;">Entity: ' + esc(eid) + '</h2>';
        document.getElementById("entity-banner").innerHTML = '<div class="banner banner-info">No rows match the current filters.</div>';
        return;
    }
    document.getElementById("entity-title").innerHTML = '<h2 style="border:none;margin-top:0;">Entity: ' + esc(eid) + '</h2>';
    // Clear the banner container so a previous render's empty-filter-state
    // info banner doesn't linger when filters now match rows.
    document.getElementById("entity-banner").innerHTML = "";

    // Context
    let em = getEntityMeta(eid);
    let ctxHtml = '<div class="entity-context">';
    if (!isEmpty(em["Entity Name"])) ctxHtml += '<h3>' + esc(em["Entity Name"]) + '</h3>';
    if (!isEmpty(em["Entity Overview"])) ctxHtml += '<div class="overview">' + formatOverview(em["Entity Overview"], eid) + '</div>';
    let meta = [];
    if (!isEmpty(em["Audit Leader"])) meta.push("Audit Leader: " + em["Audit Leader"]);
    if (!isEmpty(em["PGA"])) meta.push("PGA: " + em["PGA"]);
    if (meta.length) ctxHtml += '<p class="meta">' + meta.join(" \u00B7 ") + '</p>';

    let legacyRow = legacyData.find(r => String(r["Audit Entity ID"]||"").trim() === eid);
    if (legacyRow) {
        let inner = renderHandoffsSection(legacyRow, eid);
        if (inner) {
            ctxHtml += '<div class="drill-section"><span class="label">Handoffs</span>' + inner + '</div>';
        }
    }

    ctxHtml += "</div><div class='divider'></div>";
    document.getElementById("entity-context").innerHTML = ctxHtml;

    // Sort
    let statusOrder = {};
    Object.keys(STATUS_CONFIG).forEach(s => statusOrder[s] = STATUS_CONFIG[s].sort);
    rows.sort((a,b) => {
        let sa = statusOrder[a["Status"]]??99, sb = statusOrder[b["Status"]]??99;
        if (sa !== sb) return sa - sb;
        let ra = RATING_RANK[a["Inherent Risk Rating"]]||0, rb = RATING_RANK[b["Inherent Risk Rating"]]||0;
        return rb - ra;
    });

    let entityDetail = detailData.filter(d => String(d["entity_id"]) === String(eid));

    // --- Risk Profile tab ---
    let overviewCols = ["New L1","New L2","Status","Inherent Risk Rating","Legacy Source","Decision Basis","Additional Signals"];
    if (rows.length && rows[0].hasOwnProperty("Control Effectiveness Baseline")) overviewCols.push("Control Effectiveness Baseline");
    if (rows.length && rows[0].hasOwnProperty("Impact of Issues")) overviewCols.push("Impact of Issues");
    if (rows.length && rows[0].hasOwnProperty("Control Signals")) overviewCols.push("Control Signals");
    let profileRows = rows.map(r => overviewCols.map(c => {
        let v = r[c];
        if (c === "Status") return statusLabel(v);
        if (c === "Inherent Risk Rating") return isEmpty(v) ? "\u2014" : String(v);
        if (c === "New L2") {
            let cell = renderL2NameCell(r);
            return cell || (isEmpty(v) ? "" : String(v));
        }
        if (c === "Additional Signals") {
            let parsed = parseSignalsForRender(v);
            if (!parsed) return "";
            return { html: renderSignalsForCell(parsed, eid), tdClass: "cell-signals" };
        }
        if (c === "Decision Basis") {
            let cell = renderDecisionBasisCell(r, eid, r["New L2"]);
            return cell || (isEmpty(v) ? "" : String(v));
        }
        if (c === "Impact of Issues") {
            let cell = renderImpactForCell(r, eid, r["New L2"]);
            return cell || "";
        }
        return isEmpty(v) ? "" : String(v);
    }));
    let profileHeaderOverride = {"Inherent Risk Rating": "Legacy Risk Rating", "Status": "Suggested Status"};
    let profileToolCols = new Set(["Status", "Decision Basis", "Additional Signals", "Impact of Issues", "Control Signals", "Inherent Risk Rating"]);
    // Columns that get the column-wide expand icon. Long-prose columns
    // the auditor needs to scan down the column at a glance.
    let profileExpandCols = new Set(["Decision Basis", "Additional Signals", "Impact of Issues", "Control Signals"]);
    // Default widths: non-expand columns get compact fixed widths so
    // that expand columns (Decision Basis, Additional Signals, Impact
    // of Issues) share the remaining space generously.
    let profileWidths = {
        "New L1": "100px", "New L2": "140px", "Status": "90px",
        "Inherent Risk Rating": "100px", "Legacy Source": "100px",
        "Control Effectiveness Baseline": "130px", "Control Signals": "120px",
    };
    // Tag-based filtering: instead of showing every unique cell text
    // in the filter dropdown, extract individual chip labels so the
    // user can filter by tag type (e.g. "Keyword Match", "IAG", "App").
    let profileFilterChips = {
        "Decision Basis": ".decision-chip",
        "Additional Signals": ".signal-summary-chip",
        "Impact of Issues": ".signal-summary-chip",
    };
    let profileHeaders = overviewCols.map(c => ({
        label: profileHeaderOverride[c] || c,
        tool: profileToolCols.has(c),
        expand: profileExpandCols.has(c),
        width: profileWidths[c] || undefined,
        filterChips: profileFilterChips[c] || undefined,
    }));
    document.getElementById("entity-profile-host").innerHTML = buildTableHTML({
        id: "entity-profile-table",
        headers: profileHeaders,
        rows: profileRows,
    });

    // --- Legacy Profile tab ---
    let legacyHtml = "";
    if (legacyRatingsData.length) {
        let eidCol = resolveCol(legacyRatingsData, ["Entity ID", "Audit Entity ID"]);
        if (eidCol) {
            let lr = legacyRatingsData.filter(r => String(r[eidCol]||"").trim() === eid);
            if (lr.length) {
                let emptyCell = '<span class="empty-cell">\u2014</span>';
                let rows = lr.map(r => [
                    esc(String(r["Risk Pillar"]||"")),
                    makePill(r["Inherent Risk Rating"]||"", "severity"),
                    isEmpty(r["Inherent Risk Rationale"]) ? emptyCell : esc(String(r["Inherent Risk Rationale"])),
                    makePill(r["Control Assessment"]||"", "controlRating"),
                    isEmpty(r["Control Assessment Rationale"]) ? emptyCell : esc(String(r["Control Assessment Rationale"])),
                ]);
                legacyHtml = buildTableHTML({
                    id: "legacy-ratings-table",
                    headers: [
                        {label: "Risk Pillar", width: "160px"},
                        {label: "Inherent Risk", width: "110px"},
                        {label: "Risk Rationale"},
                        {label: "Control Assessment", width: "180px"},
                        {label: "Control Rationale"},
                    ],
                    rows: rows,
                    minimal: true,
                });
            } else { legacyHtml = "<p class='meta'>No legacy ratings found for this entity.</p>"; }
        } else { legacyHtml = "<p class='meta'>Legacy ratings data missing entity column.</p>"; }
    } else { legacyHtml = "<p class='meta'>No legacy ratings data in workbook.</p>"; }
    document.getElementById("entity-legacy-ratings").innerHTML = legacyHtml;

    // --- Traceability tab ---
    let traceHtml = "";
    if (entityDetail.length) {
        traceHtml += "<h3>Multi-Mapping Fan-Out</h3>";
        let pillars = [...new Set(entityDetail.map(d => basePillar(d["source_legacy_pillar"]||"")))].filter(p => p && p !== "nan" && p !== "None" && p !== "Findings").sort();
        pillars.forEach(pillar => {
            let pr = entityDetail.filter(d => String(d["source_legacy_pillar"]||"").includes(pillar));
            if (pr.length <= 1) return;
            let rawR = pr.map(d => d["source_risk_rating_raw"]).filter(x => !isEmpty(x));
            let rStr = rawR.length ? String(rawR[0]) : "unknown";
            let statusCounts = {};
            pr.forEach(p => {
                let s = methodToStatus(String(p["method"]||""));
                statusCounts[s] = (statusCounts[s]||0) + 1;
            });
            let parts = [];
            Object.keys(STATUS_CONFIG).forEach(s => {
                if (statusCounts[s]) parts.push(statusCounts[s] + " " + STATUS_CONFIG[s].icon);
            });
            let label = "\ud83d\udcc2 " + esc(pillar) + " (rated " + esc(rStr) + ") \u2192 " + parts.join(", ");
            let body = "";
            pr.forEach(p => {
                let s = methodToStatus(String(p["method"]||""));
                let ic = STATUS_CONFIG[s] ? STATUS_CONFIG[s].icon : "?";
                body += '<div>' + ic + ' <strong>' + esc(p["new_l2"]) + '</strong> \u2014 ' + esc(s) + '</div>';
            });
            traceHtml += mkExpander(false, label, body, "trace:" + eid + ":" + pillar);
        });

        let dedupRows = entityDetail.filter(d => String(d["source_legacy_pillar"]||"").includes("also:"));
        if (dedupRows.length) {
            traceHtml += "<h3>Convergence</h3>";
            dedupRows.forEach(dr => {
                let src = String(dr["source_legacy_pillar"]||"");
                let primary = src.split(" (also:")[0].trim();
                let also = [];
                let rem = src;
                while (rem.includes("(also:")) {
                    let s = rem.indexOf("(also:") + 6;
                    let e = rem.indexOf(")", s);
                    if (e === -1) break;
                    also.push(rem.substring(s, e).trim());
                    rem = rem.substring(e + 1);
                }
                let r = dr["source_risk_rating_raw"];
                let rStr = isEmpty(r) ? "no rating" : String(r);
                traceHtml += '<div><strong>' + esc(dr["new_l2"]) + '</strong> \u2190 ' + esc([primary, ...also].join(" + ")) + ' \u2192 kept ' + esc(rStr) + '</div>';
            });
        }
    } else {
        traceHtml = '<p class="meta">No traceability data available.</p>';
    }
    document.getElementById("entity-traceability").innerHTML = traceHtml;

    // --- Source Data tab ---
    let srcHtml = "";

    // Hover tooltip for mapper "Mapping Status" column headers. The NLP
    // mappers no longer assert a positive-confidence band — every item that
    // passes the similarity floor is Needs Review by design.
    const _NLP_STATUS_TIP = "Starting point only. These items are matched to "
        + "L2 by NLP text similarity, which can be wrong — e.g. generic "
        + "wording, or L2 definitions that read similarly. Every item is marked "
        + "Needs Review by design: confirm you agree with the L2 attribution "
        + "before relying on it.";

    // === Scope group ===
    srcHtml += "<h2>Scope</h2>";

    // Inventories — five per-type expanders + optional orphan-warning banner
    // above the group. Mirrors the issues-&-events pattern (one mkExpander
    // per source); each type defaults to collapsed and remembers user toggles.
    let inv = renderInventoriesSection(legacyRow, eid);
    srcHtml += inv.bannerHtml;
    inv.sections.forEach(section => {
        // Auto-expand sections with content; collapse empty placeholders so
        // reviewers' eyes land on data, not on "No X for this entity." rows.
        srcHtml += mkExpander(!!section.hasItems, section.header, section.body, section.key);
    });

    // Key Risks
    let es = subRisksData.filter(s => String(s["entity_id"]||s["Audit Entity"]||s["Audit Entity ID"]||"").trim() === eid);
    let subHeader = 'Key Risks \u2014 ' + es.length + ' key risk' + (es.length === 1 ? "" : "s");
    let subBody = "";
    if (es.length) {
        let subRows = es.map(s => [
            esc(String(s["risk_id"]||s["Key Risk ID"]||"")),
            esc(String(s["risk_description"]||s["Key Risk Description"]||"").substring(0,200)),
            esc(String(s["legacy_l1"]||s["Level 1 Risk Category"]||"")),
            esc(String(s["key_risk_rating"]||s["Inherent Risk Rating"]||"")),
            esc(String(s["L2 Keyword Matches"]||s["Contributed To (keyword matches)"]||"")),
        ]);
        subBody = buildTableHTML({
            id: "src-subrisks-table",
            headers: [
                "Risk ID",
                {label: "Description", expand: true},
                "Legacy L1", "Rating",
                {label: "L2 Keyword Matches", tool: true},
            ],
            rows: subRows,
        });
    } else {
        subHeader = "Key Risks";
        subBody = "<p class='meta'>No key risk descriptions for this entity.</p>";
    }
    srcHtml += mkExpander(true, subHeader, subBody, "src-subrisks");

    srcHtml += "<div class='divider'></div>";

    // === Issues & Events group ===
    srcHtml += "<h2>Issues &amp; Events</h2>";

    // Generic unmapped-items suffix (banners.yaml: unmapped_suffix), appended into a source banner.
    const unmappedSuffix = __UNMAPPED_SUFFIX_JSON__;
    function appendBannerLine(bannerHtml, line) {
        if (!bannerHtml) return '<div class="banner banner-warn">' + line + '</div>';
        let i = bannerHtml.lastIndexOf("</div>");
        if (i === -1) return bannerHtml + '<br>' + line;
        return bannerHtml.slice(0, i) + '<br>' + line + bannerHtml.slice(i);
    }

    // IAG Issues
    let efEidCol = resolveCol(findingsData, ["entity_id", "Audit Entity ID"]);
    let efAll = efEidCol ? findingsData.filter(f => String(f[efEidCol]||"").trim() === eid) : [];
    let iagHeader = "IAG Issues";
    let iagBody = __BANNER_IAG_JSON__;
    let iagUnmapped = efAll.filter(f => String(f["Mapping Status"]||"").startsWith("Filtered") && String(f["Mapping Status"]||"").toLowerCase().includes("unmappable"));
    if (iagUnmapped.length) iagBody = appendBannerLine(iagBody, unmappedSuffix);
    if (efAll.length) {
        iagHeader = 'IAG Issues \u2014 ' + efAll.length + ' issue' + (efAll.length === 1 ? "" : "s") + severitySummary(efAll, f => f["severity"]||f["Final Reportable Finding Risk Rating"], ["Critical","High","Medium","Low"]);
        let iagRows = efAll.map(f => [
            '<span class="id-chip">' + esc(String(f["issue_id"]||f["Finding ID"]||"")) + '</span>',
            makePill(f["severity"]||f["Final Reportable Finding Risk Rating"]||"", "severity"),
            esc(String(f["status"]||f["Finding Status"]||"")),
            esc(String(f["issue_title"]||f["Finding Name"]||"")),
            esc(String(f["Finding Description"]||f["finding_description"]||"")),
            esc(String(f["l2_risk"]||f["Risk Dimension Categories"]||"")),
            esc(String(f["Mapping Status"]||"")),
        ]);
        iagBody += buildTableHTML({
            id: "src-iag-table",
            headers: [
                "Finding ID", "Severity", "Status", "Title",
                {label: "Description", expand: true},
                {label: "L2 Risk", tool: true},
                {label: "Mapping Status", tool: true},
            ],
            rows: iagRows,
        });
    } else {
        iagBody += "<p class='meta'>No IAG issues for this entity.</p>";
    }
    srcHtml += mkExpander(efAll.length > 0, iagHeader, iagBody, "src-iag");

    // OREs (legacy source only — IRM rows render in their own section below)
    let oreHeader = "Operational Risk Events (OREs)";
    let oreBody = __BANNER_ORE_JSON__;
    let oreHas = false;
    if (oreData.length) {
        let seenOre = new Set();
        let eo = [];
        oreData.forEach(o => {
            if (String(o["ore_source"]||"").toUpperCase() === "IRM") return;
            if (oreRowEid(o) !== normId(eid)) return;
            let evid = String(o["Event ID"]||"").trim();
            let key = evid || (String(o["Event Title"]||"").trim() + "|" + String(o["Event Description"]||"").trim());
            if (key && key !== "|") {
                if (seenOre.has(key)) return;
                seenOre.add(key);
            }
            eo.push(o);
        });
        if (eo.length) {
            oreHas = true;
            oreHeader = 'Operational Risk Events (OREs) \u2014 ' + eo.length + ' ORE' + (eo.length === 1 ? "" : "s") + severitySummary(eo, o => o["Final Event Classification"], ["Class A","Class B","Class C","Near Miss"]);
            // Column order: ID, classification pill, status, title, then
            // remaining detail columns.
            let oreApproved = [
                {k:"Event ID", idChip:true},
                {k:"Final Event Classification", pill:"oreClass"},
                {k:"Event Status"},
                {k:"Event Title"},
                {k:"Event Description", expand: true},
                {k:"Mapped L2s", label:"Suggested L2s", tool:true},
                {k:"Mapping Status", tool:true, titleTip:_NLP_STATUS_TIP},
            ];
            let cols = oreApproved.filter(c => eo[0].hasOwnProperty(c.k));
            let oreHeaders = cols.map(c => ({
                label: c.label || c.k,
                tool: !!c.tool,
                expand: !!c.expand,
                titleTip: c.titleTip,
            }));
            let oreRows = eo.map(o => cols.map(c => {
                let raw = o[c.k] || "";
                if (c.pill) return makePill(raw, c.pill);
                if (c.idChip) return '<span class="id-chip">' + esc(String(raw)) + '</span>';
                return esc(String(raw));
            }));
            oreBody += buildTableHTML({
                id: "src-ore-table",
                headers: oreHeaders,
                rows: oreRows,
            });
        } else { oreBody += "<p class='meta'>No OREs for this entity.</p>"; }
    } else { oreBody += "<p class='meta'>No ORE data in workbook.</p>"; }
    srcHtml += mkExpander(oreHas, oreHeader, oreBody, "src-ore");

    // ORE IRM (separate per-AE drill-down section). Filtered to rows tagged
    // with `ore_source: "IRM"` (set when the Python side merges IRM rows into
    // oreData first). Header: "Operational Risk Events — IRM Archer".
    let oreIrmHeader = "Operational Risk Events — IRM Archer";
    let oreIrmBody = __BANNER_ORE_IRM_ENTITY_JSON__;
    let oreIrmHas = false;
    if (oreData.length) {
        let seenIrm = new Set();
        let eIrm = [];
        oreData.forEach(o => {
            if (String(o["ore_source"]||"").toUpperCase() !== "IRM") return;
            if (oreRowEid(o) !== normId(eid)) return;
            let evid = String(o["Event ID"]||"").trim();
            let key = evid || (String(o["Event Title"]||"").trim() + "|" + String(o["Event Description"]||"").trim());
            if (key && key !== "|") {
                if (seenIrm.has(key)) return;
                seenIrm.add(key);
            }
            eIrm.push(o);
        });
        if (eIrm.length) {
            oreIrmHas = true;
            oreIrmHeader = 'Operational Risk Events — IRM Archer — ' + eIrm.length + ' ORE' + (eIrm.length === 1 ? "" : "s");
            let irmApproved = [
                {k:"Event ID", idChip:true, label:"ORE ID"},
                {k:"Capture Status"},
                {k:"RCA Status"},
                {k:"Stop Ongoing Impact Status"},
                {k:"ORE Category"},
                {k:"ORE Status"},
                {k:"ORE Rating"},
                {k:"ORE Owner Business Unit (L1, L2, L3)"},
                {k:"Event Title", label:"ORE Title"},
                {k:"Event Description", label:"ORE Description", expand:true},
                {k:"Risk Level 2"},
                {k:"Mapped L2s", tool:true, titleTip:_NLP_STATUS_TIP},
                {k:"L2 Source", tool:true, titleTip:_NLP_STATUS_TIP},
                {k:"Legacy Event ID"},
            ];
            let cols = irmApproved.filter(c => eIrm[0].hasOwnProperty(c.k));
            let irmHeaders = cols.map(c => ({
                label: c.label || c.k,
                tool: !!c.tool,
                expand: !!c.expand,
                titleTip: c.titleTip,
            }));
            let irmRows = eIrm.map(o => cols.map(c => {
                let raw = o[c.k] || "";
                if (c.idChip) return '<span class="id-chip">' + esc(String(raw)) + '</span>';
                return esc(String(raw));
            }));
            oreIrmBody += buildTableHTML({
                id: "src-ore-irm-table",
                headers: irmHeaders,
                rows: irmRows,
            });
        } else { oreIrmBody += "<p class='meta'>No IRM OREs for this entity.</p>"; }
    } else { oreIrmBody += "<p class='meta'>No IRM ORE data in workbook.</p>"; }
    srcHtml += mkExpander(oreIrmHas, oreIrmHeader, oreIrmBody, "src-ore-irm");

    // PRSA Issues
    let prsaHeader = "PRSA Issues";
    let prsaBody = __BANNER_PRSA_JSON__;
    let prsaHas = false;
    if (prsaData.length) {
        let prsaEidCol = resolveCol(prsaData, ["AE ID", "Audit Entity", "Audit Entity ID"]);
        if (prsaEidCol) {
            let ep = prsaData.filter(p => {
                if (String(p[prsaEidCol]||"").trim() !== eid) return false;
                let pgFlag = String(p["Is PG Gap"]||"").trim().toLowerCase();
                return pgFlag !== "yes" && pgFlag !== "true" && pgFlag !== "1";
            });
            if (ep.length) {
                prsaHas = true;
                prsaHeader = 'PRSA Issues \u2014 ' + ep.length + ' record' + (ep.length === 1 ? "" : "s") + severitySummary(ep, p => p["Issue Rating"], ["Critical","High","Medium","Low"]);
                // Column order: ID, rating pill, status, title, then remaining
                // PRSA detail columns.
                let prsaApproved = ["Issue ID", "Issue Rating", "Issue Status", "Issue Title", "Issue Description", "PRSA ID", "Control Title", "Process Title", "Control ID (PRSA)", "Other AEs With This PRSA", "Mapped L2s", "Mapping Status"];
                let prsaExpandCols = new Set(["Issue Description"]);
                let cols = prsaApproved.filter(c => ep[0].hasOwnProperty(c));
                let prsaHeaders = cols.map(c => {
                    if (c === "Mapping Status") return {label: c, titleTip: _NLP_STATUS_TIP};
                    return prsaExpandCols.has(c) ? {label: c, expand: true} : c;
                });
                let prsaRows = ep.map(p => cols.map(c => {
                    if (c === "Issue Rating") return makePill(p[c]||"", "severity");
                    if (c === "Issue ID") return '<span class="id-chip">' + esc(String(p[c]||"")) + '</span>';
                    return esc(String(p[c]||""));
                }));
                prsaBody += buildTableHTML({
                    id: "src-prsa-table",
                    headers: prsaHeaders,
                    rows: prsaRows,
                });
            } else { prsaBody += "<p class='meta'>No PRSA data for this entity.</p>"; }
        } else { prsaBody += "<p class='meta'>PRSA data missing entity column.</p>"; }
    } else { prsaBody += "<p class='meta'>No PRSA data in workbook.</p>"; }
    srcHtml += mkExpander(prsaHas, prsaHeader, prsaBody, "src-prsa");

    // GRA RAPs
    let graHeader = "GRA RAPs (Regulatory Findings)";
    let graBody = __BANNER_GRA_RAP_JSON__;
    let graHas = false;
    if (graRapsData.length) {
        let graEidCol = resolveCol(graRapsData, ["Audit Entity ID"]);
        if (graEidCol) {
            let eg = graRapsData.filter(g => String(g[graEidCol]||"").trim() === eid);
            if (eg.length) {
                graHas = true;
                graHeader = 'GRA RAPs (Regulatory Findings) \u2014 ' + eg.length + ' RAP' + (eg.length === 1 ? "" : "s");
                // Column order: ID, status, header (title), then detail.
                let graApproved = ["RAP ID", "RAP Status", "RAP Header", "BU Corrective Action Due Date", "RAP Details", "Related Exams and Findings", "GRA RAPS", "Mapped L2s", "Mapping Status"];
                let graExpandCols = new Set(["RAP Details"]);
                let cols = graApproved.filter(c => eg[0].hasOwnProperty(c));
                let graHeaders = cols.map(c => {
                    if (c === "Mapping Status") return {label: c, titleTip: _NLP_STATUS_TIP};
                    return graExpandCols.has(c) ? {label: c, expand: true} : c;
                });
                let graRows = eg.map(g => cols.map(c => {
                    if (c === "RAP ID") return '<span class="id-chip">' + esc(String(g[c]||"")) + '</span>';
                    return esc(String(g[c]||""));
                }));
                graBody += buildTableHTML({
                    id: "src-gra-table",
                    headers: graHeaders,
                    rows: graRows,
                });
            } else { graBody += "<p class='meta'>No GRA RAPs for this entity.</p>"; }
        } else { graBody += "<p class='meta'>GRA RAPs data missing entity column.</p>"; }
    } else { graBody += "<p class='meta'>No GRA RAPs data in workbook.</p>"; }
    srcHtml += mkExpander(graHas, graHeader, graBody, "src-gra");

    // PG Gaps (Track C) — mapped PG gaps for this entity. Unmapped PG gaps
    // (no AE) are not visible per-AE; they live in the Source - PG Gaps Excel tab.
    let pgHeader = "PG Gaps";
    let pgBody = __BANNER_PG_GAP_JSON__;
    let pgHas = false;
    // PG Gaps drawn from the PG-only Excel tab (Source - PG Gaps). Filter to
    // mapped rows (AE populated) for the per-entity drill-down. Unmapped PG
    // gaps have blank AE — they show only in the Excel tab + banner count.
    function _isPgYes(v) {
        let s = String(v||"").trim().toLowerCase();
        return s === "yes" || s === "true" || s === "1";
    }
    if (pgGapData.length) {
        // The PG Gaps tab schema doesn't carry an AE ID column (per-issue
        // grain) — so we cross-reference into prsaData (which is AE-exploded)
        // to figure out which PG gap issues are tagged to this entity.
        let prsaEidColPg = resolveCol(prsaData, ["AE ID", "Audit Entity", "Audit Entity ID"]);
        let pgIssuesForEntity = new Set();
        if (prsaEidColPg) {
            prsaData.forEach(p => {
                if (!_isPgYes(p["Is PG Gap"])) return;
                if (String(p[prsaEidColPg]||"").trim() !== eid) return;
                let iid = String(p["Issue ID"]||"").trim();
                if (iid) pgIssuesForEntity.add(iid);
            });
        }
        let ePg = pgGapData.filter(p =>
            _isPgYes(p["Is PG Gap"]) &&
            pgIssuesForEntity.has(String(p["Issue ID"]||"").trim())
        );
        if (ePg.length) {
            pgHas = true;
            pgHeader = 'PG Gaps — ' + ePg.length + ' record' + (ePg.length === 1 ? "" : "s");
            let pgApproved = ["Issue ID", "Issue Rating", "Issue Status", "Issue Title", "Issue Description", "Risk Level 2", "Is PG Gap"];
            let pgExpandCols = new Set(["Issue Description"]);
            let cols = pgApproved.filter(c => ePg[0].hasOwnProperty(c));
            let pgHeaders = cols.map(c =>
                pgExpandCols.has(c) ? {label: c, expand: true, tool: c === "Is PG Gap"}
                                    : (c === "Is PG Gap" ? {label: c, tool: true} : c)
            );
            let pgRows = ePg.map(p => cols.map(c => {
                if (c === "Issue Rating") return makePill(p[c]||"", "severity");
                if (c === "Issue ID") return '<span class="id-chip" data-source="pg-gap">' + esc(String(p[c]||"")) + '</span>';
                return esc(String(p[c]||""));
            }));
            pgBody += buildTableHTML({
                id: "src-pg-gap-table",
                headers: pgHeaders,
                rows: pgRows,
            });
        } else { pgBody += "<p class='meta'>No PG gaps for this entity (mapped to a PRSA control). Unmapped PG gaps appear only in the Excel <em>Source - PG Gaps</em> tab.</p>"; }
    } else { pgBody += "<p class='meta'>No PG gap data in workbook.</p>"; }
    srcHtml += mkExpander(pgHas, pgHeader, pgBody, "src-pg-gap");

    // BM Activities
    let bmaHeader = "Business Monitoring Activities";
    let bmaBody = __BANNER_BMA_JSON__;
    let bmaHas = false;
    if (bmaData.length) {
        let bmaEidCol = resolveCol(bmaData, ["Related Audit Entity", "Audit Entity ID"]);
        if (bmaEidCol) {
            let eb = bmaData.filter(b => String(b[bmaEidCol]||"").trim() === eid);
            if (eb.length) {
                bmaHas = true;
                bmaHeader = 'Business Monitoring Activities \u2014 ' + eb.length + ' instance' + (eb.length === 1 ? "" : "s");
                let bmaApproved = ["Activity Instance ID", "Related BM Activity Title", "Summary of Results", "If yes, please describe impact", "Business Monitoring Cases", "Planned Instance Completion Date"];
                let cols = bmaApproved.filter(c => eb[0].hasOwnProperty(c));
                let bmaRows = eb.map(b => cols.map(c => {
                    if (c === "Activity Instance ID") return '<span class="id-chip">' + esc(String(b[c]||"")) + '</span>';
                    return esc(String(b[c]||""));
                }));
                bmaBody += buildTableHTML({
                    id: "src-bma-table",
                    headers: cols,
                    rows: bmaRows,
                });
            } else { bmaBody += "<p class='meta'>No BM Activities for this entity.</p>"; }
        } else { bmaBody += "<p class='meta'>BMA data missing entity column.</p>"; }
    } else { bmaBody += "<p class='meta'>No BM Activities data in workbook.</p>"; }
    srcHtml += mkExpander(bmaHas, bmaHeader, bmaBody, "src-bma");

    document.getElementById("entity-sources").innerHTML = srcHtml;
}

// ==================== METHODOLOGY VIEW ====================
// Read-only prose surface. Sections are sourced from
// risk_taxonomy_transformer/methodology.yaml (tab: "LUminate Methodology")
// and embedded as a flat list of [topic, detail] rows. Renders with the
// existing banner/CSS chrome; no filters, no drill-down.
function renderMethodologyView() {
    let host = document.getElementById("methodology-host");
    if (!host) return;
    if (host.dataset.rendered === "1") return;  // idempotent — render once
    let rows = methodologyRows || [];
    let html = '';
    let bullets = [];
    function flushBullets() {
        if (bullets.length) {
            html += '<ul style="margin: 4px 0 12px 24px;">' +
                bullets.map(b => '<li style="margin-bottom: 6px;">' + esc(b) + '</li>').join('') +
                '</ul>';
            bullets = [];
        }
    }
    for (let r of rows) {
        let topic = String(r[0] || '').trim();
        let detail = String(r[1] || '').trim();
        if (!topic && !detail) {
            flushBullets();
            continue;
        }
        if (topic === "LUminate Methodology") {
            flushBullets();
            html += '<h2 style="margin-top: 0;">' + esc(topic) + '</h2>';
            continue;
        }
        if (topic) {
            // New section header.
            flushBullets();
            html += '<h3 style="margin-top: 22px; color: var(--blue);">' + esc(topic) + '</h3>';
            continue;
        }
        // detail-only row — body paragraph or bullet.
        if (detail.startsWith("• ")) {
            bullets.push(detail.slice(2).trim());
        } else {
            flushBullets();
            html += '<p style="margin: 6px 0;">' + esc(detail) + '</p>';
        }
    }
    flushBullets();
    host.innerHTML = html;
    host.dataset.rendered = "1";
}

// ==================== RISK CATEGORY VIEW ====================
function renderRiskView() {
    let l2 = getTypeaheadValue("risk-select");
    if (!l2) return;
    let baseRows = auditData.filter(r => r["New L2"] === l2);
    let rows = getFilteredAuditData(baseRows);
    if (!rows.length) {
        document.getElementById("risk-title").innerHTML = '<h2 style="border:none;margin-top:0;">Risk Category: ' + esc(l2) + '</h2>';
        document.getElementById("risk-banner").innerHTML = '<div class="banner banner-info">No rows match the current filters.</div>';
        document.getElementById("risk-metrics").innerHTML = "";
        return;
    }

    let l1Vals = [...new Set(rows.map(r => r["New L1"]).filter(x => !isEmpty(x)))];
    let l1Label = l1Vals.length ? l1Vals[0] : "";
    let titleHtml = '<h2 style="border:none;margin-top:0;">Risk Category: ' + esc(l2) + '</h2>';
    if (l1Label) titleHtml += '<div class="meta">L1: ' + esc(l1Label) + ' \u00B7 ' + new Set(rows.map(r=>r["Entity ID"])).size + ' entities in scope</div>';
    document.getElementById("risk-title").innerHTML = titleHtml;

    // Clear the banner container so a previous render's empty-filter-state
    // info banner doesn't linger when filters now match rows.
    document.getElementById("risk-banner").innerHTML = "";

    // Summary metrics
    let totalEntities = new Set(rows.map(r => r["Entity ID"])).size;
    let applicableMask = rows.filter(r => r["Status"] === "Applicable");
    let isAI = r => String(r["Decision Basis"]||"").startsWith("AI review");
    let evidenceEntities = new Set(applicableMask.filter(r => !isAI(r)).map(r => r["Entity ID"])).size;
    let aiEntities = new Set(applicableMask.filter(r => isAI(r)).map(r => r["Entity ID"])).size;
    let applicableEntities = new Set(applicableMask.map(r => r["Entity ID"])).size;
    let pctApp = totalEntities ? (applicableEntities / totalEntities * 100).toFixed(0) : 0;
    document.getElementById("risk-metrics").innerHTML =
        '<div class="metric-card"><div class="value">' + totalEntities + '</div><div class="label">Total Entities</div></div>'
        + '<div class="metric-card"><div class="value">' + evidenceEntities + '</div><div class="label">Evidence-Based</div></div>'
        + '<div class="metric-card"><div class="value">' + aiEntities + '</div><div class="label">AI-Proposed</div></div>'
        + '<div class="metric-card"><div class="value">' + pctApp + '%</div><div class="label">% Applicable</div></div>';

    let statusOrder = {};
    Object.keys(STATUS_CONFIG).forEach(s => statusOrder[s] = STATUS_CONFIG[s].sort);
    rows.sort((a,b) => {
        let ra = RATING_RANK[a["Inherent Risk Rating"]]||0, rb = RATING_RANK[b["Inherent Risk Rating"]]||0;
        if (rb !== ra) return rb - ra;
        return (statusOrder[a["Status"]]||9) - (statusOrder[b["Status"]]||9);
    });
    let tRows = rows.map(r => {
        let rm = getEntityMeta(r["Entity ID"]);
        return [
        r["Entity ID"]||"", rm["Entity Name"]||"", rm["Audit Leader"]||"",
        isEmpty(r["Inherent Risk Rating"]) ? "\u2014" : r["Inherent Risk Rating"],
        statusLabel(r["Status"]),
        r["Legacy Source"]||"", r["Decision Basis"]||"",
        isEmpty(r["Additional Signals"]) ? "" : r["Additional Signals"]
        ];
    });
    document.getElementById("risk-entity-host").innerHTML = buildTableHTML({
        id: "risk-entity-table",
        headers: [
            {label: "Entity ID",     type: "str"},
            {label: "Entity Name",   type: "str"},
            {label: "Audit Leader",  type: "str"},
            {label: "Legacy Risk Rating", type: "str"},
            {label: "Suggested Status",   type: "str"},
            {label: "Legacy Source", type: "str"},
            {label: "Decision Basis", type: "str", expand: true},
            {label: "Signals",        type: "str", expand: true},
        ],
        rows: tRows,
    });

    // Rating Concentration chart removed — Entity Breakdown table + Entity
    // Drill-Down list already answer "how does this L2 distribute across
    // entities" without the additional chart real estate.

    // Populate the L2 name in the cross-source pointer below the IAG section.
    let l2NameSpan = document.getElementById("risk-l2-name");
    if (l2NameSpan) l2NameSpan.textContent = l2;

    // Per-entity drill-down
    let ddHtml = "";
    rows.forEach(r => {
        let eid2 = r["Entity ID"]||"";
        let rm = getEntityMeta(eid2);
        let status = r["Status"]||"";
        let irr = r["Inherent Risk Rating"]||"";
        let ename = rm["Entity Name"]||"";
        let parts = [icon(status) + " " + eid2];
        if (!isEmpty(ename)) parts.push(ename);
        parts.push(status);
        if (!isEmpty(irr) && irr !== "Not Applicable") parts.push(irr);
        let label = parts.join(" \u00B7 ");
        let detail = detailData.find(d => String(d["entity_id"])===eid2 && d["new_l2"]===l2);
        let entityDetailRows = detailData.filter(d => String(d["entity_id"]) === String(eid2));

        let body = '<div class="entity-context">';
        if (!isEmpty(ename)) body += '<strong>' + esc(ename) + '</strong><br>';
        if (!isEmpty(rm["Entity Overview"])) body += '<span class="meta">' + esc(rm["Entity Overview"]) + '</span><br>';
        let meta2 = [];
        if (!isEmpty(rm["Audit Leader"])) meta2.push("AL: " + esc(rm["Audit Leader"]));
        if (!isEmpty(rm["PGA"])) meta2.push("PGA: " + esc(rm["PGA"]));
        if (meta2.length) body += '<span class="meta">' + meta2.join(" \u00B7 ") + '</span>';
        body += "</div><hr style='border:none;border-top:1px solid var(--border);margin:8px 0'>";
        body += renderDrilldownBody(r, detail, entityDetailRows, eid2);
        ddHtml += mkExpander(false, label, body, "risk-drill:" + l2 + ":" + eid2);
    });
    document.getElementById("risk-drilldown").innerHTML = ddHtml;

    // IAG Issues for this L2
    let allFindings = findingsData.filter(f => {
        let fL2 = String(f["l2_risk"]||f["Mapped To L2(s)"]||f["Risk Dimension Categories"]||"");
        return fL2.includes(l2);
    });
    let inScope = new Set(rows.map(r => String(r["Entity ID"])));
    allFindings = allFindings.filter(f => inScope.has(String(f["entity_id"]||f["Audit Entity ID"]||"")));
    let fHtml = "";
    if (allFindings.length) {
        let fEntities = new Set(allFindings.map(f => f["entity_id"]||f["Audit Entity ID"]));
        fHtml = '<div class="banner banner-info"><strong>' + allFindings.length + ' IAG issues</strong> across <strong>' + fEntities.size + ' entities</strong> tagged to this L2.</div>';
        let findingRows = allFindings.map(f => [
            esc(String(f["entity_id"]||f["Audit Entity ID"]||"")),
            esc(String(f["issue_id"]||f["Finding ID"]||"")),
            makePill(f["severity"]||"", "severity"),
            esc(String(f["status"]||f["Finding Status"]||"")),
            esc(String(f["issue_title"]||f["Finding Name"]||"")),
        ]);
        fHtml += buildTableHTML({
            id: "risk-iag-table",
            headers: ["Entity", "Finding ID", "Severity", "Status", "Title"],
            rows: findingRows,
            minimal: true,
        });
    } else { fHtml = "<p class='meta'>No IAG issues tagged to this L2 in the current scope.</p>"; }
    document.getElementById("risk-findings").innerHTML = fHtml;
}

// ==================== INITIALIZATION ====================
window.addEventListener("load", () => {
    // Entity typeahead
    const entityTA = makeTypeahead(
        "entity-select",
        "entity-typeahead-list",
        _buildEntityOptions,
        (val) => { renderEntityView(); }
    );
    if (entityTA) entityTA.rebuild();
    // Risk (L2) typeahead
    const riskTA = makeTypeahead(
        "risk-select",
        "risk-typeahead-list",
        () => l2Risks.map(l => ({ value: l, label: l })),
        (val) => { renderRiskView(); }
    );
    if (riskTA) riskTA.rebuild();
    let alSelect = document.getElementById("filter-al");
    auditLeaders.forEach(v => { let o = document.createElement("option"); o.value = v; o.text = v; alSelect.add(o); });
    let pgaSelect = document.getElementById("filter-pga");
    pgaList.forEach(v => { let o = document.createElement("option"); o.value = v; o.text = v; pgaSelect.add(o); });
    let teamSelect = document.getElementById("filter-team");
    coreTeams.forEach(v => { let o = document.createElement("option"); o.value = v; o.text = v; teamSelect.add(o); });
    renderEntityView();
    document.addEventListener("keydown", (e) => {
        if (e.key !== "T" || !e.shiftKey || e.ctrlKey || e.metaKey || e.altKey) return;
        const t = e.target;
        if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
        const btn = document.getElementById("sub-tab-trace");
        if (!btn) return;
        btn.style.display = (btn.style.display === "none") ? "" : "none";
    });
});
