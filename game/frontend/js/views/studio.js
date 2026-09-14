/* ============================================================
 * views/studio.js —— 导演台 Vue 视图
 * 目录与简报在 js/studio/catalog.js、js/studio/brief.js
 * ============================================================ */
(function () {
  const { ref, computed, reactive, onMounted, onBeforeUnmount, watch } = Vue;
  const C = window.STUDIO || {};
  const {
    PRESETS, STEPS, PACK_TYPES, MOODS, CORE_MECHS, MECHS, MINIS, ACT_META, CAST_AVATAR,
    emptyBrief, hydrateFromJob
  } = C;

  const StudioView = {
    setup() {
      const S = window.Store.state;
      const step = ref('hook');
      const useLlm = ref(false);
      const generating = ref(false);
      const history = ref([]);
      const draftSavedAt = ref('');
      const snapshots = ref([]);
      const showVersions = ref(false);
      const saveError = ref('');
      const showAdvanced = ref(false);
      const resultTab = ref('poster');
      const brief = reactive(emptyBrief(PRESETS[0]));
      const DRAFT_KEY = 'kanshan_studio_draft_v2';
      let restoring = false;

      const job = computed(() => S.studioJob);
      const world = computed(() => (job.value && job.value.world) || {});
      const gate = computed(() => (job.value && job.value.gate) || { ok: false, errors: [], warnings: [] });
      const acts = computed(() => C.normActs(job.value));
      const clues = computed(() => ((job.value && job.value.detail && job.value.detail.clues) || []));
      const nodes = computed(() => ((job.value && job.value.detail && job.value.detail.truth_nodes) || []));
      const culprit = computed(() => ((job.value && job.value.detail && job.value.detail.culprit) || {}));
      const people = computed(() => ((job.value && job.value.detail && job.value.detail.characters) || []));
      const bookCovers = computed(() => {
        const d = job.value && job.value.detail;
        const fromDetail = d && Array.isArray(d.player_books) ? d.player_books : null;
        const fromJob = job.value && Array.isArray(job.value.player_books) ? job.value.player_books : null;
        const raw = (fromDetail && fromDetail.length) ? fromDetail
          : (fromJob && fromJob.length) ? fromJob : null;
        if (raw && raw.length) {
          return raw.map(b => ({
            id: b.char_id || b.id || '',
            name: b.name || '',
            you_are: b.you_are || ''
          }));
        }
        return (people.value || []).map(c => {
          const pub = (c.public && typeof c.public === 'object') ? c.public : {};
          return {
            id: c.id,
            name: c.name || '',
            you_are: pub.bio || c.public_bio || c.archetype || ''
          };
        });
      });
      const canPlay = computed(() => !!(gate.value.ok && job.value && job.value.status === 'ready'));
      const checks = computed(() => {
        const errors = [];
        if (!brief.hook.trim()) errors.push('还没有一句话钩子');
        if (!brief.pack_type) errors.push('请选择本型');
        return { ok: errors.length === 0, errors };
      });
      const health = computed(() => {
        const locs = (world.value.locations || []).length;
        const clueCount = clues.value.length;
        const nodeCount = nodes.value.length;
        const actsCount = acts.value.length;
        const scores = [
          { key: '结构', value: actsCount >= 3 ? 100 : Math.round(actsCount / 3 * 100), hint: actsCount + '/3 幕' },
          { key: '场景', value: locs >= 6 ? 100 : Math.round(locs / 6 * 100), hint: locs + '/6 地点' },
          { key: '证据', value: clueCount >= 12 ? 100 : Math.round(clueCount / 12 * 100), hint: clueCount + '/12 线索' },
          { key: '真相', value: nodeCount >= 6 ? 100 : Math.round(nodeCount / 6 * 100), hint: nodeCount + '/6 节点' }
        ];
        return scores;
      });
      const current = computed(() => STEPS.find(s => s.id === step.value) || STEPS[0]);
      const visibleSteps = computed(() => STEPS.filter(s => showAdvanced.value || ['hook','type','lock','cast','truth','gate','play'].includes(s.id)));
      const stepIndex = computed(() => visibleSteps.value.findIndex(s => s.id === step.value));
      watch(showAdvanced, () => { if (!visibleSteps.value.some(s => s.id === step.value)) step.value = 'hook'; });
      const typeName = computed(() => {
        const t = PACK_TYPES.find(x => x.id === brief.pack_type);
        return t ? t.name : ((window.Labels && window.Labels.plain(brief.pack_type, '未选本型')) || '未选本型');
      });

      const filled = computed(() => ({
        hook: !!brief.hook.trim(),
        type: !!brief.pack_type,
        lock: !!(brief.lock.timebox || brief.lock.space || brief.lock.lock_rule || brief.lock.win || brief.lock.theme),
        camp: !!(brief.camp.win_pollution || brief.camp.win_truth || brief.camp.public),
        cast: brief.cast.some(c => c.name || c.archetype),
        truth: !!(brief.truth.surface || brief.truth.crime),
        board: !!brief.board_notes.trim(),
        mech: true,
        minis: brief.minis.length > 0,
        acts: brief.acts.some(a => a.name || a.brief),
        vibe: !!(brief.vibe.dm || brief.vibe.horror_beats || brief.vibe.mood === 'horror'),
        gate: !!(job.value && gate.value.ok),
        play: canPlay.value
      }));

      const markOf = (id) => {
        if (id === 'gate') return gate.value.ok ? 'ready' : (job.value ? 'bad' : (filled.value[id] ? 'edit' : ''));
        if (id === 'play') return canPlay.value ? 'ready' : '';
        if (job.value && (id !== 'hook' || filled.value.hook)) return 'gen';
        return filled.value[id] ? 'edit' : '';
      };

      const pickPreset = (text) => { brief.hook = text; };

      const pickType = (id) => {
        const t = PACK_TYPES.find(x => x.id === id);
        if (!t) return;
        brief.pack_type = t.id;
        Object.keys(t.modules).forEach(k => { brief.modules[k] = t.modules[k]; });
        brief.minis.splice(0, brief.minis.length);
        (t.minis || []).forEach(m => brief.minis.push(m));
        brief.vibe.mood = t.mood;
        brief.camp.public = !!t.public_camps;
        brief.lock.tone = t.tone;
        if (t.id === 'horror' && !brief.vibe.dm) brief.vibe.dm = '灯灭之后只报事实，不解释空档。';
        if (t.id === 'faction' && !brief.camp.win_pollution) {
          brief.camp.win_pollution = '热度淹死真线索，或栽赃成功';
          brief.camp.win_truth = '用证据卡指认真凶';
        }
      };

      const seatOf = (cid) => {
        const c = brief.camp;
        if (cid === 'char_01') return (c.pollution || '污染') + '位 · 真凶气质';
        if (cid === 'char_02') return (c.swayable || '可策反') + '位';
        return (c.truth || '求真') + '位';
      };

      async function loadHistory() {
        try {
          const r = await fetch('/api/studio');
          if (!r.ok) return;
          const j = await r.json();
          if (j.ok && j.items) history.value = j.items.slice(0, 8);
        } catch (e) { /* 无后端静默 */ }
      }

      function replaceBrief(src) {
        const fresh = emptyBrief('');
        Object.keys(fresh).forEach(k => {
          if (!(k in src)) return;
          fresh[k] = src[k] && typeof src[k] === 'object' && !Array.isArray(src[k])
            ? Object.assign({}, fresh[k], src[k]) : src[k];
        });
        restoring = true;
        try { Object.assign(brief, JSON.parse(JSON.stringify(fresh))); }
        finally { restoring = false; }
      }
      function saveDraft(checkpoint = false) {
        try {
          const now = new Date().toISOString();
          const copy = JSON.parse(JSON.stringify(brief));
          const list = snapshots.value.slice();
          if (checkpoint && (!list[0] || JSON.stringify(list[0].brief) !== JSON.stringify(copy))) list.unshift({ brief: copy, savedAt: now });
          const kept = list.slice(0, 8);
          localStorage.setItem(DRAFT_KEY, JSON.stringify({ brief: copy, savedAt: now, snapshots: kept }));
          snapshots.value = kept;
          draftSavedAt.value = new Date(now).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
          saveError.value = '';
        } catch (e) { saveError.value = '保存失败，请检查浏览器存储空间；当前编辑仍保留在页面中。'; }
      }

      function restoreDraft() {
        try {
          const raw = JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null');
          if (!raw || !raw.brief) return false;
          replaceBrief(raw.brief);
          snapshots.value = Array.isArray(raw.snapshots) ? raw.snapshots : [];
          draftSavedAt.value = raw.savedAt ? new Date(raw.savedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
          return true;
        } catch (e) { return false; }
      }

      function clearDraft() {
        try { localStorage.removeItem(DRAFT_KEY); } catch (e) { saveError.value = '清除失败，浏览器存储不可用'; return; }
        snapshots.value = [];
        draftSavedAt.value = '';
        window.Store.toast('已清除本地草稿和版本；页面中的编辑仍保留', 'good');
      }
      function restoreSnapshot(item) {
        if (!item || !item.brief) return;
        saveDraft(true);
        replaceBrief(item.brief);
        saveDraft(false);
        window.Store.toast('已恢复简报，重新生成后更新可玩剧本', 'good');
      }

      async function generateAll() {
        const s = brief.hook.trim();
        if (!s) { window.Store.toast('先写一句钩子', 'warn'); step.value = 'hook'; return; }
        saveDraft(true);
        brief.voice.dm = brief.vibe.dm;
        brief.voice.comedy = brief.vibe.comedy;
        generating.value = true;
        try {
          const r = await fetch('/api/studio/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              seed: s,
              tier: 'demo',
              use_llm: useLlm.value,
              inner_boss: !!brief.modules.inner_boss,
              brief: JSON.parse(JSON.stringify(brief))
            })
          });
          if (!r.ok) {
            let msg = '生成失败';
            try { const err = await r.json(); msg = (window.Labels && window.Labels.apiErr(err.detail || err.message, msg)) || msg; } catch (e) { }
            window.Store.toast(msg, 'warn');
            if (!window.STUDIO_FALLBACK) window.Store.toast('请先启动本机服务后再试', 'warn');
            return;
          }
          const j = await r.json();
          if (j.ok && j.job) {
            S.studioJob = j.job;
            S.studioId = j.job.id;
            hydrateFromJob(brief, j.job);
            if (useLlm.value && j.job.provider === 'mock') {
              window.Store.toast('AI 通道没走通，已自动回退骨架稿（闸门照常校验）', 'warn');
            }
            window.Store.toast(j.notice || '新本已写成', (j.job.gate && j.job.gate.ok) ? 'good' : 'warn');
            step.value = (j.job.gate && j.job.gate.ok) ? 'play' : 'gate';
            loadHistory();
          } else {
            window.Store.toast('返回格式异常', 'warn');
          }
        } catch (e) {
          window.Store.toast('无法连接档案局服务——请先启动本机服务后再试', 'warn');
        } finally {
          generating.value = false;
        }
      }

      async function loadJob(id) {
        try {
          const r = await fetch('/api/studio/' + encodeURIComponent(id));
          if (!r.ok) { window.Store.toast('读取 job 失败', 'warn'); return; }
          const j = await r.json();
          if (j.ok && j.job) {
            S.studioJob = j.job;
            S.studioId = j.job.id;
            hydrateFromJob(brief, j.job);
            step.value = (j.job.gate && j.job.gate.ok) ? 'play' : 'gate';
          }
        } catch (e) { window.Store.toast('请先启动服务', 'warn'); }
      }

      const play = () => {
        const id = S.studioId || (job.value && job.value.id);
        if (!id) { window.Store.toast('请先走完生产线', 'warn'); return; }
        if (!canPlay.value) { window.Store.toast('闸门未通过，不可开玩', 'warn'); return; }
        window.Store.playStudio(id);
      };

      const playHistory = (h) => {
        if (!h || !h.id) return;
        if (!(h.ok && h.status === 'ready')) { window.Store.toast('这一本闸门未绿，先加载到工作台排查', 'warn'); return; }
        window.Store.playStudio(h.id);
      };

      const go = (id) => { step.value = id; };
      const next = () => { if (stepIndex.value < visibleSteps.value.length - 1) step.value = visibleSteps.value[stepIndex.value + 1].id; };
      const prev = () => { if (stepIndex.value > 0) step.value = visibleSteps.value[stepIndex.value - 1].id; };
      const avatarOf = (cid) => CAST_AVATAR[cid] || '/assets/images/bust/char_v587.png';
      const L = window.Labels;
      const tierLabel = (t) => ({ public: '公开', limited: '限知', hidden: '隐藏', fake: '伪证' }[t] || (L && L.tier(t)) || '公开');

      onMounted(loadHistory);
      onMounted(() => restoreDraft());
      watch(brief, () => { if (!restoring) saveDraft(false); }, { deep: true, flush: 'sync' });
      const saveShortcut = e => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); saveDraft(true); } };
      onMounted(() => window.addEventListener('keydown', saveShortcut));
      onBeforeUnmount(() => window.removeEventListener('keydown', saveShortcut));

      return {
        S, L, step, useLlm, generating, history, brief, job, world, gate, acts, clues, nodes, culprit, people, bookCovers,
        draftSavedAt, snapshots, showVersions, saveError, visibleSteps, showAdvanced, resultTab, checks, health,
        canPlay, current, typeName, STEPS, PRESETS, PACK_TYPES, MOODS, CORE_MECHS, MECHS, MINIS, ACT_META,
        pickPreset, pickType, seatOf, generateAll, loadJob, play, playHistory, go, next, prev, avatarOf, tierLabel, markOf, saveDraft, clearDraft, restoreSnapshot,
        Store: window.Store
      };
    },
    template: `
    <div class="studio-workbench">
      <header class="sw-hd">
        <span class="sw-tag">LINE · 一句话 → 一本新剧本杀</span>
        <h1>创一本 · 开发工作台</h1>
        <p class="sw-sub">钩子决定案情。人名、地名、12 条线索、记忆和热搜都会按构思重写；过闸后套进原来的圆桌和搜证。</p>
        <div class="sw-quickbar">
          <span class="sw-draft-state" :class="{saved: draftSavedAt}">{{ draftSavedAt ? '草稿已保存 ' + draftSavedAt : '草稿尚未保存' }}</span>
          <button type="button" class="sw-link" @click="saveDraft(true)">保存版本</button>
          <button type="button" class="sw-link" @click="clearDraft">清除草稿</button>
          <button type="button" class="sw-link" @click="showAdvanced = !showAdvanced">{{ showAdvanced ? '收起高级设置' : '展开高级设置' }}</button>
          <button type="button" class="sw-link" @click="showVersions = !showVersions">草稿版本（{{ snapshots.length }}）</button>
        </div>
        <div v-if="!checks.ok" class="sw-inline-checks">
          <b>生成前检查：</b><span v-for="e in checks.errors" :key="e">{{ e }}</span>
        </div>
      </header>

      <div class="sw-body">
        <aside class="sw-rail" aria-label="生产线">
          <ol>
            <li v-for="s in visibleSteps" :key="s.id">
              <button type="button" :class="['sw-step', markOf(s.id), { on: step === s.id }]" @click="go(s.id)">
                <em>{{ s.no }}</em>
                <span>{{ s.title }}</span>
              </button>
            </li>
          </ol>
        </aside>

        <section class="sw-stage">
          <p v-if="saveError" role="alert" class="sw-inline-checks">{{ saveError }}</p>
          <section v-if="showVersions" class="sw-out">
            <h3>创作简报版本</h3>
            <p>自动保存保留最新编辑；保存版本或生成前记录快照。恢复简报后，重新生成才会更新可玩剧本。</p>
            <p v-if="!snapshots.length">暂无快照，点击顶部「保存版本」记录当前构思。</p>
            <div class="sw-snapshots"><button v-for="(v,i) in snapshots" :key="i" @click="restoreSnapshot(v)">{{ v.brief.hook || '空白简报' }} · {{ new Date(v.savedAt).toLocaleTimeString() }} · 恢复</button></div>
          </section>
          <section class="sw-out sw-overview">
            <h3>工作台概览</h3>
            <p>{{ typeName }} · 4 人 / 6 地点 / 12 线索 · 三幕快本</p>
            <p v-if="!job">写一句钩子即可生成，其余设定可选填。生成后可在「开局」查看海报、角色、证据和导演视角。</p>
            <template v-else>
              <p>{{ world.title }} · {{ gate.ok ? '校验通过' : '需要修复' }}</p>
              <div class="sw-health"><div v-for="h in health" :key="h.key" class="sw-health-row"><b>{{ h.key }}</b><span class="sw-health-track"><i :style="{width: h.value + '%'}"></i></span><em>{{ h.hint }}</em></div></div>
              <p>以上为结构配额检查，不代表剧情质量。</p>
              <button class="sw-link" @click="go('play')">查看生成结果 →</button>
            </template>
          </section>
          <p class="sw-why"><b>{{ current.no }} {{ current.title }}</b>{{ current.why }}</p>

          <div v-if="step==='hook'" class="sw-pane">
            <label class="sw-lab">把人关进局里的那一句</label>
            <textarea v-model="brief.hook" rows="4" maxlength="200" placeholder="写一句梗概，或点下方预置…"></textarea>
            <div class="sw-presets">
              <button v-for="p in PRESETS" :key="p" type="button" class="sw-preset" @click="pickPreset(p)">{{ p }}</button>
            </div>
          </div>

          <div v-else-if="step==='type'" class="sw-pane">
            <div class="sw-picks">
              <button v-for="t in PACK_TYPES" :key="t.id" type="button" :class="['sw-pick', { on: brief.pack_type === t.id }]" @click="pickType(t.id)">
                <b>{{ t.name }}</b>
                <span>{{ t.blurb }}</span>
              </button>
            </div>
            <p class="sw-hint">选本型会改案情气质（恐怖本换灭灯令，情感本换未寄出的信），并预勾机制。快本体量仍是 4 人 / 6 地 / 12 证，内容会换。</p>
          </div>

          <div v-else-if="step==='lock'" class="sw-pane">
            <div class="sw-fields">
              <label>时间盒<input v-model="brief.lock.timebox" placeholder="例：案发夜 20:00–23:00，21:00 锁门"></label>
              <label>空间<input v-model="brief.lock.space" placeholder="例：24 小时热榜机房"></label>
              <label>出不去的规则<input v-model="brief.lock.lock_rule" placeholder="例：不出真相，不出此门"></label>
              <label>怎样算赢<input v-model="brief.lock.win" placeholder="例：用证据卡指认真凶"></label>
              <label>语气<input v-model="brief.lock.tone" placeholder="由本型预填，可改"></label>
              <label>主题<input v-model="brief.lock.theme" placeholder="例：热度不是真相"></label>
            </div>
            <aside class="sw-out" v-if="job">
              <h3>生成后的锁局</h3>
              <p>{{ world.hook }}</p>
              <ul><li v-for="r in (world.world_rules||[])" :key="r">{{ L.line(r) }}</li></ul>
            </aside>
          </div>

          <div v-else-if="step==='camp'" class="sw-pane">
            <div class="sw-fields">
              <label>污染阵营对外名<input v-model="brief.camp.pollution" placeholder="污染 / 热度 / 黑雾"></label>
              <label>可策反位对外名<input v-model="brief.camp.swayable" placeholder="可策反 / 夹心"></label>
              <label>求真阵营对外名<input v-model="brief.camp.truth" placeholder="求真 / 守灯"></label>
              <label>污染怎么赢<input v-model="brief.camp.win_pollution" placeholder="热度淹死真线索"></label>
              <label>求真怎么赢<input v-model="brief.camp.win_truth" placeholder="证据卡指认真凶"></label>
            </div>
            <label class="sw-llm"><input type="checkbox" v-model="brief.camp.public"><span>阵营本：对外公开阵营名（人设前加【阵营】；试玩包里只改称呼，不另写阵营字段）</span></label>
            <p class="sw-hint">不能改成 3 凶或无凶——闸门要求 1 污染 + ≥1 可策反。改的是称呼和公开与否。</p>
          </div>

          <div v-else-if="step==='cast'" class="sw-pane">
            <div class="sw-cast-grid">
              <article v-for="c in brief.cast" :key="c.id" class="sw-seat">
                <img :src="avatarOf(c.id)" :alt="c.name || seatOf(c.id)">
                <header><b>{{ seatOf(c.id) }}</b></header>
                <input v-model="c.name" :placeholder="'名字 · ' + seatOf(c.id)">
                <input v-model="c.archetype" placeholder="公开人设 / 职业钩子">
                <input v-model="c.comedy_hook" placeholder="一句腔调">
                <textarea v-model="c.public_bio" rows="2" placeholder="圆桌上别人能听到的自我介绍"></textarea>
              </article>
            </div>
          </div>

          <div v-else-if="step==='truth'" class="sw-pane">
            <div class="sw-fields">
              <label>表面故事<textarea v-model="brief.truth.surface" rows="2" placeholder="开局时全员以为发生了什么"></textarea></label>
              <label>罪行<input v-model="brief.truth.crime" placeholder="真凶做了什么"></label>
              <label>动机<input v-model="brief.truth.motive" placeholder="为什么做"></label>
              <label>手法<input v-model="brief.truth.method" placeholder="怎么做、谁被裹挟"></label>
            </div>
            <aside class="sw-out" v-if="job">
              <h3>真相树（作者可见）</h3>
              <p v-if="culprit.name">主谋槽：{{ culprit.name }} · {{ culprit.crime }}</p>
              <ol><li v-for="n in nodes" :key="n.id"><b>{{ n.name }}</b> {{ n.desc }}</li></ol>
            </aside>
          </div>

          <div v-else-if="step==='board'" class="sw-pane">
            <label class="sw-lab">现场气质、关键物、伪证点子</label>
            <textarea v-model="brief.board_notes" rows="3" placeholder="例：前台横幅锁门；机房缺七分钟；茶水间三分糖"></textarea>
            <aside class="sw-out" v-if="job">
              <h3>落点 · {{ (world.locations||[]).length }} 地 / {{ clues.length }} 证</h3>
              <div class="sw-chips"><span v-for="l in (world.locations||[])" :key="l.id" class="chip">{{ l.name }}</span></div>
              <ul class="sw-clues">
                <li v-for="c in clues" :key="c.id"><i :class="'t-'+c.tier">{{ tierLabel(c.tier) }}</i><b>{{ c.name }}</b><span>{{ L.place(c.location) }}</span></li>
              </ul>
            </aside>
          </div>

          <div v-else-if="step==='mech'" class="sw-pane">
            <p class="sw-lab">核心（引擎锁死）</p>
            <div class="sw-mods">
              <label v-for="m in CORE_MECHS" :key="m.key" class="sw-mod on lock">
                <input type="checkbox" checked disabled>
                <b>{{ m.name }}</b><em>{{ m.play }}</em><span>{{ m.hint }}</span>
              </label>
            </div>
            <p class="sw-lab">可插拔机制</p>
            <div class="sw-mods">
              <label v-for="m in MECHS" :key="m.key" :class="['sw-mod', { on: brief.modules[m.key] }]">
                <input type="checkbox" v-model="brief.modules[m.key]">
                <b>{{ m.name }}</b><em>{{ m.play }}</em><span>{{ m.hint }}</span>
              </label>
            </div>
          </div>

          <div v-else-if="step==='minis'" class="sw-pane">
            <div class="sw-mods">
              <label v-for="m in MINIS" :key="m.id" :class="['sw-mod', { on: brief.minis.includes(m.id) }]">
                <input type="checkbox" :value="m.id" v-model="brief.minis">
                <b>{{ m.name }}</b><em>{{ m.where }}</em><span>{{ m.hint }}</span>
              </label>
            </div>
            <p class="sw-hint">这四件已在看山壳里。勾上的，开局后「小游戏厅」只列出它们；全不勾则不出现入口。</p>
          </div>

          <div v-else-if="step==='acts'" class="sw-pane">
            <div class="sw-act-grid">
              <article v-for="a in brief.acts" :key="a.id" class="sw-act">
                <header>
                  <b>{{ ({act1:'第一幕',act2:'第二幕',act3:'第三幕'}[a.id] || '本幕') }} · {{ ACT_META[a.id].stage }}</b>
                  <span>{{ ACT_META[a.id].ap }} · {{ ACT_META[a.id].verbs }}</span>
                </header>
                <p class="sw-hint">{{ ACT_META[a.id].lock }}</p>
                <input v-model="a.name" placeholder="这一幕在海报上的名字">
                <textarea v-model="a.brief" rows="2" placeholder="这一幕玩家在干什么"></textarea>
                <input v-model="a.must_reveal" placeholder="必须先给到的信息">
                <input v-model="a.must_not_reveal" placeholder="这一幕绝对不能爆的">
                <input v-model="a.twist" placeholder="反转拍点">
                <input v-model="a.comedy" placeholder="笑点 / 恐怖拍 / 搜错彩蛋">
              </article>
            </div>
          </div>

          <div v-else-if="step==='vibe'" class="sw-pane">
            <div class="sw-picks">
              <button v-for="m in MOODS" :key="m.id" type="button" :class="['sw-pick', { on: brief.vibe.mood === m.id }]" @click="brief.vibe.mood = m.id">
                <b>{{ m.name }}</b><span>{{ m.hint }}</span>
              </button>
            </div>
            <div class="sw-fields" style="margin-top:12px">
              <label>恐怖 / 不安拍点<textarea v-model="brief.vibe.horror_beats" rows="2" placeholder="例：21:07 灯全灭七分钟；监控里多出一个没脸的人"></textarea></label>
              <label>DM 口吻<textarea v-model="brief.vibe.dm" rows="2" placeholder="欢乐：叮——只报事实。恐怖：灯灭之后只报事实。"></textarea></label>
              <label>喜剧 / 错位来源<input v-model="brief.vibe.comedy" placeholder="腔调错位，搜错彩蛋，一眼假热搜"></label>
            </div>
          </div>

          <div v-else-if="step==='gate'" class="sw-pane" :class="gate.ok ? 'gate-ok' : 'gate-bad'">
            <div class="sw-gate-status">
              <span class="sw-gate-dot"></span>
              <b>{{ job ? (gate.ok ? '闸门通过 · 可开玩' : '闸门未通过 · 停在创作台改') : '尚未编译' }}</b>
              <span class="dim tiny" v-if="job">{{ L.jobLine(job) }}</span>
            </div>
              <ul class="sw-gate-list ok" v-if="gate.ok"><li>这本新案情已过闸：4 人 / 6 地 / 12 条本局线索 / 破冰→搜证→指认</li></ul>
            <ul class="sw-gate-list bad" v-if="(gate.errors||[]).length"><li v-for="(e,i) in gate.errors" :key="'e'+i">{{ L.gateLine(e) }}</li></ul>
            <ul class="sw-gate-list warn" v-if="(gate.warnings||[]).length"><li v-for="(w,i) in gate.warnings" :key="'w'+i">{{ L.gateLine(w) }}</li></ul>
          </div>

          <div v-else-if="step==='play'" class="sw-pane">
            <template v-if="job">
              <div class="sw-result-tabs">
                <button :class="{on: resultTab==='poster'}" @click="resultTab='poster'">海报</button>
                <button :class="{on: resultTab==='cast'}" @click="resultTab='cast'">角色</button>
                <button :class="{on: resultTab==='evidence'}" @click="resultTab='evidence'">证据</button>
                <button :class="{on: resultTab==='director'}" @click="resultTab='director'">导演视角</button>
              </div>
              <template v-if="resultTab==='poster'">
              <h3 class="sw-title">{{ world.title || '未命名本' }}</h3>
              <p class="sw-logline">{{ typeName }} · {{ L.mood(brief.vibe.mood) }} · {{ world.logline }}</p>
              <ol class="sw-acts"><li v-for="a in acts" :key="a.id"><b>{{ a.name }}</b><span>{{ L.stage(a.stage) }}</span><p>{{ a.brief }}</p></li></ol>
              </template>
              <template v-if="resultTab==='cast'">
              <div class="sw-chips"><span class="chip" v-for="c in people" :key="'p'+c.id">{{ c.name }}</span></div>
              <div class="sw-dossier">
                <div class="sw-books" v-if="bookCovers.length">
                  <h4>角色故事本</h4>
                  <article class="sw-book-cover" v-for="b in bookCovers" :key="'bk'+b.id">
                    <b>{{ b.name }}</b>
                    <p>{{ b.you_are }}</p>
                  </article>
                </div>
              </div>
              </template>
              <template v-if="resultTab==='evidence'">
              <div class="sw-dossier"><h4>地点与线索</h4><div class="sw-chips">
                  <span class="chip" v-for="l in (world.locations||[])" :key="l.id">{{ l.name }}</span>
                </div>
                <ul class="sw-clues">
                  <li v-for="c in clues" :key="c.id"><i :class="'t-'+c.tier">{{ tierLabel(c.tier) }}</i><b>{{ c.name }}</b><span>{{ L.place(c.location) }}</span></li>
                </ul>
              </div>
              </template>
              <template v-if="resultTab==='director'">
              <div class="sw-dossier"><h4>剧本健康度</h4><div class="sw-health"><div v-for="h in health" :key="h.key" class="sw-health-row"><b>{{ h.key }}</b><span class="sw-health-track"><i :style="{width: h.value + '%'}"></i></span><em>{{ h.hint }}</em></div></div><h4>真相树（作者可见）</h4><p v-if="culprit.name"><b>主谋</b> {{ culprit.name }} · {{ culprit.crime }}</p><ol><li v-for="n in nodes" :key="n.id">{{ n.name }} · {{ n.desc }}</li></ol><h4 v-if="snapshots.length">历史版本</h4><div class="sw-snapshots"><button v-for="(v,i) in snapshots" :key="v.savedAt" @click="restoreSnapshot(v)">版本 {{ snapshots.length-i }} · {{ new Date(v.savedAt).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) }}</button></div></div>
              </template>
              <div class="sw-chips">
                <span class="chip" v-for="k in Object.keys(brief.modules).filter(k => brief.modules[k])" :key="k">{{ L.module(k) }}</span>
                <span class="chip" v-for="m in brief.minis" :key="'mi'+m">{{ L.mini(m) }}</span>
              </div>
              <button class="btn-start" :disabled="!canPlay" @click="play">开这本新本 ▸</button>
            </template>
            <p v-else class="sw-empty">还没有编译好的本。回到钩子，或直接走完全线。</p>
          </div>
        </section>
      </div>

      <footer class="sw-dock">
        <div class="sw-dock-nav">
          <button type="button" class="btn-skip" @click="prev" :disabled="step==='hook'">上一步</button>
          <button type="button" class="btn-skip" @click="next" :disabled="step==='play'">下一步</button>
        </div>
        <label class="sw-llm">
          <input type="checkbox" v-model="useLlm">
          <span>调用 AI 写中间稿（无 key 自动走骨架）</span>
        </label>
        <button class="btn-start sw-run" :disabled="generating" @click="generateAll">{{ generating ? '正在写这本新本…' : '生成这本新本' }}</button>
        <button type="button" class="btn-skip" @click="Store.closeStudio()">返回主菜单</button>
        <div class="sw-history" v-if="history.length">
          <span class="dim tiny">已出的本
            <button type="button" class="sw-link" @click="loadHistory">刷新</button>
          </span>
          <button v-for="h in history" :key="h.id" type="button" class="sw-hist-item" :title="h.id" @click="loadJob(h.id)">
            {{ h.title || '未命名本' }}
            <em :class="h.ok ? 'ok' : 'bad'">{{ h.ok ? '绿' : '红' }}</em>
            <em v-if="h.provider === 'main'" class="ok">AI</em>
            <em v-else-if="h.provider === 'mock'" class="dim">骨架</em>
            <em v-if="h.created_at" class="dim">{{ (h.created_at || '').slice(5, 16).replace('T', ' ') }}</em>
            <em v-if="h.ok && h.status === 'ready'" style="cursor:pointer;text-decoration:underline;margin-left:6px"
               role="button" tabindex="0"
               @click.stop="playHistory(h)" @keydown.enter.stop="playHistory(h)">重开一局 ▸</em>
          </button>
        </div>
        <p v-else class="dim tiny sw-history-empty">还没有出过本——生成一次后，这里可以浏览、加载和重开你的剧本。</p>
      </footer>
    </div>`
  };

  window.VIEWS = window.VIEWS || {};
  window.VIEWS.studio = StudioView;
})();
