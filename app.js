'use strict';

const STATUSES = ['Not started', 'Applied', 'Online Test', 'Interview', 'Offer', 'Rejected'];

const DISC_EMOJI = {
  'Aerospace Engineering':    '✈️',
  'Biomedical Engineering':   '🧬',
  'Chemical Engineering':     '⚗️',
  'Civil Engineering':        '🏗️',
  'Electrical & Electronics': '⚡',
  'Mechanical Engineering':   '⚙️',
  'Renewable Energy':         '☀️',
  'Robotics & Automation':    '🤖',
  'Software Engineering':     '💻',
  'Systems Engineering':      '🔧',
};
const STALE_DAYS = 60;

let allEmployers = [];
let currentSort = { field: 'deadline', dir: 'asc' };
let currentDiscipline = 'all';
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

  document.getElementById('discipline-filter').addEventListener('change', e => {
    currentDiscipline = e.target.value;
    render();
  });

  document.getElementById('status-filter').addEventListener('change', e => {
    currentOpenStatus = e.target.value;
    render();
  });

  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      btn.classList.add('active');
      currentCategory = btn.dataset.category;
      render();
    });
  });

  document.getElementById('export-btn').addEventListener('click', exportCSV);

  render();
}

// ── Render ─────────────────────────────────────────────────────────────────

function render() {
  let rows = allEmployers;
  rows = filterByCategory(rows, currentCategory);
  rows = filterByDiscipline(rows, currentDiscipline);
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
  tbody.innerHTML = rows.map(rowHTML).join('');

  rows.forEach(e => {
    const sel = document.getElementById(`status-${e.id}`);
    if (sel) {
      const saved = loadStatus(e.id);
      sel.value = saved;
      sel.dataset.status = saved;
    }
  });
}

function rowHTML(e) {
  const disciplines = (e.disciplines || []).map(d =>
    `<span class="disc-emoji" title="${d}">${DISC_EMOJI[d] || d}</span>`
  ).join('');
  const stale = isStale(e.last_verified) ? `<span class="stale-badge" title="Last verified ${e.last_verified}">OLD</span>` : '';
  const notes = e.early_closure_note
    ? `⚠️ ${e.early_closure_note}`
    : (e.rolling_basis ? 'Rolling — apply early' : '');

  return `
    <tr>
      <td>
        <select class="status-select" id="status-${e.id}" onchange="onStatusChange('${e.id}', this)">
          ${STATUSES.map(s => `<option value="${s}">${s}</option>`).join('')}
        </select>
      </td>
      <td><a class="employer-link" href="${e.url}" target="_blank" rel="noopener">${e.employer}</a></td>
      <td>${e.scheme_name}</td>
      <td><div class="tags">${disciplines}</div></td>
      <td>${dateCellHTML(e.opening_date, false)}</td>
      <td>${dateCellHTML(e.deadline, true, e)}${stale}</td>
      <td class="col-locations">${(e.locations || []).join(', ')}</td>
      <td class="col-rolling">${e.rolling_basis ? '<span class="rolling-yes">✓</span>' : '<span class="rolling-no">—</span>'}</td>
      <td class="col-notes">${notes}</td>
    </tr>`;
}

function dateCellHTML(dateStr, isDeadline, e) {
  if (isDeadline && e && (e.status === 'rolling' || e.rolling_basis)) {
    return `<span class="deadline-date rolling">Rolling</span>`;
  }
  if (!dateStr) return `<span class="deadline-na">TBC</span>`;

  const date = new Date(dateStr);
  const formatted = date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });

  if (isDeadline) {
    const daysLeft = Math.ceil((date - Date.now()) / 86400000);
    const cls = daysLeft <= 30 && daysLeft > 0 ? 'deadline-date soon' : 'deadline-date';
    return `<span class="${cls}">${formatted}</span>`;
  }
  return `<span class="deadline-date">${formatted}</span>`;
}

// ── Filters ────────────────────────────────────────────────────────────────

function filterByCategory(employers, cat) {
  if (cat === 'all') return employers;
  return employers.filter(e => e.category === cat);
}

function filterByDiscipline(employers, discipline) {
  if (discipline === 'all') return employers;
  return employers.filter(e => (e.disciplines || []).includes(discipline));
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
  currentDiscipline = 'all';
  currentCategory = 'all';
  currentOpenStatus = 'all';
  document.getElementById('search-input').value = '';
  document.getElementById('discipline-filter').value = 'all';
  document.getElementById('status-filter').value = 'all';
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelector('.tab[data-category="all"]').classList.add('active');
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
