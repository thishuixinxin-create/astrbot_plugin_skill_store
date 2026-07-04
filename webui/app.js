/**
 * SKILL 商店 - 前端应用
 *
 * 通过 /api/plug/ 遗留兼容路径直接调用后端 API。
 * 使用 credentials: 'include' 传递 cookie 鉴权。
 */

const API_PREFIX = '/api/plug/astrbot_plugin_skill_store';
let currentPage = 1;
let currentKeyword = '';

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', () => {
  loadCacheStatus();
  loadSkills();
});

// ==================== 页面切换 ====================

function switchPage(name) {
  document.querySelectorAll('.page').forEach(p => p.style.display = 'none');
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById(`page-${name}`).style.display = 'block';
  document.querySelector(`.nav-item[data-page="${name}"]`).classList.add('active');

  if (name === 'browse') loadSkills();
  if (name === 'installed') loadInstalled();
}

// ==================== 通知 ====================

function showToast(msg, type = 'info') {
  const existing = document.querySelector('.toast');
  if (existing) existing.remove();
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

// ==================== API 请求 ====================

async function apiGet(endpoint, params) {
  const query = params ? '?' + new URLSearchParams(params).toString() : '';
  const resp = await fetch(`${API_PREFIX}${endpoint}${query}`, {
    credentials: 'include',
    headers: { 'Accept': 'application/json' },
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  if (data.status === 'error') throw new Error(data.message || '请求失败');
  return data.data ?? data;
}

async function apiPost(endpoint, body) {
  const resp = await fetch(`${API_PREFIX}${endpoint}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  if (data.status === 'error') throw new Error(data.message || '请求失败');
  return data.data ?? data;
}

// ==================== 浏览 SKILL ====================

async function loadSkills(page = 1) {
  currentPage = page;
  const container = document.getElementById('skill-list');
  container.innerHTML = `<div class="loading"><div class="loading-spinner"></div><p>正在加载...</p></div>`;

  try {
    const params = { page: String(page) };
    if (currentKeyword) params.keyword = currentKeyword;

    const data = await apiGet('/api/search', params);
    const skills = data.skills || [];
    const total = data.total || skills.length;

    if (skills.length === 0) {
      container.innerHTML = `<div class="empty-state"><div class="icon">🔍</div><p>没有找到 SKILL，试试换个关键词喵~</p></div>`;
      return;
    }

    container.innerHTML = `<div style="font-size:13px;color:var(--text-secondary);margin-bottom:12px">共 ${total} 个匹配结果</div><div class="skill-grid">${skills.map(skill => renderSkillCard(skill)).join('')}</div>`;
    renderPagination(page, total);
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><div class="icon">❌</div><p>请求失败：${escapeHtml(e.message)}</p></div>`;
    console.error('[SkillStore]', e);
  }
}

function renderSkillCard(skill) {
  const name = skill.name || skill.full_name || '?';
  const desc = skill.description ? escapeHtml(skill.description.substring(0, 150)) : '(无描述)';
  const stars = skill.stars || 0;
  const author = skill.owner || '?';
  const fullName = skill.full_name || '';
  const topics = (skill.topics || []).filter(t => t !== 'astrbot-skill').join(', ');

  return `
    <div class="skill-card">
      <div class="skill-card-header">
        <div class="skill-name" title="${escapeHtml(fullName)}">${escapeHtml(name)}</div>
        <div class="skill-stars">⭐ ${stars}</div>
      </div>
      <div class="skill-desc">${desc}</div>
      <div class="skill-meta">
        <span>👤 ${escapeHtml(author)}</span>
        ${topics ? `<span>🏷 ${escapeHtml(topics)}</span>` : ''}
      </div>
      <div class="skill-card-actions">
        <button class="btn btn-outline btn-sm" onclick="showDetail('${escapeHtml(fullName)}')">详情</button>
        <button class="btn btn-primary btn-sm" onclick="installSkill('${escapeHtml(fullName)}', '${escapeHtml(name)}')">安装</button>
      </div>
    </div>
  `;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// ==================== 搜索 & 分页 ====================

function searchSkills() {
  const input = document.getElementById('search-input');
  currentKeyword = input.value.trim();
  loadSkills(1);
}

function clearSearch() {
  document.getElementById('search-input').value = '';
  currentKeyword = '';
  loadSkills(1);
}

function renderPagination(currentPage, total) {
  const container = document.getElementById('pagination');
  const perPage = 30;
  const totalPages = Math.ceil(total / perPage);
  if (totalPages <= 1) { container.innerHTML = ''; return; }
  const pages = [];
  const start = Math.max(1, currentPage - 2);
  const end = Math.min(totalPages, currentPage + 2);
  for (let i = start; i <= end; i++) pages.push(i);
  container.innerHTML = `
    <button class="btn btn-outline btn-sm" onclick="loadSkills(${Math.max(1, currentPage - 1)})" ${currentPage <= 1 ? 'disabled' : ''}>⬅</button>
    ${pages.map(p => `<button class="btn btn-outline btn-sm ${p === currentPage ? 'active' : ''}" onclick="loadSkills(${p})">${p}</button>`).join('')}
    <button class="btn btn-outline btn-sm" onclick="loadSkills(${Math.min(totalPages, currentPage + 1)})" ${currentPage >= totalPages ? 'disabled' : ''}>➡</button>`;
}

// ==================== 详情、安装、管理、缓存 ====================

async function showDetail(fullName) {
  const modal = document.getElementById('detail-modal');
  const title = document.getElementById('detail-title');
  const body = document.getElementById('detail-body');
  title.textContent = '加载中...';
  body.innerHTML = `<div class="loading"><div class="loading-spinner"></div></div>`;
  modal.classList.add('show');
  try {
    const data = await apiGet('/api/detail', { full_name: fullName });
    if (!data.detail) { body.innerHTML = '<p>无法加载 SKILL 详情</p>'; title.textContent = fullName; return; }
    const d = data.detail;
    title.textContent = d.name || fullName;
    body.innerHTML = `
      <div class="modal-section"><h3>📝 描述</h3><p>${escapeHtml(d.description || '(无描述)')}</p></div>
      <div class="modal-section"><h3>ℹ️ 信息</h3><p>📦 版本：${escapeHtml(d.version || '?')} · 👤 作者：${escapeHtml(d.author || (d.full_name||'').split('/')[0] || '?')} · ⭐ ${d.stars || 0} Stars</p></div>
      <div class="modal-section"><h3>📄 预览</h3><div class="readme-content">${escapeHtml(d.raw_skill_md_preview || '无预览')}</div></div>
      <div style="display:flex;gap:8px;margin-top:16px">
        <button class="btn btn-primary" onclick="installSkill('${escapeHtml(d.full_name||fullName)}','${escapeHtml(d.name||fullName)}');closeDetail();">📥 安装此 SKILL</button>
        <button class="btn btn-outline" onclick="closeDetail()">关闭</button>
      </div>`;
  } catch (e) { body.innerHTML = `<p>加载失败：${e.message}</p>`; title.textContent = fullName; }
}

function closeDetail() { document.getElementById('detail-modal').classList.remove('show'); }

async function installSkill(fullName, skillName) {
  if (!confirm(`确定要安装「${skillName}」吗喵？`)) return;
  try {
    const r = await apiPost('/api/install', { full_name: fullName, skill_name: skillName, branch: 'main' });
    showToast(r.success ? `✅ ${r.message||'安装成功！'}` : `❌ ${r.message||'安装失败'}`, r.success?'success':'error');
    if (r.success) { loadSkills(currentPage); loadInstalled(); }
  } catch (e) { showToast(`❌ ${e.message}`, 'error'); }
}

async function loadInstalled() {
  const container = document.getElementById('installed-list');
  container.innerHTML = `<div class="loading"><div class="loading-spinner"></div><p>加载中...</p></div>`;
  try {
    const data = await apiGet('/api/installed');
    const list = data.installed || [];
    if (!list.length) { container.innerHTML = '<div class="empty-state"><div class="icon">📦</div><p>还没有安装任何 SKILL~</p></div>'; return; }
    container.innerHTML = `<div class="installed-list">${list.map(s => renderInstalledItem(s)).join('')}</div>`;
  } catch (e) { container.innerHTML = `<div class="empty-state"><div class="icon">❌</div><p>${e.message}</p></div>`; }
}

function renderInstalledItem(skill) {
  const name = skill.name || skill.skill_name || '?';
  const active = skill.active !== false;
  const t = skill.installed_at ? new Date(skill.installed_at*1000).toLocaleString() : '未知';
  return `<div class="installed-item"><div class="installed-item-info"><div class="installed-item-name">${escapeHtml(name)}<span class="status-badge ${active?'status-active':'status-inactive'}">${active?'运行中':'已停用'}</span></div><div class="installed-item-meta">v${escapeHtml(skill.version||'?')} · ${t}</div></div><div class="installed-item-actions"><button class="btn btn-outline btn-sm" onclick="toggleSkill('${escapeHtml(name)}',${!active})">${active?'停用':'启用'}</button><button class="btn btn-danger btn-sm" onclick="uninstallSkill('${escapeHtml(name)}')">卸载</button></div></div>`;
}

async function toggleSkill(n, active) {
  try {
    const r = await apiPost('/api/toggle', { skill_name: n, active });
    showToast(r.success ? `✅ ${r.message||'ok'}` : `❌ ${r.message||'fail'}`, r.success?'success':'error');
    if (r.success) loadInstalled();
  } catch (e) { showToast(`❌ ${e.message}`, 'error'); }
}

async function uninstallSkill(n) {
  if (!confirm(`确定卸载「${n}」？不可逆喵！`)) return;
  try {
    const r = await apiPost('/api/uninstall', { skill_name: n });
    showToast(r.success ? `✅ ${r.message||'卸载成功'}` : `❌ ${r.message||'卸载失败'}`, r.success?'success':'error');
    if (r.success) { loadInstalled(); loadSkills(currentPage); }
  } catch (e) { showToast(`❌ ${e.message}`, 'error'); }
}

async function loadCacheStatus() {
  try {
    const data = await apiGet('/api/cache/status');
    const el = document.getElementById('cache-status');
    if (!el) return;
    if (data.cache_age < 0) { el.textContent='📭 无缓存'; el.style.color='var(--danger)'; }
    else if (data.is_fresh) { const h=Math.floor(data.cache_age/3600),m=Math.floor((data.cache_age%3600)/60); el.textContent=`📦 ${data.skills_count}个 ${h}h${m}m前`; el.style.color='var(--success)'; }
    else { el.textContent='⚠️ 已过期'; el.style.color='var(--warning)'; }
  } catch(e) {}
}

async function refreshCache() {
  if (!confirm('从 GitHub 全量检索所有 SKILL？需要几分钟喵~')) return;
  const btn = document.querySelector('button[onclick="refreshCache()"]');
  if (btn) { btn.disabled=true; btn.textContent='⏳ ...'; }
  try {
    const r = await apiPost('/api/cache/refresh', {});
    showToast(r.success ? `✅ ${r.message||'ok'}` : `❌ ${r.message||'fail'}`, r.success?'success':'error');
    if (r.success) { loadCacheStatus(); loadSkills(currentPage); }
  } catch(e) { showToast(`❌ ${e.message}`, 'error'); }
  finally { if(btn) { btn.disabled=false; btn.textContent='🔄 更新缓存'; } }
}
