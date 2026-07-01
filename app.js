'use strict';

const STATUSES = ['Not started', 'Applied', 'Online Test', 'Interview', 'Offer', 'Rejected'];

const STALE_DAYS = 60;

// Sector grouping — mirrors the "tier" grouping pattern (Bulge Bracket, Elite
// Boutique, etc.) from finance trackers, adapted to engineering disciplines.
// First matching discipline in this priority order determines the group.
const SECTOR_PRIORITY = [
  ['Aerospace Engineering',    'Aerospace & Defence'],
  ['Civil Engineering',        'Infrastructure & Construction'],
  ['Renewable Energy',         'Energy & Utilities'],
  ['Chemical Engineering',     'Chemical & Process'],
  ['Biomedical Engineering',   'Biomedical & Healthcare'],
  ['Mechanical Engineering',   'Industrial & Manufacturing'],
  ['Electrical & Electronics', 'Electronics & Technology'],
  ['Software Engineering',     'Software & Technology'],
  ['Systems Engineering',      'Systems & Automation'],
  ['Robotics & Automation',    'Systems & Automation'],
];

function sectorFor(e) {
  const disciplines = e.disciplines || [];
  for (const [disc, sector] of SECTOR_PRIORITY) {
    if (disciplines.includes(disc)) return sector;
  }
  return 'Other Engineering';
}

let allEmployers = [];
let currentSort = { field: 'deadline', dir: 'asc' };
let currentCategory = 'all';
let currentOpenStatus = 'all';
let currentSearch = '';

// ── Bootstrap ──────────────────────────────────────────────────────────────

async function init() {
  if (typeof DEADLINES_DATA === 'undefined') {
    document.getElementById('error-banner').classList.remove('hidden');
    document.getElementById('table-body').innerHTML =
      '<tr><td colspan="8" class="loading">Could not load data.</td></tr>';
    return;
  }
  allEmployers = DEADLINES_DATA.employers || [];

  document.getElementById('search-input').addEventListener('input', e => {
    currentSearch = e.target.value.trim().toLowerCase();
    render();
  });

  document.getElementById('status-filter').addEventListener('change', e => {
    currentOpenStatus = e.target.value;
    render();
  });

  document.querySelectorAll('.pill').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.pill').forEach(t => t.classList.remove('active'));
      btn.classList.add('active');
      currentCategory = btn.dataset.category;
      render();
    });
  });

  document.getElementById('export-btn').addEventListener('click', exportCSV);

  setupStickyScroll();
  render();
}

// ── Sticky horizontal scrollbar ───────────────────────────────────────────
// Keeps a scrollbar pinned to the bottom of the viewport that mirrors the
// table's native horizontal scroll, so it's always reachable on a tall page.

function setupStickyScroll() {
  const wrapper = document.getElementById('table-wrapper');
  const sticky = document.getElementById('sticky-hscroll');
  const stickyInner = document.getElementById('sticky-hscroll-inner');
  const table = document.getElementById('deadlines-table');

  let syncing = false;

  function refresh() {
    stickyInner.style.width = table.scrollWidth + 'px';
    const needsScroll = table.scrollWidth > wrapper.clientWidth;
    sticky.classList.toggle('visible', needsScroll);
  }

  wrapper.addEventListener('scroll', () => {
    if (syncing) return;
    syncing = true;
    sticky.scrollLeft = wrapper.scrollLeft;
    syncing = false;
  });

  sticky.addEventListener('scroll', () => {
    if (syncing) return;
    syncing = true;
    wrapper.scrollLeft = sticky.scrollLeft;
    syncing = false;
  });

  window.addEventListener('resize', refresh);
  new MutationObserver(refresh).observe(table, { childList: true, subtree: true });

  refresh();
}

// ── Render ─────────────────────────────────────────────────────────────────

