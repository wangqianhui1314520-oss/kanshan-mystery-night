/* ============================================================
 * api.js - same-origin API routing with Windows loopback protection
 *
 * Browser requests made from http://localhost are rewritten to
 * http://127.0.0.1:<same-port>. Remote HTTPS/HTTP deployments keep
 * their original origin. file:// keeps relative URLs for local mock mode.
 * ============================================================ */
(function () {
  'use strict';

  const root = window;
  const nativeFetch = typeof root.fetch === 'function' ? root.fetch.bind(root) : null;

  function isHttpProtocol(protocol) {
    return protocol === 'http:' || protocol === 'https:';
  }

  function origin() {
    const loc = root.location || {};
    if (!isHttpProtocol(loc.protocol)) return '';
    const host = String(loc.hostname || '').toLowerCase();
    if (host === 'localhost') {
      return loc.protocol + '//127.0.0.1' + (loc.port ? ':' + loc.port : '');
    }
    return String(loc.origin || '').replace(/\/$/, '');
  }

  function isLoopbackPage() {
    const loc = root.location || {};
    const host = String(loc.hostname || '').toLowerCase();
    return host === 'localhost' || host === '127.0.0.1';
  }

  function rewrite(input) {
    const base = origin();
    if (!base) return input;
    if (typeof input !== 'string') return input;
    if (input.charAt(0) === '/') return base + input;
    if (!/^(?:https?|wss?):\/\//i.test(input)) return input;
    try {
      const parsed = new URL(input);
      if (isLoopbackPage() && String(parsed.hostname || '').toLowerCase() === 'localhost') {
        parsed.hostname = '127.0.0.1';
      }
      return parsed.toString();
    } catch (e) {
      return input;
    }
  }

  function wsOrigin() {
    return origin().replace(/^http/, 'ws');
  }

  function apiFetch(input, options) {
    if (!nativeFetch) return Promise.reject(new Error('当前环境不支持网络请求'));
    return nativeFetch(rewrite(input), options);
  }

  root.Api = {
    origin: origin,
    wsOrigin: wsOrigin,
    rewrite: rewrite,
    fetch: apiFetch
  };

  /* Existing modules use native-looking fetch(). Wrap it once so every
     relative API call receives the same localhost handling. */
  if (nativeFetch && !root.__KanshanApiFetchWrapped) {
    root.fetch = apiFetch;
    root.__KanshanApiFetchWrapped = true;
  }
})();
