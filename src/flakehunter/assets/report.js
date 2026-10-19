document.querySelectorAll('table.sortable').forEach((table) => {
  table.querySelectorAll('th button').forEach((button) => {
    button.addEventListener('click', () => {
      const th = button.closest('th');
      const ascending = th.getAttribute('aria-sort') !== 'ascending';
      table.querySelectorAll('th').forEach((h) => h.removeAttribute('aria-sort'));
      th.setAttribute('aria-sort', ascending ? 'ascending' : 'descending');
      const body = table.tBodies[0];
      const col = th.cellIndex;
      const rows = Array.from(body.rows);
      rows.sort((a, b) => {
        const x = a.cells[col].dataset.v ?? a.cells[col].textContent.trim();
        const y = b.cells[col].dataset.v ?? b.cells[col].textContent.trim();
        const nx = Number(x);
        const ny = Number(y);
        const both = x !== '' && y !== '' && !Number.isNaN(nx) && !Number.isNaN(ny);
        const cmp = both ? nx - ny : String(x).localeCompare(String(y), 'en');
        return ascending ? cmp : -cmp;
      });
      rows.forEach((row) => body.appendChild(row));
    });
  });
});
const filter = document.getElementById('filter');
if (filter) {
  filter.addEventListener('input', () => {
    const query = filter.value.trim().toLowerCase();
    document.querySelectorAll('table.sortable tbody tr').forEach((row) => {
      row.hidden = query !== '' && !row.dataset.name.includes(query);
    });
  });
}