function render() {
  let rows = allEmployers;
  rows = filterByCategory(rows, currentCategory);
  rows = filterByOpenStatus(rows, currentOpenStatus);
  rows = filterBySearch(rows, currentSearch);
  rows = sort(rows, currentSort.field, currentSort.dir);

  const emptyState = document.getElementById('empty-state');
  const tbody = document.getElementById('table-body');

  if (rows.length === 0) {
    emptyState.classList.remove('hidden');
    tbody.innerHTML = '';
    return;
  }

  emptyState.classList.add('hidden');
  tbody.innerHTML = groupedRowsHTML(rows);

  rows.forEach(e => {
    const sel = document.getElementById(`status-${e.id}`);
    if (sel) {
      const saved = loadStatus(e.id);
      sel.value = saved;
      sel.dataset.status = saved;
    }
  });
}

const SECTOR_ORDER = [
  'Aerospace & Defence', 'Infrastructure & Construction', 'Energy & Utilities',
  'Chemical & Process', 'Biomedical & Healthcare', 'Industrial & Manufacturing',
  'Electronics & Technology', 'Software & Technology', 'Systems & Automation',
  'Other Engineering',
];

function groupedRowsHTML(rows) {
  const groups = new Map();
  rows.forEach(e => {
    const sector = sectorFor(e);
    if (!groups.has(sector)) groups.set(sector, []);
    groups.get(sector).push(e);
  });

  const orderedSectors = [...groups.keys()].sort(
    (a, b) => SECTOR_ORDER.indexOf(a) - SECTOR_ORDER.indexOf(b)
  );

  return orderedSectors.map(sector => {
    const items = groups.get(sector);
    const header = `
      <tr class="sector-row">
        <td colspan="8">${sector} <span class="sector-count">${items.length}</span></td>
      </tr>`;
    return header + items.map(rowHTML).join('');
  }).join('');
}

function rowHTML(e) {
  const stale = isStale(e.last_verified) ? `<span class="stale-badge" title="Last verified ${e.last_verified}">OLD</span>` : '';
  const notes = e.early_closure_note
    ? `⚠️ ${e.early_closure_note}`
    : (e.rolling_basis ? 'Rolling — apply early' : '');

  const closedClass = e.status === 'closed' ? ' class="row-closed"' : '';

  return `
    <tr${closedClass}>
      <td>
        <select class="status-select" id="status-${e.id}" onchange="onStatusChange('${e.id}', this)">
          ${STATUSES.map(s => `<option value="${s}">${s}</option>`).join('')}
        </select>
      </td>
      <td><a class="employer-link" href="${e.url}" target="_blank" rel="noopener">${e.employer}</a></td>
      <td>${e.scheme_name}</td>
      ${dateCellHTML(e.opening_date, false)}
      ${dateCellHTML(e.deadline, true, e, stale)}
      <td class="col-locations">${(e.locations || []).join(', ')}</td>
      <td class="col-rolling">${e.rolling_basis ? '<span class="rolling-yes">✓</span>' : '<span class="rolling-no">—</span>'}</td>
      <td class="col-notes">${notes}</td>
    </tr>`;
}

function dateCellHTML(dateStr, isDeadline, e, extra) {
  extra = extra || '';
  if (isDeadline && e && (e.status === 'rolling' || e.rolling_basis)) {
    return `<td class="date-cell rolling"><span class="deadline-date rolling">Rolling</span>${extra}</td>`;
  }
  if (!dateStr) return `<td class="date-cell"><span class="deadline-na">TBC</span>${extra}</td>`;

  const date = new Date(dateStr);
  const formatted = date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  const daysUntil = Math.ceil((date - Date.now()) / 86400000);

  if (isDeadline) {
    const soon = daysUntil <= 30 && daysUntil > 0;
    const cellCls = soon ? 'date-cell highlight-soon' : 'date-cell';
    const spanCls = soon ? 'deadline-date soon' : 'deadline-date';
    return `<td class="${cellCls}"><span class="${spanCls}">${formatted}</span>${extra}</td>`;
  }

  // Opening date: highlight if it opens within the next 30 days (upcoming)
  // or has already opened (in the application window now).
  const isImminent = daysUntil <= 30;
  const cellCls = isImminent ? 'date-cell highlight-soon' : 'date-cell';
  return `<td class="${cellCls}"><span class="deadline-date">${formatted}</span>${extra}</td>`;
}

