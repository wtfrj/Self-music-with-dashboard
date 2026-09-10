/* ═══════════════════════════════════════════════════════════
   Self Music Dashboard
   MADE BY RJ
═══════════════════════════════════════════════════════════ */

// ── State ─────────────────────────────────────────────────────────────────────
let ws = null;
let wsReconnectTimer = null;
let isPlaying = false;
let isPaused = false;
let isLooped = false;
let currentLength = 0;
let currentPos = 0;
let progressInterval = null;
let allServers = [];
let currentTrackUri = '';

// ── WebSocket Connection ───────────────────────────────────────────────────────
function connectWS() {
  clearTimeout(wsReconnectTimer);
  setWsDot('connecting', 'Connecting...');

  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${proto}//${location.host}/ws`);

  ws.onopen = () => {
    setWsDot('connected', 'Connected');
    showNotif('Connected to dashboard', 'success');
  };

  ws.onmessage = (event) => {
    let data;
    try { data = JSON.parse(event.data); } catch { return; }

    switch (data.type) {
      case 'state_update': handleStateUpdate(data); break;
      case 'position_update': handlePositionUpdate(data); break;
      case 'notification': showNotif(data.message, data.level || 'info'); break;
      case 'error': showNotif(data.message, 'error'); break;
      case 'search_results': renderSearchResults(data.results); break;
    }
  };

  ws.onclose = () => {
    setWsDot('disconnected', 'Disconnected');
    ws = null;
    wsReconnectTimer = setTimeout(connectWS, 3000);
  };

  ws.onerror = () => {
    setWsDot('disconnected', 'Error');
  };
}

function setWsDot(state, label) {
  const dot = document.getElementById('ws-dot');
  const lbl = document.getElementById('ws-label');
  dot.className = `ws-dot ${state}`;
  lbl.textContent = label;
}

function sendWS(payload) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    showNotif('Not connected to dashboard!', 'error');
    return false;
  }
  ws.send(JSON.stringify(payload));
  return true;
}

// ── State Handlers ─────────────────────────────────────────────────────────────
function handleStateUpdate(data) {
  // User info
  if (data.user) {
    const el = document.getElementById('user-name');
    if (el) el.textContent = data.user.name;
    const av = document.getElementById('user-avatar');
    if (av && data.user.avatar) av.src = data.user.avatar;
  }

  // Servers sidebar
  allServers = data.all_servers || [];
  renderSidebarServers(allServers);
  populateVCServerDropdown(allServers);
  renderServersGrid(allServers);

  // Active server
  if (data.server) {
    setText('server-name', data.server.name);
    setText('server-channel', '# ' + (data.server.channel || ''));
    const si = document.getElementById('server-icon');
    if (si && data.server.icon) si.src = data.server.icon;
  } else {
    setText('server-name', 'Not in a VC');
    setText('server-channel', '-');
  }

  // Loop mode
  isLooped = data.loop_mode === 'loop' || data.loop_mode === 'loop_all';
  const loopBtn = document.getElementById('btn-loop');
  if (loopBtn) loopBtn.classList.toggle('active', isLooped);
  const loopInd = document.getElementById('loop-indicator');
  if (loopInd) loopInd.style.display = isLooped ? 'flex' : 'none';

  // Volume
  const volSlider = document.getElementById('vol-slider');
  if (volSlider && data.volume !== undefined) volSlider.value = data.volume;

  // Player
  isPlaying = data.is_playing;
  isPaused = data.is_paused;

  const playIcon = document.getElementById('play-icon');
  const thumb = document.getElementById('song-thumbnail');
  const discRing = document.getElementById('disc-ring');
  const progressFill = document.getElementById('progress-fill');

  if (isPlaying && data.track) {
    setText('song-title', data.track.title);
    setText('song-author', data.track.author);

    if (thumb) {
      thumb.src = data.track.thumbnail || buildPlaceholder(data.track.title);
      thumb.classList.toggle('playing', !isPaused);
    }
    if (discRing) discRing.classList.toggle('playing', !isPaused);

    if (playIcon) playIcon.className = isPaused ? 'fas fa-play' : 'fas fa-pause';

    // Song link
    const link = document.getElementById('song-link');
    if (link && data.track.uri) {
      link.href = data.track.uri;
      link.style.display = 'inline-flex';
      currentTrackUri = data.track.uri;
    }

    currentLength = data.track.length || 0;
    currentPos = data.track.position || 0;

    setText('time-total', formatMs(currentLength));

    // Progress pauses when paused
    if (progressFill) progressFill.classList.toggle('paused', isPaused);

    restartProgressInterval();
  } else {
    // Nothing playing
    setText('song-title', 'No Song Playing');
    setText('song-author', 'Queue is empty');
    if (thumb) {
      thumb.src = "data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='110' height='110' viewBox='0 0 110 110'%3E%3Crect width='100%25' height='100%25' fill='%23060d14' rx='14'/%3E%3Ccircle cx='55' cy='55' r='36' fill='%23020509' stroke='%2300AEEF' stroke-width='2' stroke-dasharray='4 2'/%3E%3Cpath d='M48 38v30c-2-1.5-5-2-8-1-4 1.5-6 5.5-5 9s4 5.5 8 4c4-1.5 6-5.5 5-9V48l18-4v20c-2-1.5-5-2-8-1-4 1.5-6 5.5-5 9s4 5.5 8 4c4-1.5 6-5.5 5-9V38z' fill='%2300AEEF'/%3E%3C/svg%3E";
      thumb.classList.remove('playing');
    }
    if (discRing) discRing.classList.remove('playing');
    if (playIcon) playIcon.className = 'fas fa-play';
    const link = document.getElementById('song-link');
    if (link) link.style.display = 'none';

    clearProgressInterval();
    currentPos = 0;
    currentLength = 0;
    updateProgressBar();
  }

  // Queue
  renderQueue(data.queue || [], data.track);
}

