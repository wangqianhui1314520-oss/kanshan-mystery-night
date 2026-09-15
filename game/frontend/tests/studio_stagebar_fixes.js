// Regression guard (2026-09-15): stepIndex export, stagebar locked-state buttons, assemble recompile visibility.
// Reuses the headless Vue renderer harness from studio_runtime.js.
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const assert = require('assert/strict');
const root = path.resolve(__dirname, '..');
const storage = new Map();
const listeners = new Map();
function decodeElement() {
  const el = { children: [], textContent: '', _html: '' };
  el.getAttribute = key => key === 'foo' ? el._decoded : null;
  Object.defineProperty(el, 'innerHTML', {
    get() { return el._html; },
    set(value) {
      el._html = String(value);
      const match = el._html.match(/^<div foo="([\s\S]*)">(?:<\/div>)?$/);
      if (match) {
        el._decoded = match[1]
          .replace(/&quot;/g, '"').replace(/&amp;/g, '&')
          .replace(/&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>');
        el.children = [el];
      } else {
        el.children = [];
        el.textContent = el._html
          .replace(/&amp;/g, '&').replace(/&lt;/g, '<')
          .replace(/&gt;/g, '>').replace(/&quot;/g, '"')
          .replace(/&#39;/g, "'").replace(/&nbsp;/g, ' ');
      }
    }
  });
  return el;
}
const documentShim = { activeElement: null, createElement: decodeElement };
const s = { console, setTimeout, clearTimeout, Date, JSON, Promise,
  localStorage: { getItem: k => storage.get(k) || null, setItem: (k,v) => storage.set(k,v), removeItem: k => storage.delete(k) },
  fetch: async () => ({ ok: true, json: async () => ({ ok: true, items: [] }) }),
  addEventListener: (k,v) => listeners.set(k,v), removeEventListener: k => listeners.delete(k),
  document: documentShim,
};
s.window = s; s.globalThis = s;
vm.createContext(s);
function load(f) { vm.runInContext(fs.readFileSync(path.join(root,f),'utf8'),s,{filename:f}); }
load('js/vendor/vue.global.prod.js');
load('js/studio/catalog.js'); load('js/studio/brief.js');
s.Labels = new Proxy({}, { get: () => v => String(v || '') });
s.Store = { state: s.Vue.reactive({ studioJob:null, studioId:'' }), toast:()=>{} };
load('js/views/studio.js');
s.document = documentShim;
function node(type, text='') { return {type,text,children:[],parent:null,props:{},tagName:String(type).toUpperCase(),style:{},addEventListener(){},removeEventListener(){}}; }
const renderer = s.Vue.createRenderer({
  createElement: node, createText:t=>node('text',t), createComment:t=>node('comment',t),
  setText:(n,t)=>n.text=t, setElementText:(n,t)=>{n.text=t;n.children=[];},
  parentNode:n=>n.parent, nextSibling:n=>n.parent?.children[n.parent.children.indexOf(n)+1] || null,
  insert:(n,p,anchor)=>{ if(n.parent){const i=n.parent.children.indexOf(n);if(i>=0)n.parent.children.splice(i,1);} n.parent=p;const i=p.children.indexOf(anchor);if(i<0)p.children.push(n);else p.children.splice(i,0,n); },
  remove:n=>{if(n.parent){const i=n.parent.children.indexOf(n);if(i>=0)n.parent.children.splice(i,1);}},
  patchProp:(n,k,o,v)=>{n.props[k]=v;}, setScopeId:()=>{}, insertStaticContent:()=>{throw Error('unexpected static content');}
});
const host=node('root');
const app=renderer.createApp(s.VIEWS.studio);
const errors=[];
app.config.errorHandler=e=>{errors.push(e);};
const component=app.mount(host);
const text=n=>n.type==='comment'?'':String(n.text || '')+n.children.map(text).join('');
function findButtons(n, out=[]) {
  if (n.tagName === 'BUTTON') out.push(n);
  n.children.forEach(c => findButtons(c, out));
  return out;
}
const btnByText = (re) => findButtons(host).find(b => re.test(text(b)));
async function run(){
  await s.Vue.nextTick();

  // 1) stepIndex exposed: rail counter must render "1 / 7", never "NaN / 7"
  assert.match(text(host), /1 \/ 7/, 'rail counter should render step 1 of 7');
  assert.ok(!text(host).includes('NaN'), 'rail counter must not render NaN (stepIndex must be returned from setup)');

  // 2) locked stage buttons: both gen and lock disabled once stage locked
  component.draft.draft_id = 'd1';
  component.draft.world = { title: '真相稿', logline: '', surface_truth: '', inner_truth: '', truth_nodes: [] };
  component.locks.truth = true;
  component.step = 's2'; await s.Vue.nextTick();
  const genBtn = btnByText(/已锁定（解锁后可改写）|重写真相草案|AI 写真相草案/);
  assert.ok(genBtn, 's2 gen button rendered');
  assert.equal(genBtn.props.disabled, true, 'locked truth stage must disable rewrite button (server would 409)');
  const lockBtn = btnByText(/已锁定|锁定真相/);
  assert.ok(lockBtn, 's2 lock button rendered');
  assert.equal(lockBtn.props.disabled, true, 'locked truth stage must disable lock button');
  // unlock restores usability
  component.locks.truth = false; await s.Vue.nextTick();
  const genBtn2 = btnByText(/重写真相草案|AI 写真相草案/);
  assert.ok(genBtn2, 'unlocked gen button rendered');
  assert.notEqual(genBtn2.props.disabled, true, 'unlocked stage must re-enable rewrite button');

  // 3) assemble recompile: with a compiled job AND a server draft, the button must survive (old bug: v-if="!job" removed it forever)
  s.Store.state.studioJob = { status: 'ready', gate: { ok: true, errors: [], warnings: [] }, world: { title: '编译本', locations: [] }, detail: { clues: [], truth_nodes: [], characters: [], culprit: {} }, acts: [] };
  component.step = 's6'; await s.Vue.nextTick();
  assert.match(text(host), /重新编译过闸/, 'recompile button must stay visible after a successful assemble');
  const asmBtn = btnByText(/重新编译过闸|编译过闸/);
  assert.ok(asmBtn, 'assemble button present');
  assert.notEqual(asmBtn.props.disabled, true, 'recompile must be clickable when draft exists');

  // 4) job loaded from history (no server draft id): recompile stays hidden to avoid 404
  component.draft.draft_id = ''; await s.Vue.nextTick();
  assert.ok(!btnByText(/重新编译过闸|编译过闸（三段终稿/), 'history-loaded job without draft id must hide recompile button (no draft to assemble)');
  assert.ok(!/重新编译过闸/.test(text(host)), 'recompile label must disappear from output');

  assert.equal(errors.length, 0, errors.map(e=>e.stack).join('\n'));
  app.unmount();
  console.log('PASS studio stagebar fixes: stepIndex counter, locked-button disabling, assemble recompile visibility');
}
run().catch(e=>{console.error(e);process.exitCode=1;});
