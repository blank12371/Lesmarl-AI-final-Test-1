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

  async function streamPrompt(prompt, attachments = [], mode = 'general', history = []) {
    const controller = new AbortController();
    activeStream = controller;
    const modeInstructions = {
      general: 'Be a clear, balanced, helpful assistant. Answer directly and organize longer replies.',
      code: 'Act as a careful software engineering assistant. Explain assumptions, provide correct code, and point out important edge cases.',
      writer: 'Act as a writing partner. Match the requested audience and tone, and produce polished, original writing.',
      study: 'Act as a patient tutor. Explain ideas step by step, check understanding, and guide the learner instead of merely giving answers.'
    };
    const messages = [
      { role: 'system', content: modeInstructions[mode] || modeInstructions.general },
      ...history.slice(-20),
      { role: 'user', content: prompt || 'Please review the attached files.' }
    ];
    const attachmentChunkSize = 12_000;
    attachments.forEach((file) => {
      const chunks = file.content.match(new RegExp(`[\\s\\S]{1,${attachmentChunkSize}}`, 'g')) || [''];
      chunks.forEach((chunk, index) => {
        const chunkLabel = chunks.length > 1 ? ` (part ${index + 1}/${chunks.length})` : '';
        messages.push({ role: 'user', content: `Attached file: ${file.name}${chunkLabel}\n\n${chunk}` });
      });
    });
    const requestBody = JSON.stringify({
      model: localStorage.getItem('lesmarl-default-model') || null,
      messages,
      temperature: 0.7,
      max_tokens: 4096
    });
    if (new TextEncoder().encode(requestBody).length > 180 * 1024) {
      throw new Error('The prompt and attachments exceed the request size limit. Remove a file and try again.');
    }
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: requestBody,
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

    try {
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
            const modelLabel = doneMeta.model || 'complete';
            message.node.querySelector('.message__header span').textContent = modelLabel;
            if (doneMeta.truncated) {
              const contentNode = message.node.querySelector('.message__content');
              contentNode.insertAdjacentHTML('beforeend', '<p class="response-warning">This response reached the model output limit. Ask to continue for the rest.</p>');
            }
          } else if (event === 'error') {
            const err = JSON.parse(text);
            throw new Error(err.message || 'Unable to complete the request.');
          }
        }
      }
    } catch (error) {
      if (controller.signal.aborted) {
        message.node.querySelector('.message__header span').textContent = 'Stopped';
        return currentText;
      }
      message.node.remove();
      throw error;
    } finally {
      if (activeStream === controller) activeStream = null;
    }

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
