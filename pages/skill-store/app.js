// SKILL Store v0.1.1
(function() {
  var bridge = window.AstrBotPluginPage;
  if (!bridge) return document.getElementById('list').innerHTML = '<div style="text-align:center;padding:60px;color:red">Bridge not loaded</div>';

  var allSkills = [], currentPage = 1, _totalFromAPI = 0;
  var PER_PAGE = 24;

  // ===== 前端日志 =====
  function flog(level, msg, data) {
    try {
      var x = new XMLHttpRequest();
      x.open('POST', '/api/plug/astrbot_plugin_skill_store/api/log');
      x.setRequestHeader('Content-Type','application/json');
      x.withCredentials = true;
      x.send(JSON.stringify({level:level, msg:msg, data:String(data||'').slice(0,500)}));
    } catch(e) {}
  }
  window.onerror = function(msg,u,l) { flog('error', msg+' at '+u+':'+l); };
  window.addEventListener('unhandledrejection', function(e) { flog('error', 'Promise: '+String(e.reason)); });

  // ===== 缓存 =====
  function loadCache() {
    try {
      var r = localStorage.getItem('ss_all');
      flog('info', 'cache check: ' + (r ? 'found' : 'empty'));
      if (!r) return null;
      var c = JSON.parse(r);
      var age = Date.now() - c.ts;
      var days = age / 86400000;
      flog('info', 'cache age: ' + days.toFixed(1) + ' days, skills: ' + (c.skills ? c.skills.length : 0));
      if (age > 604800000) { flog('info', 'cache expired'); return null; } // 7 days
      return c.skills;
    } catch(e) { flog('error', 'cache load error', e.message); return null; }
  }
  function saveCache(s) {
    try {
      localStorage.setItem('ss_all', JSON.stringify({skills:s, ts:Date.now()}));
      flog('info', 'cache saved: ' + (s ? s.length : 0) + ' skills');
    } catch(e) { flog('error', 'cache save error', e.message); }
  }

  // ===== UI =====
  function showLoading() {
    document.getElementById('list').innerHTML = '<div style="display:flex;justify-content:center;align-items:center;height:400px"><div style="width:48px;height:48px;border:4px solid #e0e0e0;border-top-color:#6c5ce7;border-radius:50%;animation:spin 0.8s linear infinite"></div></div>';
  }

  function esc(s) { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

  // ===== 获取数据 =====
  async function fetchPage(p) {
    try {
      var result = await bridge.apiGet('/api/search', { page: String(p) });
      return result;
    } catch(e) {
      flog('error', 'fetchPage '+p+' failed', e.message);
      throw e;
    }
  }

  // ===== 渲染 =====
  function render() {
    var el = document.getElementById('list');
    if (!allSkills.length) {
      el.innerHTML = '<div style="text-align:center;padding:80px 20px"><div style="font-size:48px;margin-bottom:16px;color:#b2bec3">Empty</div><div style="font-size:14px;color:#b2bec3">Click Refresh Cache</div></div>';
      document.getElementById('pagination').innerHTML = '';
      return;
    }
    var start = (currentPage - 1) * PER_PAGE;
    if (start >= allSkills.length) { currentPage = 1; start = 0; }
    var skills = allSkills.slice(start, start + PER_PAGE);
    var totalPages = Math.ceil(allSkills.length / PER_PAGE);

    var html = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px">';
    for (var i = 0; i < skills.length; i++) {
      var s = skills[i];
      var n = s.name || s.skill_name || '?';
      var desc = (s.description || '').slice(0, 150);
      var star = s.stars || 0;
      var fn = s.full_name || '';
      var owner = s.owner || fn.split('/')[0] || '';
      var repo = fn.split('/')[1] || '';
      html += '<div class="sc" style="background:#fff;border-radius:14px;padding:20px;box-shadow:0 2px 16px rgba(0,0,0,0.06);transition:all 0.25s ease;cursor:default;border:1px solid #edf2f7">'
        + '<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px">'
        + '<div style="font-weight:600;font-size:15px;color:#2d3436;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1">' + esc(n) + '</div>'
        + '<div style="font-size:13px;color:#fdcb6e;font-weight:600;flex-shrink:0;margin-left:8px">&#11088; ' + star + '</div>'
        + '</div>'
        + '<div style="font-size:13px;color:#636e72;line-height:1.6;margin-bottom:12px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;min-height:58px">' + esc(desc) + '</div>'
        + '<div style="display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap;font-size:11px;color:#b2bec3">'
        + '<span style="background:#f0f2f5;padding:2px 8px;border-radius:5px">' + esc(owner) + '</span>'
        + '<span style="background:#f0f2f5;padding:2px 8px;border-radius:5px">' + esc(repo) + '</span>'
        + '</div>'
        + '<div style="display:flex;gap:8px" class="ca">'
        + '<button class="b b-o" onclick="window.analyze(\'' + esc(fn) + '\',\'' + esc(n) + '\')">&#128269; 分析</button>'
        + '<button class="b b-o" onclick="window.open(\'https://github.com/' + esc(fn) + '\')">GitHub</button>'
        + '<button class="b b-p" onclick="window.install(\'' + esc(fn) + '\',\'' + esc(n) + '\')">&#11015; 安装</button>'
        + '</div></div>';
    }
    html += '</div>';
    el.innerHTML = html;

    updatePagination(totalPages);
  }

  function updatePagination(totalPages) {
    if (totalPages === undefined) {
      var effectiveTotal = Math.max(allSkills.length, _totalFromAPI);
      totalPages = Math.ceil(effectiveTotal / PER_PAGE);
    }
    var el = document.getElementById('pagination');
    if (totalPages <= 1) { el.innerHTML = ''; return; }
    var h = '<div style="display:flex;justify-content:center;align-items:center;gap:6px;margin-top:24px;padding:8px 0">';
    if (currentPage > 1) h += '<button class="pb" data-page="' + (currentPage-1) + '">&#8592;</button>';
    for (var i = Math.max(1, currentPage-3); i <= Math.min(totalPages, currentPage+3); i++) {
      h += '<button class="pb' + (i === currentPage ? ' pa' : '') + '" data-page="' + i + '">' + i + '</button>';
    }
    if (currentPage < totalPages) h += '<button class="pb" data-page="' + (currentPage+1) + '">&#8594;</button>';
    h += '<span style="font-size:12px;color:#b2bec3;margin-left:8px" id="tc">' + allSkills.length + ' skills</span></div>';
    el.innerHTML = h;
  }

  // 事件委托：监听 pagination 容器的点击
  document.getElementById('pagination').addEventListener('click', function(e) {
    var btn = e.target.closest('.pb');
    if (btn) {
      var page = parseInt(btn.getAttribute('data-page'));
      if (page && page !== currentPage) {
        currentPage = page;
        render();
        window.scrollTo({top: 0, behavior: 'smooth'});
      }
    }
  });

  window.goPage = function(p) { currentPage = p; render(); window.scrollTo({top:0,behavior:'smooth'}); };

  // ===== 主加载逻辑 =====
  var _loadingBg = false;

  async function load() {
    flog('info', 'load started');
    allSkills = loadCache();
    if (allSkills && allSkills.length) {
      flog('info', 'cache hit: '+allSkills.length);
      render();
      // 后台静默刷新（不阻塞用户）
      if (!_loadingBg) {
        _loadingBg = true;
        try {
          var d1 = await fetchPage(1);
          var s1 = d1.skills || [];
          if (s1.length && JSON.stringify(s1) !== JSON.stringify(allSkills.slice(0, s1.length))) {
            flog('info', 'cache stale, refreshing silently');
            allSkills = [];
            await _fetchAllPages();
          }
        } catch(e) { flog('warn', 'bg refresh skipped', e.message); }
        _loadingBg = false;
      }
      return;
    }

    allSkills = [];
    showLoading();

    // 拉第一页 -> 立刻显示
    try {
      flog('info', 'fetching page 1');
      var d1 = await fetchPage(1);
      var s1 = d1.skills || [];
      flog('info', 'page 1 got '+s1.length);
      if (s1.length) {
        allSkills = s1.slice();
        _totalFromAPI = d1.total || s1.length; // 保存 API 返回的 total 用于翻页
        saveCache(allSkills);
        render();
      } else {
        document.getElementById('list').innerHTML = '<div style="text-align:center;padding:80px 20px;color:#636e72">No skills. Click Refresh Cache.</div>';
      }
    } catch(e) {
      flog('error', 'initial load failed', e.message);
      document.getElementById('list').innerHTML = '<div style="text-align:center;padding:80px 20px"><div style="font-size:40px;margin-bottom:12px;color:#e17055">&#9888;</div><div style="font-size:16px;color:#636e72">Load failed</div><div style="font-size:13px;color:#b2bec3;margin:8px 0">' + e.message + '</div><button onclick="window.refresh()" style="margin-top:12px;padding:8px 24px;border:none;border-radius:10px;background:#6c5ce7;color:#fff;cursor:pointer;font-size:14px">Retry</button></div>';
      return;
    }

    await _fetchAllPages();
  }

  async function _fetchAllPages() {
    var p = 2;
    while (true) {
      try {
        flog('info', 'fetching page '+p);
        var d = await fetchPage(p);
        var sk = d.skills || [];
        if (!sk.length) { flog('info', 'done at page '+(p-1)); break; }
        allSkills = allSkills.concat(sk);
        saveCache(allSkills);
        // 只更新总数，不重新绘制翻页按钮（避免按钮被替换导致无法点击）
        var tc = document.getElementById('tc');
        if (tc) tc.textContent = allSkills.length + ' skills';
        p++;
      } catch(e) {
        flog('warn', 'page '+p+' failed', e.message);
        break;
      }
    }
    flog('info', 'total: '+allSkills.length);
  }

  // ===== 智能搜索 =====
  window.smartSearch = async function() {
    var q = document.getElementById('sq').value.trim();
    if (!q) { load(); return; }
    showLoading();
    try {
      var r = await bridge.apiPost('/api/smart_search', { query: q });
      if (r.skills && r.skills.length) {
        allSkills = r.skills;
        currentPage = 1;
        render();
        showToast('Found ' + r.total + ' matching skills', 'success');
      } else {
        document.getElementById('list').innerHTML = '<div style="text-align:center;padding:80px 20px;color:#636e72">No skills match your query</div>';
        document.getElementById('pagination').innerHTML = '';
      }
    } catch(e) {
      showToast('Search error: ' + e.message, 'error');
    }
  };

  // 清除搜索，回到全部列表
  window.clearSearch = function() {
    document.getElementById('sq').value = '';
    load();
  };

  // ===== 操作 =====
  window.refresh = async function() {
    var btn = document.querySelector('button[onclick="window.refresh()"]');
    if (btn) { btn.disabled = true; btn.textContent = '...'; }
    try { localStorage.removeItem('ss_all'); } catch(e) {}
    allSkills = [];
    await load();
    showToast('Done', 'success');
    if (btn) { btn.disabled = false; btn.textContent = 'Refresh Cache'; }
  };

  // ===== 分析弹窗 =====
  var modal = document.getElementById('am');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'am';
    modal.style.cssText = 'display:none;position:fixed;inset:0;background:rgba(0,0,0,0.4);z-index:9999;justify-content:center;align-items:center;backdrop-filter:blur(4px)';
    modal.innerHTML = '<div style="background:#fff;border-radius:20px;padding:28px;max-width:500px;width:90%;max-height:70vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,0.2)"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px"><h3 id="mt" style="margin:0;font-size:18px;font-weight:600"></h3><button id="mc" style="width:32px;height:32px;border:none;border-radius:8px;background:#f1f2f6;cursor:pointer;font-size:16px">&#10005;</button></div><div id="mb" style="font-size:14px;line-height:1.8;color:#2d3436;white-space:pre-wrap"></div></div>';
    document.body.appendChild(modal);
    document.getElementById('mc').onclick = function(){ modal.style.display='none'; };
    modal.onclick = function(e) { if (e.target === this) this.style.display='none'; };
  }

  window.analyze = async function(fn, name) {
    document.getElementById('mt').textContent = '\uD83D\uDD0D ' + name;
    document.getElementById('mb').textContent = 'Analyzing...';
    modal.style.display = 'flex';
    try {
      var r = await bridge.apiPost('/api/analyze', { full_name: fn });
      document.getElementById('mb').textContent = r.analysis || 'No result';
    } catch(e) {
      document.getElementById('mb').textContent = 'Error: ' + e.message;
    }
  };

  window.install = async function(fn, name) {
    showToast('Installing ' + name + '...', 'info');
    try {
      var r = await bridge.apiPost('/api/install', { full_name: fn, skill_name: name, branch: 'main' });
      if (r.success) showToast('Installed ' + name, 'success');
      else showToast(r.message || 'Failed', 'error');
    } catch(e) { showToast('Error: ' + e.message, 'error'); }
  };

  // ===== Toast =====
  function showToast(msg, type) {
    var c = {info:'#6c5ce7',success:'#00b894',error:'#e17055'};
    var el = document.createElement('div');
    el.style.cssText = 'position:fixed;top:20px;right:20px;z-index:99999;padding:12px 20px;border-radius:10px;color:#fff;font-size:14px;background:' + (c[type]||c.info) + ';box-shadow:0 4px 20px rgba(0,0,0,0.15);max-width:360px;transition:opacity 0.3s';
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(function(){ el.style.opacity='0'; setTimeout(function(){ el.remove(); }, 300); }, 3000);
  }

  // ===== 样式注入 =====
  var st = document.createElement('style');
  st.textContent = '@keyframes spin{to{transform:rotate(360deg)}}'
    + '.sc:hover{transform:translateY(-3px);box-shadow:0 8px 30px rgba(108,92,231,0.12)!important}'
    + '.sc:hover .ca{opacity:1!important}'
    + '.b{padding:7px 14px;border:none;border-radius:8px;font-size:12px;cursor:pointer;flex:1;text-align:center;transition:all 0.2s}'
    + '.b-o{background:#f0edff;color:#6c5ce7;font-weight:500}'
    + '.b-o:hover{background:#6c5ce7;color:#fff}'
    + '.b-p{background:#6c5ce7;color:#fff;font-weight:500}'
    + '.b-p:hover{opacity:0.85}'
    + '.pb{padding:7px 13px;border:1px solid #dfe6e9;border-radius:8px;background:#fff;cursor:pointer;font-size:13px;color:#2d3436;transition:all 0.2s;min-width:36px}'
    + '.pb:hover{border-color:#6c5ce7;color:#6c5ce7}'
    + '.pa{background:#6c5ce7;color:#fff;border-color:#6c5ce7;font-weight:600}'
    + '.pa:hover{background:#6c5ce7;color:#fff;border-color:#6c5ce7}'
    + '.ca{opacity:0;transition:opacity 0.2s}';
  document.head.appendChild(st);

  // ===== 启动 =====
  Promise.all([
    new Promise(function(r) { if (document.readyState !== 'loading') r(); else document.addEventListener('DOMContentLoaded', r); }),
    bridge.ready().catch(function(){})
  ]).then(load);
})();
