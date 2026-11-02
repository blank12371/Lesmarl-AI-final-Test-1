/* Lesmarl AI - Made by Mashrur Ahmed Arib - MIT License. See LICENSE. */
window.LesmarlUI = (() => {
  function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    document.body.dataset.theme = theme;
  }

  function bindTextareaAutoGrow(textarea) {
    const resize = () => {
      textarea.style.height = 'auto';
      textarea.style.height = Math.min(textarea.scrollHeight, 220) + 'px';
    };
    textarea.addEventListener('input', resize);
    resize();
  }

  function setModeSelection(mode) {
    document.querySelectorAll('.mode-card').forEach((card) => {
      card.classList.toggle('is-selected', card.dataset.mode === mode);
    });
  }

  function hideEmptyState() {
    const empty = document.getElementById('empty-state');
    if (empty) {
      empty.hidden = true;
    }
  }

  return { setTheme, bindTextareaAutoGrow, setModeSelection, hideEmptyState };
})();
