/* Lesmarl AI - Made by Mashrur Ahmed Arib - MIT License. See LICENSE. */
document.addEventListener('DOMContentLoaded', () => {
  const theme = localStorage.getItem('lesmarl-theme') || 'dark';
  window.LesmarlUI.setTheme(theme);

  const textarea = document.getElementById('prompt-input');
  window.LesmarlUI.bindTextareaAutoGrow(textarea);

  constantButtons();
  document.getElementById('toggle-theme').addEventListener('click', () => {
    const next = document.body.dataset.theme === 'dark' ? 'light' : 'dark';
    localStorage.setItem('lesmarl-theme', next);
    window.LesmarlUI.setTheme(next);
  });

  document.getElementById('prompt-grid').addEventListener('click', (event) => {
    const button = event.target.closest('.prompt-card');
    if (!button) return;
    textarea.value = button.textContent.trim();
    textarea.dispatchEvent(new Event('input'));
  });

  document.getElementById('mode-strip').addEventListener('click', (event) => {
    const card = event.target.closest('.mode-card');
    if (!card) return;
    window.LesmarlUI.setModeSelection(card.dataset.mode);
  });

  document.getElementById('composer').addEventListener('submit', async (event) => {
    event.preventDefault();
    const prompt = textarea.value.trim();
    if (!prompt) return;
    window.LesmarlUI.hideEmptyState();
    window.LesmarlChat.renderMessage('user', prompt, 'just now');
    textarea.value = '';
    textarea.dispatchEvent(new Event('input'));

    try {
      await window.LesmarlChat.streamPrompt(prompt);
    } catch (error) {
      window.LesmarlChat.renderMessage('assistant', `Error: ${error.message}`, 'error');
    }
  });

  document.getElementById('stop-button').addEventListener('click', () => {
    window.LesmarlChat.stop();
  });

  document.getElementById('attach-file').addEventListener('click', () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.multiple = true;
    input.click();
  });

  function constantButtons() {
    document.querySelectorAll('.prompt-card, .mode-card, .icon-button, .ghost-button, .primary-button, .secondary-button').forEach((button) => {
      button.addEventListener('mouseenter', () => button.style.transform = 'translateY(-1px)');
      button.addEventListener('mouseleave', () => button.style.transform = 'translateY(0)');
    });
  }
});
