/* 工作台简报：空稿、回填、从 job 水合。不碰 Vue 视图。 */
(function (g) {
  const C = g.STUDIO = g.STUDIO || {};

  C.emptyBrief = function (hook) {
    return {
      hook: hook || (C.PRESETS && C.PRESETS[0]) || '',
      pack_type: 'fun_mech',
      lock: { timebox: '', space: '', lock_rule: '', win: '', tone: '', theme: '' },
      camp: { pollution: '污染', swayable: '可策反', truth: '求真', public: false, win_pollution: '', win_truth: '' },
      cast: ['char_01', 'char_02', 'char_03', 'char_04'].map(id => ({
        id: id, name: '', archetype: '', comedy_hook: '', public_bio: ''
      })),
      truth: { surface: '', crime: '', motive: '', method: '' },
      board_notes: '',
      acts: ['act1', 'act2', 'act3'].map(id => ({
        id: id, name: '', brief: '', must_reveal: '', must_not_reveal: '', twist: '', comedy: ''
      })),
      modules: C.emptyMods ? C.emptyMods() : {},
      minis: ['heart', 'refute3', 'runner', 'badge'],
      vibe: { mood: 'comedy', horror_beats: '', dm: '', comedy: '' },
      voice: { dm: '', comedy: '' }
    };
  };

  C.asLine = function (v) {
    if (Array.isArray(v)) return v.filter(Boolean).join('，');
    return v == null ? '' : String(v);
  };

  C.normActs = function (job) {
    if (!job) return [];
    const a = job.acts;
    return Array.isArray(a) ? a : (a && a.acts) || [];
  };

  C.fillBriefFrom = function (src, target) {
    const s = src || {};
    target.hook = s.hook || target.hook;
    if (s.pack_type) target.pack_type = s.pack_type;
    const lock = s.lock || {};
    Object.keys(target.lock).forEach(k => { if (lock[k]) target.lock[k] = lock[k]; });
    const camp = s.camp || {};
    Object.keys(target.camp).forEach(k => {
      if (k === 'public' && 'public' in camp) target.camp.public = !!camp.public;
      else if (camp[k]) target.camp[k] = camp[k];
    });
    (s.cast || []).forEach((row, i) => {
      if (!target.cast[i] || !row) return;
      ['name', 'archetype', 'comedy_hook', 'public_bio'].forEach(k => {
        if (row[k]) target.cast[i][k] = row[k];
      });
    });
    const t = s.truth || {};
    Object.keys(target.truth).forEach(k => { if (t[k]) target.truth[k] = t[k]; });
    if (s.board_notes) target.board_notes = s.board_notes;
    (s.acts || []).forEach((row, i) => {
      if (!target.acts[i] || !row) return;
      target.acts[i].name = row.name || target.acts[i].name;
      target.acts[i].brief = row.brief || target.acts[i].brief;
      target.acts[i].must_reveal = C.asLine(row.must_reveal) || target.acts[i].must_reveal;
      target.acts[i].must_not_reveal = C.asLine(row.must_not_reveal) || target.acts[i].must_not_reveal;
      target.acts[i].twist = row.twist || row.twist_beat || target.acts[i].twist;
      target.acts[i].comedy = row.comedy || row.comedy_beat || target.acts[i].comedy;
    });
    if (s.modules) Object.keys(target.modules).forEach(k => {
      if (k in s.modules) target.modules[k] = !!s.modules[k];
    });
    if (Array.isArray(s.minis)) {
      target.minis.splice(0, target.minis.length);
      s.minis.forEach(id => target.minis.push(id));
    }
    const vibe = s.vibe || {};
    if (vibe.mood) target.vibe.mood = vibe.mood;
    if (vibe.horror_beats) target.vibe.horror_beats = vibe.horror_beats;
    const v = s.voice || {};
    target.vibe.dm = vibe.dm || v.dm || target.vibe.dm;
    target.vibe.comedy = C.asLine(vibe.comedy || v.comedy) || target.vibe.comedy;
    target.voice.dm = target.vibe.dm;
    target.voice.comedy = target.vibe.comedy;
  };

  C.hydrateFromJob = function (brief, job) {
    if (!job) return;
    const saved = job.seed && job.seed.brief;
    if (saved) C.fillBriefFrom(saved, brief);
    if (job.seed && job.seed.text && !brief.hook) brief.hook = job.seed.text;
    const w = job.world || {};
    if (!brief.lock.theme) brief.lock.theme = w.theme || '';
    if (!brief.lock.tone) brief.lock.tone = w.tone || '';
    (w.cast_slots || []).forEach((slot, i) => {
      if (!brief.cast[i]) return;
      if (!brief.cast[i].name) brief.cast[i].name = slot.name || '';
      if (!brief.cast[i].archetype) brief.cast[i].archetype = slot.archetype || '';
      if (!brief.cast[i].comedy_hook) brief.cast[i].comedy_hook = slot.comedy_hook || '';
    });
    if (!brief.truth.surface) brief.truth.surface = w.surface_truth || '';
    const cul = (job.detail && job.detail.culprit) || {};
    if (!brief.truth.crime) brief.truth.crime = cul.crime || '';
    if (!brief.truth.motive) brief.truth.motive = cul.motive || '';
    if (!brief.truth.method) brief.truth.method = cul.method || '';
    C.normActs(job).forEach((a, i) => {
      if (!brief.acts[i]) return;
      if (!brief.acts[i].name) brief.acts[i].name = a.name || '';
      if (!brief.acts[i].brief) brief.acts[i].brief = a.brief || '';
      if (!brief.acts[i].must_reveal) brief.acts[i].must_reveal = C.asLine(a.must_reveal);
      if (!brief.acts[i].must_not_reveal) brief.acts[i].must_not_reveal = C.asLine(a.must_not_reveal);
      if (!brief.acts[i].twist) brief.acts[i].twist = a.twist_beat || '';
      if (!brief.acts[i].comedy) brief.acts[i].comedy = a.comedy_beat || '';
    });
    if (job.modules) Object.keys(brief.modules).forEach(k => {
      if (k in job.modules) brief.modules[k] = !!job.modules[k];
    });
    if (!brief.vibe.dm && C.normActs(job)[0]) brief.vibe.dm = C.normActs(job)[0].dm_notes || '';
    if (!brief.vibe.comedy && w.comedy_sources) brief.vibe.comedy = C.asLine(w.comedy_sources);
    brief.voice.dm = brief.vibe.dm;
    brief.voice.comedy = brief.vibe.comedy;
  };
})(typeof window !== 'undefined' ? window : globalThis);
