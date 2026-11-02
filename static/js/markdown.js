/* Lesmarl AI - Made by Mashrur Ahmed Arib - MIT License. See LICENSE. */
window.LesmarlMarkdown = (() => {
  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function renderInline(text) {
    let out = escapeHtml(text);
    out = out.replace(/`([^`]+)`/g, '<code>$1</code>');
    out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    out = out.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    out = out.replace(/~~([^~]+)~~/g, '<del>$1</del>');
    out = out.replace(/\[(.+?)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" rel="noopener noreferrer nofollow" target="_blank">$1</a>');
    return out;
  }

  function render(source) {
    const safe = escapeHtml(source);
    let html = safe
      .replace(/\r\n/g, '\n')
      .replace(/```([\w-]*)\n([\s\S]*?)```/g, (_, language, code) => {
        const highlighted = window.LesmarlHighlight ? window.LesmarlHighlight.render(code.trim(), language || 'code') : escapeHtml(code.trim());
        return `<pre><code class="language-${escapeHtml(language || 'text')}">${highlighted}</code></pre>`;
      })
      .replace(/^(#{1,6})\s+(.*)$/gm, (_, hashes, text) => `<h${hashes.length}>${renderInline(text)}</h${hashes.length}>`)
      .replace(/^(?:\*\s+|\-\s+|\+\s+)(.*)$/gm, '<li>$1</li>')
      .replace(/^(?:\d+\.\s+)(.*)$/gm, '<li>$1</li>')
      .replace(/^(>\s+.*)$/gm, '<blockquote>$1</blockquote>')
      .replace(/^(?:---|___|\*\*\*)$/gm, '<hr>')
      .replace(/\n{2,}/g, '</p><p>')
      .replace(/<p><li>/g, '<ul><li>')
      .replace(/<\/li><\/p>/g, '</li></ul>')
      .replace(/<p><h1>/g, '<h1>')
      .replace(/<\/h1><\/p>/g, '</h1>')
      .replace(/<p><h2>/g, '<h2>')
      .replace(/<\/h2><\/p>/g, '</h2>')
      .replace(/<p><h3>/g, '<h3>')
      .replace(/<\/h3><\/p>/g, '</h3>')
      .replace(/<p><blockquote>/g, '<blockquote>')
      .replace(/<\/blockquote><\/p>/g, '</blockquote>')
      .replace(/\n/g, '<br>');

    html = html.replace(/<br><h/g, '<h');
    return `<p>${html}</p>`;
  }

  return { render, escapeHtml };
})();
