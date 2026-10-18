/* STREET KINGS live-update adapter. Requires an explicitly configured URL. */
(function (window) {
  'use strict';
  if (window.StreetKingsLive && window.StreetKingsLive.version === '1.0.0') return;
  let timer = null;
  let controller = null;
  let active = false;
  let lastData = null;
  let config = { url: null, intervalMs: 10000, credentials: 'same-origin' };
  function emit(type, detail) { window.dispatchEvent(new CustomEvent('streetkings:' + type, { detail: detail || {} })); }
  function configure(settings) {
    settings = settings || {};
    if (active) throw new Error('Stop live updates before reconfiguring');
    if (settings.url !== undefined && settings.url !== null && typeof settings.url !== 'string') throw new TypeError('url must be a string');
    if (settings.url !== undefined) config.url = settings.url;
    if (settings.intervalMs !== undefined) {
      if (!Number.isFinite(settings.intervalMs) || settings.intervalMs < 1000) throw new RangeError('intervalMs must be at least 1000');
      config.intervalMs = settings.intervalMs;
    }
    if (settings.credentials !== undefined) {
      if (!['omit', 'same-origin', 'include'].includes(settings.credentials)) throw new Error('Invalid credentials setting');
      config.credentials = settings.credentials;
    }
  }
  async function refresh() {
    if (!config.url) { emit('live:unconfigured', {}); return null; }
    if (controller) return null;
    controller = new AbortController();
    const ownController = controller;
    try {
      const response = await window.fetch(config.url, { method: 'GET', credentials: config.credentials, cache: 'no-store', signal: ownController.signal, headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error('Live endpoint returned HTTP ' + response.status);
      const data = await response.json();
      lastData = data;
      emit('live:update', { data: data });
      return data;
    } catch (error) {
      if (error.name !== 'AbortError') emit('live:error', { message: error.message });
      return null;
    } finally { if (controller === ownController) controller = null; }
  }
  function stop() { active = false; if (timer) { window.clearInterval(timer); timer = null; } if (controller) controller.abort(); emit('live:stopped', {}); }
  function start() { if (active) return; if (!config.url) { emit('live:unconfigured', {}); return; } active = true; refresh(); timer = window.setInterval(refresh, config.intervalMs); emit('live:started', {}); }
  window.StreetKingsLive = Object.freeze({ version: '1.0.0', configure: configure, start: start, stop: stop, refresh: refresh, getLastData: function () { return lastData; }, isActive: function () { return active; } });
  window.addEventListener('pagehide', stop);
})(window);