function handlePositionUpdate(data) {
  // Real-time position sync from server ticker
  currentPos = data.position || currentPos;
  currentLength = data.length || currentLength;
  isPaused = data.is_paused || false;
  isPlaying = data.is_playing || false;

  const progressFill = document.getElementById('progress-fill');
  const playIcon = document.getElementById('play-icon');
  const thumb = document.getElementById('song-thumbnail');
  const discRing = document.getElementById('disc-ring');

  if (progressFill) progressFill.classList.toggle('paused', isPaused);
  if (playIcon) playIcon.className = isPaused ? 'fas fa-play' : 'fas fa-pause';
  if (thumb) thumb.classList.toggle('playing', !isPaused && isPlaying);
  if (discRing) discRing.classList.toggle('playing', !isPaused && isPlaying);

  if (isPaused) {
    clearProgressInterval();
  } else if (isPlaying && !progressInterval) {
    restartProgressInterval();
  }

  updateProgressBar();
}

// ── Progress Bar ───────────────────────────────────────────────────────────────
function restartProgressInterval() {
  clearProgressInterval();
  if (!isPaused) {
    progressInterval = setInterval(() => {
      if (!isPaused && currentPos < currentLength) {
        currentPos += 1000;
        updateProgressBar();
      }
    }, 1000);
  }
  updateProgressBar();
}

function clearProgressInterval() {
  if (progressInterval) {
    clearInterval(progressInterval);
    progressInterval = null;
  }
}

function updateProgressBar() {
  const fill = document.getElementById('progress-fill');
  const timeCur = document.getElementById('time-current');

  if (currentLength > 0) {
    const pct = Math.min((currentPos / currentLength) * 100, 100);
    if (fill) fill.style.width = pct + '%';
  } else {
    if (fill) fill.style.width = '0%';
  }
  if (timeCur) timeCur.textContent = formatMs(currentPos);
}

