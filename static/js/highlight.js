/* Lesmarl AI - Made by Mashrur Ahmed Arib - MIT License. See LICENSE. */
window.LesmarlHighlight = (() => {
  const simpleLanguages = {
    js: 'javascript',
    javascript: 'javascript',
    py: 'python',
    python: 'python',
    html: 'html',
    css: 'css',
    json: 'json',
    bash: 'bash',
    shell: 'bash',
    sql: 'sql'
  };

  function escape(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function render(code, language) {
    const normalized = (simpleLanguages[language] || language || 'text').toLowerCase();
    return escape(code).replace(/(\b(?:const|let|var|function|return|if|else|for|while|class|import|from|export|await|async)\b)/g, '<span style="color:#7dd3fc;">$1</span>')
      .replace(/(\b(?:true|false|null|undefined)\b)/g, '<span style="color:#c4b5fd;">$1</span>')
      .replace(/(".*?"|'(?:\\.|[^'])*'|`(?:\\.|[^`])*`)/g, '<span style="color:#86efac;">$1</span>')
      .replace(/(\b\d+\b)/g, '<span style="color:#fbbf24;">$1</span>');
  }

  return { render };
})();
