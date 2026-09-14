// Vue renderer test: mounts the workbench without a browser or a live game session.
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const assert = require('assert/strict');
const root = path.resolve(__dirname, '..');
const storage = new Map();
const listeners = new Map();
const s = { console, setTimeout, clearTimeout, Date, JSON, Promise,
  localStorage: { getItem: k => storage.get(k) || null, setItem: (k,v) => storage.set(k,v), removeItem: k => storage.delete(k) },
  fetch: async () => ({ ok: true, json: async () => ({ ok: true, items: [] }) }),
  addEventListener: (k,v) => listeners.set(k,v), removeEventListener: k => listeners.delete(k),
};
s.window = s; s.globalThis = s;
vm.createContext(s);
function load(f) { vm.runInContext(fs.readFileSync(path.join(root,f),'utf8'),s,{filename:f}); }
load('js/vendor/vue.global.prod.js');
load('js/studio/catalog.js'); load('js/studio/brief.js');
s.Labels = new Proxy({}, { get: () => v => String(v || '') });
s.Store = { state: s.Vue.reactive({ studioJob:null, studioId:'' }), toast:()=>{} };
load('js/views/studio.js');
s.document = { activeElement: null };
// Host nodes allow real component setup, computed state, template rendering and lifecycle.
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
async function run(){
  await s.Vue.nextTick();
  assert.match(text(host),/开发工作台/);
  assert.match(text(host),/工作台概览/);
  assert.match(text(host),/草稿版本/);
  assert.equal(component.checks.ok,true,'one-line generation does not require extra fields');
  component.step='lock'; component.next(); assert.equal(component.step,'cast','skip collapsed camp step');
  component.showAdvanced=true; await s.Vue.nextTick(); component.step='camp'; component.showAdvanced=false;
  await s.Vue.nextTick(); assert.equal(component.step,'hook');
  component.brief.hook='第一稿'; component.brief.truth.crime=''; component.brief.camp.public=false;
  component.brief.minis=[]; component.saveDraft(true);
  const first=component.snapshots[0];
  for(let i=0;i<12;i++)component.brief.hook='输入'+i;
  assert.equal(component.snapshots.length,1,'typing must not evict named checkpoints');
  component.brief.truth.crime='后来填写'; component.brief.camp.public=true;
  component.restoreSnapshot(first);
  assert.equal(component.brief.truth.crime,''); assert.equal(component.brief.camp.public,false);
  assert.equal(component.brief.minis.length,0); assert.equal(component.brief.hook,'第一稿');
  assert.equal(component.snapshots.length,2,'restore preserves current work');
  component.showVersions=true; await s.Vue.nextTick(); assert.match(text(host),/创作简报版本/);
  s.Store.state.studioJob={status:'ready',gate:{ok:true},world:{title:'测试剧本',locations:[]},detail:{clues:[],truth_nodes:[],characters:[],culprit:{name:'秘密主谋'}},acts:[]};
  component.step='play'; await s.Vue.nextTick();
  for(const label of ['海报','角色','证据','导演视角'])assert.match(text(host),new RegExp(label));
  assert.ok(!text(host).includes('秘密主谋'),'poster keeps director secrets hidden');
  component.resultTab='director'; await s.Vue.nextTick();assert.match(text(host),/秘密主谋/);
  component.clearDraft(); await s.Vue.nextTick(); assert.equal(component.snapshots.length,0);
  assert.equal(storage.size,0,'clear must not immediately resave');
  const original=s.localStorage.setItem;
  s.localStorage.setItem=()=>{throw Error('quota');};component.saveDraft(true);
  assert.match(component.saveError,/保存失败/);s.localStorage.setItem=original;
  app.unmount(); assert.equal(listeners.has('keydown'),false);
  assert.equal(errors.length,0,errors.map(e=>e.stack).join('\n'));
  console.log('PASS studio mounted rendering, navigation, version retention, exact restore, clear, storage errors, result tabs and cleanup');
}
run().catch(e=>{console.error(e);process.exitCode=1;});
