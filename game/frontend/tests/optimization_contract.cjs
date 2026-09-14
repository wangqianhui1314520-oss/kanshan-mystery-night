const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const path = require('path');
const root = path.resolve(__dirname, '..');
const ctx = { console, URLSearchParams, setTimeout:()=>0, clearTimeout(){}, setInterval:()=>0, clearInterval(){},
 localStorage:{getItem:()=>null,setItem(){},removeItem(){}}, sessionStorage:{getItem:()=>null,setItem(){}},
 location:{search:'',hash:'',origin:'http://localhost',pathname:'/'}, navigator:{},
 document:{createElement:()=>({set innerHTML(v){this.textContent=v.replace(/&gt;/g,'>').replace(/&lt;/g,'<').replace(/&amp;/g,'&');}}),addEventListener(){},documentElement:{style:{setProperty(){}}}}, addEventListener(){} };
ctx.window=ctx; vm.createContext(ctx);
for(const file of ['js/vendor/vue.global.prod.js','js/data.js','js/pollution_data.js','js/store.js'])
 vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),ctx,{filename:file});
ctx.Net={on(){}}; ctx.VIEWS={};
for(const file of ['js/views/hotfeed.js','js/views/map.js'])
 vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),ctx,{filename:file});
const S=ctx.Store.state; S.playerId='player:test'; S.act=3; S.stage='investigate';
const metrics={exposure:72,credibility:55,emotion:66};
ctx.Store.applyEvent({type:'hotfeed_refresh',payload:{heat:65,signals:metrics,panel:[{id:'test',title:'服务端帖子',heat_delta:8,topic_tag:'科技',round:1,_refuted:false}]}});
const view=ctx.VIEWS.hotfeed.setup();
assert.equal(view.pagePosts.value[0].title,'服务端帖子');
assert.equal(view.pagePosts.value[0].delta,8);
assert.equal(view.signalRows.value[0].value,72);
assert.equal(S.heat,65);
S.refuted.test={ok:false}; assert.equal(view.refuted(view.pagePosts.value[0]),false);
ctx.Store.applyEvent({type:'hotfeed_refresh',payload:{panel:[]}});
assert.equal(view.pagePosts.value.length,0);
const map=ctx.VIEWS.map.setup(); map.open(ctx.MOCK.locations[0]);
ctx.Store.applyEvent({type:'search_result',actor:'player:test',payload:{hit:false,location:ctx.MOCK.locations[0].name,source:'engine',ambient:'环境痕迹',hint:{keywords:['访客']}}});
(async()=>{
 await ctx.Vue.nextTick();
 assert.equal(map.searchHint.value.keywords[0],'访客');
 map.lastGain.value={text:'后来发来的环境线索'};
 assert.equal(map.searchHint.value.keywords[0],'访客');
 for(const name of ['hotfeed','map']) { const render=ctx.Vue.compile(ctx.VIEWS[name].template, {decodeEntities: s => s.replace(/&gt;/g,'>').replace(/&lt;/g,'<').replace(/&amp;/g,'&')}); assert.equal(typeof render,'function'); }
 console.log('PASS: Vue store -> panel/metrics; empty panel; failed refute; persistent search hint; templates compile');
})().catch(e=>{console.error(e);process.exitCode=1;});