// ── Filters ────────────────────────────────────────────────────────────────

function filterByCategory(employers, cat) {
  if (cat === 'all') return employers;
  return employers.filter(e => e.category === cat);
}

function filterByOpenStatus(employers, status) {
  if (status === 'all') return employers;
  return employers.filter(e => e.status === status);
}

function filterBySearch(employers, query) {
  if (!query) return employers;
  return employers.filter(e =>
    e.employer.toLowerCase().includes(query) ||
    e.scheme_name.toLowerCase().includes(query)
  );
}

// ── Sort ───────────────────────────────────────────────────────────────────

function sort(employers, field, dir) {
  return [...employers].sort((a, b) => {
    const av = a[field];
    const bv = b[field];
    if (!av) return 1;
    if (!bv) return -1;
    const diff = new Date(av) - new Date(bv);
    return dir === 'asc' ? diff : -diff;
  });
}

function setSort(field) {
  if (currentSort.field === field) {
    currentSort.dir = currentSort.dir === 'asc' ? 'desc' : 'asc';
  } else {
    currentSort = { field, dir: 'asc' };
  }
  // Update icons
  const colMap = { opening_date: 'opening', deadline: 'deadline' };
  Object.entries(colMap).forEach(([f, elId]) => {
    const th = document.getElementById(`sort-${elId}`);
    const icon = th.querySelector('.sort-icon');
    if (f === currentSort.field) {
      icon.textContent = currentSort.dir === 'asc' ? '▲' : '▼';
      th.classList.add('sort-active');
    } else {
      icon.textContent = '';
      th.classList.remove('sort-active');
    }
  });
  render();
}

function resetFilters() {
  currentSearch = '';
  currentCategory = 'all';
  currentOpenStatus = 'all';
  document.getElementById('search-input').value = '';
  document.getElementById('status-filter').value = 'all';
  document.querySelectorAll('.pill').forEach(t => t.classList.remove('active'));
  document.querySelector('.pill[data-category="all"]').classList.add('active');
  render();
}

// ── Status tracker ─────────────────────────────────────────────────────────

function onStatusChange(id, select) {
  select.dataset.status = select.value;
  saveStatus(id, select.value);
}

function saveStatus(id, status) {
  try {
    status === 'Not started'
      ? localStorage.removeItem(`status_${id}`)
      : localStorage.setItem(`status_${id}`, status);
  } catch (e) {}
}

function loadStatus(id) {
  try { return localStorage.getItem(`status_${id}`) || 'Not started'; }
  catch (e) { return 'Not started'; }
}

// ── CSV export ─────────────────────────────────────────────────────────────

function exportCSV() {
  const headers = ['Employer', 'Scheme', 'Category', 'Disciplines', 'Opens', 'Closes', 'Locations', 'Status', 'Rolling', 'URL'];
  const rows = allEmployers.map(e => [
    e.employer, e.scheme_name, e.category || '',
    (e.disciplines || []).join('; '),
    e.opening_date || '', e.deadline || (e.rolling_basis ? 'Rolling' : 'TBC'),
    (e.locations || []).join('; '),
    loadStatus(e.id), e.rolling_basis ? 'Yes' : 'No', e.url
  ]);
  const csv = [headers, ...rows]
    .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
    .join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  a.download = 'eng-tracker.csv';
  a.click();
}

// ── Staleness ──────────────────────────────────────────────────────────────

function isStale(lastVerified) {
  if (!lastVerified) return true;
  return (Date.now() - new Date(lastVerified)) / 86400000 > STALE_DAYS;
}

// ── Start ──────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', init);
