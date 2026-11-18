'use strict';
(() => {
  const waiting = new Map();
  let sequence = 0;
  const bridge = window.StorageLensNative;
  if (bridge) bridge.onmessage = event => {
    try {
      const message = JSON.parse(event.data);
      const entry = waiting.get(message.id);
      if (!entry) return;
      clearTimeout(entry.timeout); waiting.delete(message.id);
      if (message.ok) entry.resolve(message.data);
      else entry.reject(new Error(message.error || 'failed'));
    } catch (error) { console.error('Invalid native response', error.name); }
  };
  window.device = (method, args = {}) => new Promise((resolve, reject) => {
    if (!bridge) { reject(new Error('notReady')); return; }
    if (waiting.size >= 8) { reject(new Error('busy')); return; }
    const id = `request-${++sequence}`;
    const timeout = setTimeout(() => { waiting.delete(id); reject(new Error('failed')); }, 60000);
    waiting.set(id, { resolve, reject, timeout });
    bridge.postMessage(JSON.stringify({ id, method, args }));
  });
  window.addEventListener('pagehide', () => {
    for (const entry of waiting.values()) { clearTimeout(entry.timeout); entry.reject(new Error('failed')); }
    waiting.clear();
  });
  window.loadCopy = async () => {
    let model = window.STORAGELENS_CONTENT;
    try {
      const response = await fetch('public/storagelens.model.json');
      if (response.ok) model = await response.json();
    } catch { /* The generated bundled copy remains available offline. */ }
    if (!model || model.schemaVersion !== 1 || !model.locales[model.defaultLocale]) throw new Error('invalid');
    const locale = Object.keys(model.locales).find(l => navigator.language.toLowerCase().startsWith(l)) || model.defaultLocale;
    const base = model.locales[model.defaultLocale];
    document.documentElement.lang = locale;
    return (key, values = {}) => {
      const value = model.locales[locale][key] || base[key] || base['errors.failed'];
      return value.replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ''));
    };
  };
})();
