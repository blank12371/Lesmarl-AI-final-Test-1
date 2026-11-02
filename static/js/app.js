/* Lesmarl AI - Made by Mashrur Ahmed Arib - MIT License. See LICENSE. */
document.addEventListener('DOMContentLoaded', () => {
  const theme = localStorage.getItem('lesmarl-theme') || 'dark';
  window.LesmarlUI.setTheme(theme);

  const textarea = document.getElementById('prompt-input');
  window.LesmarlUI.bindTextareaAutoGrow(textarea);
  bindVoiceInput(textarea);

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

  function bindVoiceInput(input) {
    const button = document.getElementById('toggle-voice');
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      button.title = 'Voice input is not supported in this browser.';
      button.addEventListener('click', () => {
        window.alert('Voice input is not supported in this browser. Try a current version of Chrome or Edge.');
      });
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = navigator.language || 'en-US';
    recognition.continuous = true;
    recognition.interimResults = true;
    let finalTranscript = '';
    let startingText = '';
    let isListening = false;

    button.addEventListener('click', () => {
      if (isListening) {
        recognition.stop();
        return;
      }
      finalTranscript = '';
      startingText = input.value;
      try {
        recognition.start();
      } catch (error) {
        window.alert('Voice input could not start. Check microphone permission and try again.');
      }
    });

    recognition.addEventListener('start', () => {
      isListening = true;
      button.textContent = 'Listening...';
      button.setAttribute('aria-pressed', 'true');
      button.title = 'Click to stop voice input.';
    });

    recognition.addEventListener('result', (event) => {
      let interimTranscript = '';
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const transcript = event.results[index][0].transcript;
        if (event.results[index].isFinal) {
          finalTranscript += transcript;
        } else {
          interimTranscript += transcript;
        }
      }
      const baseText = startingText.trimEnd();
      const separator = baseText && !/\s$/.test(startingText) ? ' ' : '';
      input.value = baseText + separator + finalTranscript + interimTranscript;
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });

    recognition.addEventListener('error', (event) => {
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
        window.alert('Microphone access was blocked. Allow microphone access for this site in your browser settings.');
      } else if (event.error !== 'no-speech' && event.error !== 'aborted') {
        window.alert('Voice input encountered an error. Check your microphone and try again.');
      }
    });

    recognition.addEventListener('end', () => {
      isListening = false;
      button.textContent = 'Voice';
      button.setAttribute('aria-pressed', 'false');
      button.title = 'Start voice input.';
    });
  }

  function constantButtons() {
    document.querySelectorAll('.prompt-card, .mode-card, .icon-button, .ghost-button, .primary-button, .secondary-button').forEach((button) => {
      button.addEventListener('mouseenter', () => button.style.transform = 'translateY(-1px)');
      button.addEventListener('mouseleave', () => button.style.transform = 'translateY(0)');
    });
  }
});
