#!/usr/bin/env node
/* api.js 回归：Windows localhost loopback、端口、远程 origin、file://。 */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'js', 'api.js'), 'utf8');

function makeContext(location) {
  const calls = [];
  const context = {
    URL,
    console,
    location,
    fetch: (url, options) => {
      calls.push({ url, options });
      return Promise.resolve({ ok: true });
    },
  };
  context.window = context;
  context.globalThis = context;
  vm.createContext(context);
  vm.runInContext(source, context, { filename: 'api.js' });
  return { context, calls };
}

const local = makeContext({
  protocol: 'http:', hostname: 'localhost', port: '8899',
  origin: 'http://localhost:8899', href: 'http://localhost:8899/'
});
assert.equal(local.context.Api.origin(), 'http://127.0.0.1:8899');
assert.equal(local.context.Api.wsOrigin(), 'ws://127.0.0.1:8899');
assert.equal(local.context.Api.rewrite('/api/studio/catalog'), 'http://127.0.0.1:8899/api/studio/catalog');
assert.equal(
  local.context.Api.rewrite('http://localhost:8899/api/session'),
  'http://127.0.0.1:8899/api/session'
);
assert.equal(
  local.context.Api.rewrite('ws://localhost:8899/ws/session?player_id=p1'),
  'ws://127.0.0.1:8899/ws/session?player_id=p1'
);
local.context.fetch('/api/health', { method: 'GET' });
assert.equal(local.calls[0].url, 'http://127.0.0.1:8899/api/health');

const remote = makeContext({
  protocol: 'https:', hostname: 'demo.example.com', port: '',
  origin: 'https://demo.example.com', href: 'https://demo.example.com/'
});
assert.equal(remote.context.Api.origin(), 'https://demo.example.com');
assert.equal(remote.context.Api.rewrite('/api/health'), 'https://demo.example.com/api/health');
assert.equal(
  remote.context.Api.rewrite('https://demo.example.com/api/session'),
  'https://demo.example.com/api/session'
);
assert.equal(
  remote.context.Api.rewrite('http://localhost:8899/api/session'),
  'http://localhost:8899/api/session',
  '远程页面不得把绝对 localhost 误改写为远端浏览器的 127.0.0.1'
);

const file = makeContext({
  protocol: 'file:', hostname: '', port: '', origin: 'null', href: 'file:///game/frontend/index.html'
});
assert.equal(file.context.Api.origin(), '');
assert.equal(file.context.Api.rewrite('/api/health'), '/api/health');
assert.equal(file.context.Api.rewrite('http://localhost:8899/api/health'), 'http://localhost:8899/api/health');

console.log('PASS api routing: localhost loopback, port preservation, remote origin and file mode');
