'use strict';

const STATUSES = ['Not started', 'Applied', 'Online Test', 'Interview', 'Offer', 'Rejected'];
const STALE_DAYS = 60;

let allEmployers = [];
let currentSort = 'asc';
let currentDiscipline = 'all';

// ── Bootstrap ──────────────────────────────────────────────────────────────

async function init() {
  if (typeof DEADLINES_DATA === 'undefined') {
    document.getElementById('error-banner').classList.remove('hidden');
    document.getElementById('table-body').innerHTML =
      '<tr><td colspan="6" class="loading">Could not load data.</td></tr>';
    return;
  }
  allEmployers = DEADLINES_DATA.employers || [];

  document.getElementById('discipline-filter').addEventListener('change', e => {
    currentDiscipline = e.target.value;
    render();
  });

  document.getElementById('export-btn').addEventListener('click', exportCSV);

  render();
}

// ── Render ─────────────────────────────────────────────────────────────────

function render() {
  let rows = filter(allEmployers, currentDiscipline);
  rows = sort(rows, currentSort);

  const emptyState = document.getElementById('empty-state');
  const tbody = document.getElementById('table-body');

  if (rows.length === 0) {
    emptyState.classList.remove('hidden');
    tbody.innerHTML = '';
    return;
  }

  emptyState.classList.add('hidden');
  tbody.innerHTML = rows.map(rowHTML).join('');

  // Apply saved statuses
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
  const deadlineCell = deadlineCellHTML(e);
  const disciplines = (e.disciplines || []).map(d => `<span class="tag">${d}</span>`).join('');
  const stale = isStale(e.last_verified) ? `<span class="stale-badge" title="Verified ${e.last_verified}">OLD</span>` : '';
  const notes = e.early_closure_note
    ? `⚠️ ${e.early_closure_note}`
    : (e.rolling_basis ? 'Rolling basis — apply early' : '');

  return `
    <tr>
      <td>
        <select class="status-select" id="status-${e.id}"
                onchange="onStatusChange('${e.id}', this)">
          ${STATUSES.map(s => `<option value="${s}">${s}</option>`).join('')}
        </select>
      </td>
      <td>
        <a class="employer-link" href="${e.url}" target="_blank" rel="noopener">${e.employer}</a>
      </td>
      <td>${e.scheme_name}</td>
      <td><div class="tags">${disciplines}</div></td>
      <td>${deadlineCell}${stale}</td>
      <td class="col-notes">${notes}</td>
    </tr>`;
}

function deadlineCellHTML(e) {
  if (e.status === 'rolling' || e.rolling_basis) {
    return `<span class="deadline-date rolling">Rolling</span>`;
  }
  if (!e.deadline) {
    return `<span class="deadline-na">TBC</span>`;
  }
  const date = new Date(e.deadline);
  const daysLeft = Math.ceil((date - Date.now()) / 86400000);
  const formatted = date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  const cls = daysLeft <= 30 ? 'deadline-date soon' : 'deadline-date';
  return `<span class="${cls}" title="${daysLeft > 0 ? daysLeft + ' days left' : 'Passed'}">${formatted}</span>`;
}

// ── Filter & sort ──────────────────────────────────────────────────────────

function filter(employers, discipline) {
  if (discipline === 'all') return employers;
  return employers.filter(e => (e.disciplines || []).includes(discipline));
}

function sort(employers, direction) {
  return [...employers].sort((a, b) => {
    // Rolling/null dates always last
    if (!a.deadline) return 1;
    if (!b.deadline) return -1;
    const diff = new Date(a.deadline) - new Date(b.deadline);
    return direction === 'asc' ? diff : -diff;
  });
}

function toggleSort() {
  currentSort = currentSort === 'asc' ? 'desc' : 'asc';
  const icon = document.querySelector('#sort-col .sort-icon');
  icon.textContent = currentSort === 'asc' ? '▲' : '▼';
  render();
}

function resetFilter() {
  currentDiscipline = 'all';
  document.getElementById('discipline-filter').value = 'all';
  render();
}

// ── Status tracker (localStorage) ─────────────────────────────────────────

function onStatusChange(id, select) {
  const status = select.value;
  select.dataset.status = status;
  saveStatus(id, status);
}

function saveStatus(id, status) {
  try {
    if (status === 'Not started') {
      localStorage.removeItem(`status_${id}`);
    } else {
      localStorage.setItem(`status_${id}`, status);
    }
  } catch (e) {
    // incognito or storage quota exceeded — fail silently
  }
}

function loadStatus(id) {
  try {
    return localStorage.getItem(`status_${id}`) || 'Not started';
  } catch (e) {
    return 'Not started';
  }
}

// ── CSV export ─────────────────────────────────────────────────────────────

function exportCSV() {
  const headers = ['Employer', 'Scheme', 'Disciplines', 'Deadline', 'Status', 'Rolling', 'URL'];
  const rows = allEmployers.map(e => [
    e.employer,
    e.scheme_name,
    (e.disciplines || []).join('; '),
    e.deadline || (e.rolling_basis ? 'Rolling' : 'TBC'),
    loadStatus(e.id),
    e.rolling_basis ? 'Yes' : 'No',
    e.url
  ]);

  const csv = [headers, ...rows]
    .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
    .join('\n');

  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'eng-tracker.csv';
  a.click();
  URL.revokeObjectURL(url);
}

// ── Staleness check ────────────────────────────────────────────────────────

function isStale(lastVerified) {
  if (!lastVerified) return true;
  const days = (Date.now() - new Date(lastVerified)) / 86400000;
  return days > STALE_DAYS;
}

// ── Start ──────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', init);
