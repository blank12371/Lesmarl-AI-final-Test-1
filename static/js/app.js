/* Lesmarl AI - Made by Mashrur Ahmed Arib - MIT License. See LICENSE. */
document.addEventListener('DOMContentLoaded', () => {
  const theme = localStorage.getItem('lesmarl-theme') || 'dark';
  window.LesmarlUI.setTheme(theme);

  const textarea = document.getElementById('prompt-input');
  window.LesmarlUI.bindTextareaAutoGrow(textarea);
  bindVoiceInput(textarea);
  let csrfToken = '';
  let currentUser = null;
  let authMode = 'login';
  const attachments = [];
  const allowedFileExtensions = /\.(txt|md|csv|json|js|ts|py|html|css|sql|sh|yaml|yml|xml|toml|java|c|cpp|h|go|rs)$/i;
  const maxFileBytes = 200 * 1024;
  const maxTotalAttachmentBytes = 140 * 1024;

  initializeAccount();
  document.getElementById('new-chat').addEventListener('click', startNewChat);
  document.getElementById('open-settings').addEventListener('click', openSettings);
  document.getElementById('settings-account').addEventListener('click', openAuth);
  document.getElementById('account-button').addEventListener('click', openAuth);
  document.getElementById('sign-out-button').addEventListener('click', signOut);
  document.getElementById('settings-sign-out').addEventListener('click', signOut);
  document.getElementById('auth-form').addEventListener('submit', submitAuth);
  document.getElementById('enhance-prompt').addEventListener('click', enhancePrompt);
  document.getElementById('accept-enhanced-prompt').addEventListener('click', acceptEnhancedPrompt);
  document.getElementById('discard-enhanced-prompt').addEventListener('click', () => document.getElementById('enhance-dialog').close());
  document.querySelectorAll('[data-auth-mode]').forEach((button) => {
    button.addEventListener('click', () => setAuthMode(button.dataset.authMode));
  });

  constantButtons();
  document.getElementById('toggle-theme').addEventListener('click', () => {
    applyTheme(document.body.dataset.theme === 'dark' ? 'light' : 'dark');
  });
  document.getElementById('settings-theme').value = theme;
  document.getElementById('settings-theme').addEventListener('change', (event) => applyTheme(event.target.value));
  document.getElementById('settings-model').addEventListener('change', (event) => {
    if (event.target.value) localStorage.setItem('lesmarl-default-model', event.target.value);
  });
  document.getElementById('open-commands').addEventListener('click', openCommands);
  document.getElementById('command-search').addEventListener('input', filterCommands);
  document.getElementById('command-list').addEventListener('click', runCommand);
  document.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      openCommands();
    }
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
    if (!currentUser) {
      openAuth();
      return;
    }
    const prompt = textarea.value.trim();
    if (!prompt && !attachments.length) return;
    const submittedAttachments = [...attachments];
    window.LesmarlUI.hideEmptyState();
    window.LesmarlChat.renderMessage('user', prompt || 'Please review the attached files.', submittedAttachments.map((file) => file.name).join(', ') || 'just now');
    textarea.value = '';
    textarea.dispatchEvent(new Event('input'));

    try {
      await window.LesmarlChat.streamPrompt(prompt, submittedAttachments);
      submittedAttachments.forEach((file) => removeAttachment(file.id));
    } catch (error) {
      window.LesmarlChat.renderMessage('assistant', `Error: ${error.message}`, 'error');
    }
  });

  document.getElementById('stop-button').addEventListener('click', () => {
    window.LesmarlChat.stop();
  });

  document.getElementById('attach-file').addEventListener('click', () => document.getElementById('file-input').click());
  document.getElementById('file-input').addEventListener('change', handleFileSelection);
  document.getElementById('attachment-list').addEventListener('click', (event) => {
    const button = event.target.closest('[data-remove-attachment]');
    if (button) removeAttachment(button.dataset.removeAttachment);
  });

  function applyTheme(value) {
    const nextTheme = value === 'light' ? 'light' : 'dark';
    localStorage.setItem('lesmarl-theme', nextTheme);
    window.LesmarlUI.setTheme(nextTheme);
    document.getElementById('settings-theme').value = nextTheme;
  }

  async function initializeAccount() {
    try {
      const response = await fetch('/api/auth/me', { credentials: 'same-origin' });
      const data = await response.json();
      csrfToken = data.csrf_token || '';
      currentUser = data.user;
      updateAccountControls();
      if (!currentUser) openAuth();
    } catch (error) {
      document.getElementById('auth-message').textContent = 'Could not connect to the account service. Refresh and try again.';
    }
  }

  async function handleFileSelection(event) {
    const input = event.currentTarget;
    for (const file of Array.from(input.files || [])) {
      if (!allowedFileExtensions.test(file.name)) {
        window.alert(`${file.name}: choose a supported text or source-code file.`);
        continue;
      }
      if (file.size > maxFileBytes) {
        window.alert(`${file.name}: files must be 200 KB or smaller.`);
        continue;
      }
      const currentTotal = attachments.reduce((total, attachment) => total + attachment.size, 0);
      if (currentTotal + file.size > maxTotalAttachmentBytes) {
        window.alert('Attachments are limited to 140 KB total per message to fit the server request limit.');
        break;
      }
      try {
        const content = await file.text();
        attachments.push({ id: crypto.randomUUID(), name: file.name, size: file.size, content });
        renderAttachments();
      } catch (error) {
        window.alert(`${file.name}: the file could not be read.`);
      }
    }
    input.value = '';
  }

  function renderAttachments() {
    const container = document.getElementById('attachment-list');
    container.replaceChildren();
    attachments.forEach((file) => {
      const chip = document.createElement('span');
      chip.className = 'attachment-chip';
      const name = document.createElement('span');
      name.textContent = file.name;
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.textContent = '×';
      remove.dataset.removeAttachment = file.id;
      remove.setAttribute('aria-label', `Remove ${file.name}`);
      chip.append(name, remove);
      container.append(chip);
    });
  }

  function removeAttachment(id) {
    const index = attachments.findIndex((file) => file.id === id);
    if (index >= 0) attachments.splice(index, 1);
    renderAttachments();
  }

  async function enhancePrompt() {
    const prompt = textarea.value.trim();
    const message = document.getElementById('enhance-message');
    if (!currentUser) {
      openAuth();
      return;
    }
    if (!prompt) {
      message.textContent = 'Write a draft prompt first.';
      document.getElementById('enhance-dialog').showModal();
      return;
    }

    const button = document.getElementById('enhance-prompt');
    button.disabled = true;
    button.textContent = 'Enhancing...';
    try {
      const response = await fetch('/api/enhance', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({
          prompt,
          model: localStorage.getItem('lesmarl-default-model') || null
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error?.message || 'Could not enhance the prompt.');
      document.getElementById('enhanced-prompt-preview').value = data.prompt;
      message.textContent = '';
      document.getElementById('enhance-dialog').showModal();
    } catch (error) {
      window.alert(error.message);
    } finally {
      button.disabled = false;
      button.textContent = 'Enhance';
    }
  }

  function acceptEnhancedPrompt() {
    textarea.value = document.getElementById('enhanced-prompt-preview').value;
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    document.getElementById('enhance-dialog').close();
    textarea.focus();
  }

  function updateAccountControls() {
    const signedIn = Boolean(currentUser);
    document.getElementById('account-name').textContent = signedIn ? currentUser.name : '';
    document.getElementById('account-name').hidden = !signedIn;
    document.getElementById('account-button').hidden = signedIn;
    document.getElementById('sign-out-button').hidden = !signedIn;
    document.getElementById('settings-account').hidden = signedIn;
    document.getElementById('settings-sign-out').hidden = !signedIn;
    document.getElementById('settings-account').textContent = signedIn ? currentUser.name : 'Sign in';
  }

  function setAuthMode(mode) {
    authMode = mode === 'register' ? 'register' : 'login';
    const isRegister = authMode === 'register';
    document.getElementById('auth-title').textContent = isRegister ? 'Create account' : 'Sign in';
    document.getElementById('auth-submit').textContent = isRegister ? 'Create account' : 'Sign in';
    document.getElementById('auth-password').autocomplete = isRegister ? 'new-password' : 'current-password';
    document.getElementById('auth-message').textContent = isRegister ? 'Use a name and a password of at least 10 characters.' : '';
    document.querySelectorAll('[data-auth-mode]').forEach((button) => {
      button.classList.toggle('is-selected', button.dataset.authMode === authMode);
    });
  }

  function openAuth() {
    document.getElementById('settings-dialog').close();
    document.getElementById('commands-dialog').close();
    setAuthMode(currentUser ? 'login' : authMode);
    const dialog = document.getElementById('auth-dialog');
    if (!dialog.open) dialog.showModal();
    document.getElementById('auth-name').focus();
  }

  async function submitAuth(event) {
    event.preventDefault();
    const message = document.getElementById('auth-message');
    const submit = document.getElementById('auth-submit');
    message.textContent = '';
    submit.disabled = true;
    try {
      const response = await fetch(`/api/auth/${authMode === 'register' ? 'register' : 'login'}`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({
          name: document.getElementById('auth-name').value,
          password: document.getElementById('auth-password').value
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error?.message || 'Account request failed.');
      currentUser = data.user;
      csrfToken = data.csrf_token || '';
      document.getElementById('auth-form').reset();
      document.getElementById('auth-dialog').close();
      updateAccountControls();
    } catch (error) {
      message.textContent = error.message;
    } finally {
      submit.disabled = false;
    }
  }

  async function signOut() {
    try {
      const response = await fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-CSRF-Token': csrfToken }
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error?.message || 'Could not sign out.');
      csrfToken = data.csrf_token || '';
      currentUser = null;
      updateAccountControls();
      startNewChat();
      openAuth();
    } catch (error) {
      window.alert(error.message);
    }
  }

  function startNewChat() {
    document.getElementById('messages').replaceChildren();
    document.getElementById('empty-state').hidden = false;
    textarea.value = '';
    textarea.dispatchEvent(new Event('input'));
    document.getElementById('chat-panel')?.scrollTo({ top: 0 });
    textarea.focus();
  }

  async function openSettings() {
    const dialog = document.getElementById('settings-dialog');
    if (!dialog.open) dialog.showModal();
    try {
      const response = await fetch('/api/models');
      const data = await response.json();
      const select = document.getElementById('settings-model');
      const savedModel = localStorage.getItem('lesmarl-default-model') || data.default || '';
      select.replaceChildren();
      (data.models || []).forEach((model) => {
        const option = document.createElement('option');
        option.value = model.id;
        option.textContent = model.name;
        select.append(option);
      });
      if (savedModel && !Array.from(select.options).some((option) => option.value === savedModel)) {
        const option = document.createElement('option');
        option.value = savedModel;
        option.textContent = `${savedModel} (configured)`;
        select.prepend(option);
      }
      if (!select.options.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'Model list unavailable';
        select.append(option);
      }
      select.value = savedModel;
    } catch (error) {
      document.getElementById('settings-model').replaceChildren(new Option('Model list unavailable', ''));
    }
  }

  function openCommands() {
    const dialog = document.getElementById('commands-dialog');
    if (!dialog.open) dialog.showModal();
    const search = document.getElementById('command-search');
    search.value = '';
    filterCommands();
    search.focus();
  }

  function filterCommands() {
    const query = document.getElementById('command-search').value.trim().toLowerCase();
    document.querySelectorAll('#command-list [data-command]').forEach((button) => {
      button.hidden = !button.textContent.toLowerCase().includes(query);
    });
  }

  function runCommand(event) {
    const command = event.target.closest('[data-command]')?.dataset.command;
    if (!command) return;
    document.getElementById('commands-dialog').close();
    if (command === 'new') startNewChat();
    if (command === 'settings') openSettings();
    if (command === 'theme') applyTheme(document.body.dataset.theme === 'dark' ? 'light' : 'dark');
    if (command === 'account') openAuth();
  }

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
