// 预加载脚本：在隔离渲染进程中暴露安全的本地能力给 widget.html
// 直读 ~/.workbuddy/projects/**/*.jsonl，实时统计 token 消耗
const { contextBridge, ipcRenderer, shell } = require('electron');
const fs = require('fs');
const os = require('os');
const path = require('path');

const PROJECTS = path.join(os.homedir(), '.workbuddy', 'projects');

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
 * 扫描全部 jsonl，按 messageId 去重，累计 input/output/total + 按模型拆分，
 * 并按 sessionId 聚合，返回时间戳最新的会话作为"当前对话"。
 */
function scan() {
  const files = [];
  walk(PROJECTS, files);

  const seen = new Set();
  let input = 0, output = 0, total = 0, requests = 0;
  const bm = {};

  // 按 session 聚合
  const sessions = {};  // sessionId -> { input, output, total, requests, lastTs }

  for (const fp of files) {
    let txt;
    try { txt = fs.readFileSync(fp, 'utf8'); } catch (_) { continue; }
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
      const sid = o.sessionId || o.conversationId || (pd.sessionId) || 'unknown';
      const s = sessions[sid] = sessions[sid] || { sessionId: sid, input: 0, output: 0, total: 0, requests: 0, lastTs: 0 };
      s.input += inp; s.output += out; s.total += tot; s.requests++;
      const ts = Number(o.timestamp);
      if (ts > s.lastTs) s.lastTs = ts;
    }
  }

  const byModel = Object.values(bm).sort((a, b) => b.tot - a.tot);

  // 当前对话 = 时间戳最新的 session
  let currentSession = null;
  let maxTs = -1;
  for (const s of Object.values(sessions)) {
    if (s.lastTs > maxTs) { maxTs = s.lastTs; currentSession = s; }
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
  moveTo: (x, y) => ipcRenderer.send('move-to', x, y), // 手动拖拽：移动窗口
  openFile: (p) => { try { shell.openPath(p); } catch (_) {} }
});
