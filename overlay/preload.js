// 预加载脚本：在隔离渲染进程中暴露安全的本地能力给 widget.html
// 直读 ~/.workbuddy/projects/**/*.jsonl，实时统计 token 消耗
const { contextBridge, ipcRenderer, shell } = require('electron');
const fs = require('fs');
const os = require('os');
const path = require('path');

const PROJECTS = path.join(os.homedir(), '.workbuddy', 'projects');
const APP_SESSIONS = path.join(os.homedir(), '.workbuddy', 'app', 'sessions.json');

function walk(dir, out) {
  let ents;
  try { ents = fs.readdirSync(dir, { withFileTypes: true }); } catch (_) { return; }
  for (const e of ents) {
    const p = path.join(dir, e.name);
    try {
      if (e.isDirectory()) walk(p, out);
      else if (e.name.endsWith('.jsonl')) out.push(p);
    } catch (_) { /* 忽略权限/符号链接 */ }
  }
}

/**
 * 增量缓存：token 数据是 append-only 的 jsonl，逐文件按 mtime/size 判断是否变化，
 * 只重扫变化的文件，避免每次 tick 全量重扫 ~1.2 万条记录（原先 ~4.8s，严重卡顿 UI）。
 * 累计状态（seen 去重 / 总量 / 按模型 / 会话）跨 tick 持久化在模块级。
 */
const filesMeta = new Map();   // path -> { mtimeMs, size }
const seen = new Set();        // messageId 去重（跨 scan 持久）
let input = 0, output = 0, total = 0, requests = 0;
const bm = {};                 // model -> { model, in, out, tot, cache, n }
const sessions = {};           // sessionId -> { sessionId, input, output, total, requests, lastTs }

/** 解析一段 jsonl 文本，把新记录累进模块级状态（去重 + 聚合） */
function ingest(txt) {
  const lines = txt.split('\n');
  for (const line of lines) {
    if (line.indexOf('rawUsage') < 0) continue;
    let o;
    try { o = JSON.parse(line); } catch (_) { continue; }
    const pd = o.providerData || {};
    const ru = pd.rawUsage;
    if (!ru) continue;
    if (!o.timestamp) continue;          // 与 extract.py 口径一致：无时间戳不计入
    const mid = pd.messageId;
    if (mid) {
      if (seen.has(mid)) continue;        // 同一 API 响应多次落盘只计一次
      seen.add(mid);
    }
    const inp = Number(ru.prompt_tokens || 0);
    const out = Number(ru.completion_tokens || 0);
    const tot = Number(ru.total_tokens || (inp + out));
    input += inp; output += out; total += tot; requests++;

    const model = pd.requestModelName || pd.model || 'unknown';
    const m = bm[model] = bm[model] || { model, in: 0, out: 0, tot: 0, cache: 0, n: 0 };
    m.in += inp; m.out += out; m.tot += tot; m.n++;
    let c = 0;
    if (ru.prompt_cache_hit_tokens) c = Number(ru.prompt_cache_hit_tokens);
    else if (ru.prompt_tokens_details && ru.prompt_tokens_details.cached_tokens) c = Number(ru.prompt_tokens_details.cached_tokens);
    m.cache += c;

    // 会话聚合
    const sid = o.sessionId || o.conversationId || pd.sessionId || 'unknown';
    const s = sessions[sid] = sessions[sid] || { sessionId: sid, input: 0, output: 0, total: 0, requests: 0, lastTs: 0 };
    s.input += inp; s.output += out; s.total += tot; s.requests++;
    const ts = Number(o.timestamp);
    if (ts > s.lastTs) s.lastTs = ts;
  }
}

/**
 * 读 WorkBuddy 当前活跃会话：app/sessions.json 按 resumedAt 降序，第一个即当前会话。
 * 切换会话时 WorkBuddy 会更新 resumedAt 排序，widget 据此跟随切换。
 */
function readCurrentConversationId() {
  try {
    const j = JSON.parse(fs.readFileSync(APP_SESSIONS, 'utf8'));
    const list = j && j.sessions;
    if (Array.isArray(list) && list.length > 0 && list[0].conversationId) {
      return list[0].conversationId;
    }
  } catch (_) { /* 忽略 */ }
  return null;
}

function scan() {
  const files = [];
  walk(PROJECTS, files);

  for (const fp of files) {
    let st;
    try { st = fs.statSync(fp); } catch (_) { continue; }
    const prev = filesMeta.get(fp);
    if (prev && prev.mtimeMs === st.mtimeMs && prev.size === st.size) {
      continue;  // 文件未变化，跳过（用缓存）
    }
    filesMeta.set(fp, { mtimeMs: st.mtimeMs, size: st.size });
    let txt;
    try { txt = fs.readFileSync(fp, 'utf8'); } catch (_) { continue; }
    ingest(txt);
  }

  const byModel = Object.values(bm).sort((a, b) => b.tot - a.tot);

  // 当前对话 = WorkBuddy 当前激活的会话（sessions.json 第一个）；fallback 时间戳最新
  const activeId = readCurrentConversationId();
  let currentSession = activeId ? sessions[activeId] : null;
  if (!currentSession) {
    let maxTs = -1;
    for (const s of Object.values(sessions)) {
      if (s.lastTs > maxTs) { maxTs = s.lastTs; currentSession = s; }
    }
  }

  return { input, output, total, requests, byModel, currentSession, scannedAt: Date.now() };
}

contextBridge.exposeInMainWorld('api', {
  hasLive: true,
  readTokens: () => scan(),
  openPopup: () => ipcRenderer.send('open-popup'),
  closePopup: () => ipcRenderer.send('close-popup'),
  hide: () => ipcRenderer.send('hide-app'),      // 胶囊 × = 隐藏到托盘
  getBounds: () => ipcRenderer.invoke('get-bounds'),   // 手动拖拽：取窗口位置
  moveTo: (x, y) => ipcRenderer.send('move-to', x, y), // 手动拖拽：移动窗口（绝对坐标）
  moveBy: (dx, dy) => ipcRenderer.send('move-by', dx, dy), // 手动拖拽：增量移动（避免竞态）
  openFile: (p) => { try { shell.openPath(p); } catch (_) {} }
});