// ── Queue Render ───────────────────────────────────────────────────────────────
function renderQueue(queue, nowTrack) {
  const list = document.getElementById('queue-list');
  const counter = document.getElementById('queue-count');
  if (!list) return;

  const totalCount = queue.length + (nowTrack ? 1 : 0);
  if (counter) counter.textContent = `${totalCount} song${totalCount !== 1 ? 's' : ''}`;

  if (!nowTrack && queue.length === 0) {
    list.innerHTML = `
      <div class="empty-state">
        <i class="fas fa-music"></i>
        <p>Queue is empty. Play a song to get started!</p>
      </div>`;
    return;
  }

  list.innerHTML = '';

  // Now playing row at top
  if (nowTrack) {
    const nowEl = document.createElement('div');
    nowEl.className = 'queue-item now-playing-row';
    nowEl.innerHTML = `
      <div class="qi-num"><i class="fas fa-volume-up" style="font-size:0.75rem"></i></div>
      <img class="qi-thumb" src="${nowTrack.thumbnail || buildPlaceholder(nowTrack.title)}" alt="">
      <div class="qi-info">
        <div class="qi-title">${escHtml(nowTrack.title)}</div>
        <div class="qi-author">${escHtml(nowTrack.author)}</div>
      </div>
      <div class="qi-len">${formatMs(nowTrack.length)}</div>
      <div class="qi-len" style="color:var(--sky);font-size:0.72rem">PLAYING</div>
    `;
    list.appendChild(nowEl);
  }

  queue.forEach((track, i) => {
    const el = document.createElement('div');
    el.className = 'queue-item';
    el.innerHTML = `
      <div class="qi-num">${i + 1}</div>
      <img class="qi-thumb" src="${track.thumbnail || buildPlaceholder(track.title)}" alt="">
      <div class="qi-info">
        <div class="qi-title">${escHtml(track.title)}</div>
        <div class="qi-author">${escHtml(track.author)}</div>
      </div>
      <div class="qi-len">${formatMs(track.length)}</div>
      <button class="qi-remove" onclick="removeFromQueue(${i})" title="Remove">
        <i class="fas fa-times"></i>
      </button>
    `;
    list.appendChild(el);
  });
}

// ── Sidebar Servers ────────────────────────────────────────────────────────────
function renderSidebarServers(servers) {
  const wrap = document.getElementById('sidebar-servers');
  if (!wrap) return;
  wrap.innerHTML = '';
  if (!servers.length) {
    wrap.innerHTML = '<div class="server-item-sm"><span>No servers</span></div>';
    return;
  }
  servers.forEach(s => {
    const el = document.createElement('div');
    el.className = 'server-item-sm';
    el.title = `${s.name}\nID: ${s.id}`;
    el.innerHTML = `
      <img src="${s.icon || buildServerPlaceholder(s.name)}" alt="${escHtml(s.name)}">
      <span>${escHtml(s.name)}</span>
    `;
    el.onclick = () => {
      showView('servers');
      showNotif(`Server: ${s.name}`, 'info');
    };
    wrap.appendChild(el);
  });
}

function renderServersGrid(servers) {
  const grid = document.getElementById('servers-grid');
  const total = document.getElementById('total-servers');
  if (!grid) return;
  if (total) total.textContent = servers.length;
  if (!servers.length) {
    grid.innerHTML = `<div class="empty-state" style="grid-column:1/-1"><i class="fas fa-server"></i><p>No servers found.</p></div>`;
    return;
  }
  grid.innerHTML = '';
  servers.forEach(s => {
    const el = document.createElement('div');
    el.className = 'server-card-item glass';
    el.innerHTML = `
      <img src="${s.icon || buildServerPlaceholder(s.name)}" alt="${escHtml(s.name)}">
      <div class="sc-name">${escHtml(s.name)}</div>
      <div class="sc-id">${s.id}</div>
      <div class="sc-badge">${s.member_count || '?'} members</div>
    `;
    grid.appendChild(el);
  });
}

// ── VC Dropdown ────────────────────────────────────────────────────────────────
function populateVCServerDropdown(servers) {
  const sel = document.getElementById('vc-server-select');
  if (!sel) return;
  const current = sel.value;
  sel.innerHTML = '<option value="">-- Select a Server --</option>';
  servers.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s.id;
    opt.textContent = s.name;
    sel.appendChild(opt);
  });
  if (current) sel.value = current;
}

