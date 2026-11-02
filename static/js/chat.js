/* Lesmarl AI - Made by Mashrur Ahmed Arib - MIT License. See LICENSE. */
window.LesmarlChat = (() => {
  let activeStream = null;

  function renderMessage(role, content, meta = '') {
    const root = document.getElementById('messages');
    const wrapper = document.createElement('article');
    wrapper.className = 'message ' + (role === 'assistant' ? 'message--assistant' : 'message--user');
    wrapper.innerHTML = `
      <div class="message__header">
        <strong>${role === 'assistant' ? 'Assistant' : 'You'}</strong>
        <span>${meta}</span>
      </div>
      <div class="message__content">${window.LesmarlMarkdown.render(content)}</div>
    `;
    root.appendChild(wrapper);
    wrapper.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  async function streamPrompt(prompt) {
    const controller = new AbortController();
    activeStream = controller;
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({
        model: null,
        messages: [{ role: 'user', content: prompt }],
        temperature: 0.7,
        max_tokens: 512
      }),
      signal: controller.signal
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload?.error?.message || 'Unable to reach the model service.');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let currentText = '';
    const message = {
      role: 'assistant',
      content: '',
      node: document.createElement('article')
    };

    message.node.className = 'message message--assistant';
    message.node.innerHTML = `
      <div class="message__header"><strong>Assistant</strong><span>Streaming</span></div>
      <div class="message__content"></div>
    `;
    document.getElementById('messages').appendChild(message.node);

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop() || '';

      for (const part of parts) {
        if (!part.trim()) continue;
        const eventLine = part.match(/^event:\s*(.+)$/m);
        const dataLine = part.match(/^data:\s*(.*)$/m);
        if (!eventLine || !dataLine) continue;
        const event = eventLine[1].trim();
        const text = dataLine[1];
        if (event === 'meta') {
          const meta = JSON.parse(text);
          message.node.querySelector('.message__header span').textContent = meta.model || 'model';
        } else if (event === 'token') {
          const token = JSON.parse(text).text || '';
          currentText += token;
          const contentNode = message.node.querySelector('.message__content');
          contentNode.innerHTML = window.LesmarlMarkdown.render(currentText);
        } else if (event === 'done') {
          const doneMeta = JSON.parse(text);
          message.node.querySelector('.message__header span').textContent = doneMeta.model || 'complete';
        } else if (event === 'error') {
          const err = JSON.parse(text);
          const contentNode = message.node.querySelector('.message__content');
          contentNode.innerHTML = `<p class="error-box">${window.LesmarlMarkdown.escapeHtml(err.message || 'Unable to complete the request.')}</p>`;
        }
      }
    }

    activeStream = null;
    return currentText;
  }

  function stop() {
    if (activeStream) {
      activeStream.abort();
      activeStream = null;
    }
  }

  return { renderMessage, streamPrompt, stop };
})();
