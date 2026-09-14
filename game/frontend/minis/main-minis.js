/* ============================================================
 * main-minis.js —— mini 宿主接入主应用（#/mini/{id} hash 路由）
 * 职责：boot 时检测 hash → view='mini'（免登录外链直达，不过 session）；
 *       注册 MiniHostView（壳顶栏 = 标题/数据源声明/计分/返回）与 $minisClose。
 * ============================================================ */
(function () {
  const { ref, computed } = Vue;

  const MiniHostView = {
    setup() {
      const cur = ref(window.Minis.currentId());
      const onChange = () => { cur.value = window.Minis.currentId(); };
      window.addEventListener('hashchange', onChange);
      const def = computed(() => window.Minis.REG[cur.value] || null);
      const catalog = computed(() => window.Store.studioMiniCatalog());
      const back = () => { window.Minis.close(); cur.value = null; onChange(); };
      return { cur, def, catalog, back, S: window.Store.state };
    },
    template: `
    <section class="view mini-host">
      <header class="mini-top">
        <div class="mini-top-l">
          <img src="../content/assets/images/logo_badge.png" alt="" class="mini-logo">
          <div><b>求真档案局 · 迷你游戏厅</b><span>免登录即可试玩</span></div>
        </div>
        <div class="mini-top-r">
          <span class="chip" v-if="S.dossier">侦探：{{ S.dossier.name }}</span>
          <button class="btn ghost sm" @click="back">← 回主线</button>
        </div>
      </header>

      <template v-if="def">
        <div class="mini-def">
          <h2>{{ def.title }}</h2>
          <p class="dim">{{ def.tagline }}</p>
          <p class="dim">{{ def.entry }}</p>
        </div>
        <component :is="def.component"></component>
      </template>

      <div v-else class="mini-lobby">
        <h2>四件可选（安放位图 §9.4 全做）</h2>
        <div class="mini-lobby-grid">
          <button v-for="(d, id) in catalog" :key="id" class="mini-card" @click="Minis.open(id)">
            <b>{{ d.title }}</b>
            <span class="dim">{{ d.tagline }}</span>
            <em class="dim">{{ d.entry }}</em>
          </button>
        </div>
        <p class="dim">铁律沿用：不新增美术管线、不上传用户数据、分享卡只导出图片不做自动发布。</p>
      </div>
    </section>`
  };

  function install(app) {
    app.component('mini-host', MiniHostView);
    app.config.globalProperties.$minisClose = () => window.Minis.close();
    window.VIEWS.mini = MiniHostView;
  }
  window.MinisInstall = install;

  // hash 预检：boot 前把 #/mini/* 映射进 Store.view（main.js 读 URL 参数白名单不含 mini，这里补）
  if (/^#\/mini\//.test(location.hash || '')) {
    window.__MINI_BOOT__ = window.Minis.currentId();
  }
})();