function populateVCChannels() {
  const serverSel = document.getElementById('vc-server-select');
  const channelSel = document.getElementById('vc-channel-select');
  if (!serverSel || !channelSel) return;

  const guildId = serverSel.value;
  channelSel.innerHTML = '<option value="">-- Select a Voice Channel --</option>';

  const server = allServers.find(s => s.id === guildId);
  if (!server || !server.channels) return;

  server.channels.forEach(ch => {
    const opt = document.createElement('option');
    opt.value = ch.id;
    opt.textContent = `${ch.name} (${ch.members} 🔊)`;
    channelSel.appendChild(opt);
  });
}

// ── Actions ────────────────────────────────────────────────────────────────────
function sendAction(action, extra = {}) {
  sendWS({ action, ...extra });
}

function playSong() {
  const input = document.getElementById('search-input');
  const query = input ? input.value.trim() : '';
  if (!query) {
    showNotif('Please enter a song name or URL.', 'warning');
    return;
  }

  // Clear search results
  clearSearchResults();

  sendWS({ action: 'play', query });
  showNotif(`🔍 Searching: ${query}`, 'info');
  if (input) input.value = '';
}

function playSpecific(uri, title) {
  sendWS({ action: 'play', query: uri });
  showNotif(`▶ Adding: ${title}`, 'info');
  clearSearchResults();
}

function setVolume(val) {
  sendWS({ action: 'volume', value: parseInt(val) });
}

function joinVCFromDropdown() {
  const serverSel = document.getElementById('vc-server-select');
  const channelSel = document.getElementById('vc-channel-select');
  if (!serverSel || !channelSel) return;

  const guildId = serverSel.value;
  const channelId = channelSel.value;

  if (!guildId) { showNotif('Please select a server.', 'warning'); return; }
  if (!channelId) { showNotif('Please select a voice channel.', 'warning'); return; }

  sendWS({ action: 'join_vc', guild_id: guildId, channel_id: channelId });
}

function joinVCById() {
  const input = document.getElementById('vc-channel-id-input');
  const id = input ? input.value.trim() : '';
  if (!id) { showNotif('Please enter a channel ID.', 'warning'); return; }
  sendWS({ action: 'join_vc', channel_id: id });
  if (input) input.value = '';
}

function joinServer() {
  const input = document.getElementById('invite-input');
  const url = input ? input.value.trim() : '';
  if (!url) { showNotif('Please enter an invite link or code.', 'warning'); return; }
  // Accept full URLs like https://discord.gg/abc or just the code "abc"
  if (url.length < 2) { showNotif('Invalid invite code.', 'warning'); return; }
  sendWS({ action: 'join_server', invite_url: url });
  showNotif('Sending join request...', 'info');
  if (input) input.value = '';
}

function removeFromQueue(index) {
  sendWS({ action: 'remove_queue', index });
}

function openView(name) {
  showView(name);
}

// ── Search Live ────────────────────────────────────────────────────────────────
let searchDebounce = null;

document.addEventListener('DOMContentLoaded', () => {
  const si = document.getElementById('search-input');
  if (si) {
    si.addEventListener('input', () => {
      clearTimeout(searchDebounce);
      const q = si.value.trim();
      if (q.length < 3) { clearSearchResults(); return; }
      // Don't search URLs — play directly
      if (q.startsWith('http')) { clearSearchResults(); return; }
      searchDebounce = setTimeout(() => {
        sendWS({ action: 'search', query: q });
      }, 600);
    });
  }
});

function renderSearchResults(results) {
  const wrap = document.getElementById('search-results');
  if (!wrap) return;
  wrap.innerHTML = '';
  if (!results || !results.length) return;

  results.forEach(r => {
    const el = document.createElement('div');
    el.className = 'search-result-item';
    el.innerHTML = `
      <img src="${r.thumbnail || buildPlaceholder(r.title)}" alt="">
      <div class="sri-info">
        <div class="sri-title">${escHtml(r.title)}</div>
        <div class="sri-author">${escHtml(r.author)}</div>
      </div>
      <div class="sri-len">${formatMs(r.length)}</div>
    `;
    el.onclick = () => playSpecific(r.uri, r.title);
    wrap.appendChild(el);
  });
}

