document.addEventListener('DOMContentLoaded', () => {
  const tables = Array.from(document.querySelectorAll('table[data-sortable]'));

  tables.forEach((table) => {
    const headers = Array.from(table.querySelectorAll('thead th'));
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    let sortState = {};

    headers.forEach((header, index) => {
      header.addEventListener('click', () => {
        const key = header.dataset.key || index.toString();
        const type = header.dataset.type || 'string';
        const direction = sortState[key] === 'asc' ? 'desc' : 'asc';
        sortState = { [key]: direction };

        headers.forEach((h) => {
          h.removeAttribute('data-active');
          h.removeAttribute('data-arrow');
        });

        header.setAttribute('data-active', direction);
        header.setAttribute('data-arrow', direction === 'asc' ? '▲' : '▼');

        const sortedRows = [...rows].sort((rowA, rowB) => {
          const cellA = rowA.children[index];
          const cellB = rowB.children[index];
          const valueA = cellA?.dataset.value ?? cellA?.textContent ?? '';
          const valueB = cellB?.dataset.value ?? cellB?.textContent ?? '';

          if (type === 'number') {
            const numA = parseFloat(String(valueA).replace(',', '.')) || 0;
            const numB = parseFloat(String(valueB).replace(',', '.')) || 0;
            return direction === 'asc' ? numA - numB : numB - numA;
          }

          return direction === 'asc'
            ? String(valueA).localeCompare(String(valueB), 'ru')
            : String(valueB).localeCompare(String(valueA), 'ru');
        });

        tbody.replaceChildren(...sortedRows);
      });
    });

    const searchInputId = table.dataset.search;
    if (searchInputId) {
      const searchInput = document.getElementById(searchInputId);
      if (searchInput) {
        searchInput.addEventListener('input', () => {
          const query = searchInput.value.trim().toLowerCase();
          rows.forEach((row) => {
            const matches = row.textContent.toLowerCase().includes(query);
            row.style.display = matches ? '' : 'none';
          });
        });
      }
    }
  });
});
