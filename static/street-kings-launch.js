/* STREET KINGS launch adapter. No backend assumptions. */
(function (window, document) {
  'use strict';
  if (window.StreetKingsLaunch && window.StreetKingsLaunch.version === '1.0.0') return;
  const listeners = new Set();
  let started = false;
  const state = { ready: false, error: null };
  function emit(type, detail) {
    window.dispatchEvent(new CustomEvent('streetkings:' + type, { detail: detail || {} }));
    listeners.forEach(function (fn) { try { fn(type, detail || {}); } catch (err) { console.error(err); } });
  }
  function start() {
    if (started) return;
    started = true;
    state.ready = true;
    emit('launch:ready', { path: window.location.pathname });
  }
  function on(callback) { if (typeof callback !== 'function') throw new TypeError('callback must be a function'); listeners.add(callback); return function () { listeners.delete(callback); }; }
  window.StreetKingsLaunch = Object.freeze({ version: '1.0.0', start: start, on: on, getState: function () { return Object.assign({}, state); } });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})(window, document);
