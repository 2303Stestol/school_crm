document.addEventListener('DOMContentLoaded', () => {
  const panels = document.querySelectorAll('[data-lessons-panel]');

  panels.forEach((panel) => {
    panel.addEventListener('click', (event) => {
      const removeButton = event.target.closest('[data-remove-lesson]');
      if (!removeButton) return;

      const listItem = removeButton.closest('li');
      if (listItem) {
        listItem.classList.add('is-removing');
        window.setTimeout(() => {
          listItem.remove();
        }, 150);
      }
    });
  });
});