function clearSearchResults() {
  const wrap = document.getElementById('search-results');
  if (wrap) wrap.innerHTML = '';
}

// ── View Navigation ────────────────────────────────────────────────────────────
function showView(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-link').forEach(a => a.classList.remove('active'));

  const view = document.getElementById(`view-${name}`);
  if (view) view.classList.add('active');

  const navLink = document.getElementById(`nav-${name}`);
  if (navLink) navLink.classList.add('active');

  // Load stats when stats view opens
  if (name === 'stats') loadStats();
}

// ── Stats ──────────────────────────────────────────────────────────────────────
async function loadStats() {
  try {
    const res = await fetch('/api/stats');
    const data = await res.json();
    if (data.error) { showNotif(data.error, 'error'); return; }

    setText('stat-uptime', data.uptime || '--:--:--');
    setText('stat-guilds', data.guilds ?? '-');
    setText('stat-vc', data.voice_connections ?? '-');
    setText('stat-songs', data.songs_played ?? '-');
    setText('stat-ping', data.ping ? data.ping + 'ms' : '-');
    setText('stat-ws', data.ws_clients ?? '-');
  } catch (e) {
    showNotif('Failed to load stats.', 'error');
  }
}

// Auto-refresh stats every 30s when stats view is active
setInterval(() => {
  const statsView = document.getElementById('view-stats');
  if (statsView && statsView.classList.contains('active')) {
    loadStats();
  }
}, 30000);

// ── Notification System ────────────────────────────────────────────────────────
function showNotif(message, type = 'info') {
  const container = document.getElementById('notif-container');
  if (!container) return;

  const icons = {
    success: 'fa-check-circle',
    error: 'fa-exclamation-circle',
    warning: 'fa-exclamation-triangle',
    info: 'fa-info-circle',
  };

  const notif = document.createElement('div');
  notif.className = `notif ${type}`;
  notif.innerHTML = `
    <i class="fas ${icons[type] || icons.info} n-icon"></i>
    <span class="n-msg">${escHtml(String(message))}</span>
    <button class="n-close" onclick="dismissNotif(this.parentElement)">
      <i class="fas fa-times"></i>
    </button>
  `;

  container.appendChild(notif);

  // Auto dismiss after 4s
  setTimeout(() => dismissNotif(notif), 4000);
}

function dismissNotif(el) {
  if (!el || el.classList.contains('hide')) return;
  el.classList.add('hide');
  setTimeout(() => el.remove(), 320);
}

// ── Helpers ────────────────────────────────────────────────────────────────────
function formatMs(ms) {
  if (!ms || ms <= 0) return '0:00';
  const totalSec = Math.floor(ms / 1000);
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return `${min}:${sec.toString().padStart(2, '0')}`;
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function buildPlaceholder(title) {
  const text = (title || 'Music').substring(0, 2).toUpperCase();
  return `data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='42' height='42' viewBox='0 0 42 42'%3E%3Crect width='100%25' height='100%25' fill='%23060d14' rx='6'/%3E%3Ctext x='50%25' y='54%25' dominant-baseline='middle' text-anchor='middle' fill='%2300AEEF' font-family='Space Grotesk, sans-serif' font-weight='bold' font-size='14'%3E${text}%3C/text%3E%3C/svg%3E`;
}

function buildServerPlaceholder(name) {
  const text = (name || 'S').substring(0, 2).toUpperCase();
  return `data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='56' height='56' viewBox='0 0 56 56'%3E%3Crect width='100%25' height='100%25' fill='%23060d14' rx='14'/%3E%3Ctext x='50%25' y='54%25' dominant-baseline='middle' text-anchor='middle' fill='%2300AEEF' font-family='Space Grotesk, sans-serif' font-weight='bold' font-size='18'%3E${text}%3C/text%3E%3C/svg%3E`;
}

// ── Init ───────────────────────────────────────────────────────────────────────
connectWS();
