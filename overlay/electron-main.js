// -*- coding: utf-8 -*-
/**
 * Token Widget — Cluely 式透明置顶浮层（Electron 架构，独立软件版）
 * ====================================================
 * 参考 Cluely 技术方案：
 *   1. Visual layer:  transparent:true + alwaysOnTop:true 的 BrowserWindow
 *   2. Anti-capture:   setContentProtection(true)（Windows 上包装 WDA_EXCLUDEFROMCAPTURE）
 *
 * 独立软件能力（Phase A）：
 *   - 单例锁：requestSingleInstanceLock 防重复启动
 *   - 托盘常驻：Tray 图标 + 菜单（显示/隐藏 / 退出）
 *   - 销毁式隐藏：关闭浮窗 = destroy 窗口（释放 renderer 内存），进程由托盘常驻
 *   - 优雅退出：托盘「退出」→ 保存 → 清理进程树
 *
 * 结构：
 *   - 主窗口：单行胶囊（透明背景），可拖拽，点击展开详情
 *   - 详情 popup：点击胶囊后弹出的完整信息卡片（×/Esc 关闭）
 */
const { app, BrowserWindow, ipcMain, screen, Tray, Menu, nativeImage } = require('electron');
const path = require('path');
const fs = require('fs');

const WIDGET_HTML = path.join(__dirname, 'widget.html');   // 自包含：widget.html 在 overlay/ 目录内
const TRAY_ICON = path.join(__dirname, 'assets', 'tray.png');

const ENABLE_PROTECT = process.env.TOKEN_WIDGET_NO_PROTECT !== '1';

const SIZE = {
  pill: { w: 320, h: 36 },
  popup: { w: 480, h: 560 }
};

let mainWin = null;
let popupWin = null;
let tray = null;
let isQuitting = false;   // 真正退出标记（区别于「隐藏到托盘」）

// ============ 配置持久化（Phase B：位置记忆 / 开机自启） ============
function configPath() {
  return path.join(app.getPath('userData'), 'config.json');
}

function loadConfig() {
  try {
    return JSON.parse(fs.readFileSync(configPath(), 'utf8'));
  } catch (_) {
    return {};
  }
}

function saveConfig(cfg) {
  try {
    fs.writeFileSync(configPath(), JSON.stringify(cfg, null, 2), 'utf8');
  } catch (_) { /* 忽略写入失败 */ }
}

function rememberWindowBounds() {
  if (!mainWin) return;
  try {
    const cfg = loadConfig();
    cfg.windowPosition = mainWin.getBounds();
    saveConfig(cfg);
  } catch (_) { /* 忽略 */ }
}

// ============ 单例锁：防止重复启动 ============
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    // 用户再次双击图标 → 显示主窗口
    showMainWindow();
  });

  // ============ 窗口 ============
  function makeOverlay(win) {
    win.setAlwaysOnTop(true, 'screen-saver');
    if (ENABLE_PROTECT) {
      try { win.setContentProtection(true); } catch (e) { /* 平台不支持忽略 */ }
    }
    win.setBackgroundColor('#00000000');
  }

  function createMainWindow() {
    if (mainWin) return;
    const area = screen.getPrimaryDisplay().workAreaSize;
    const s = SIZE.pill;
    // 位置记忆：优先用上次保存的位置，否则屏幕居中
    const cfg = loadConfig();
    const saved = cfg.windowPosition;
    const x = (saved && typeof saved.x === 'number' && typeof saved.y === 'number')
      ? saved.x : Math.round((area.width - s.w) / 2);
    const y = (saved && typeof saved.x === 'number' && typeof saved.y === 'number')
      ? saved.y : Math.round((area.height - s.h) / 2);
    mainWin = new BrowserWindow({
      width: s.w,
      height: s.h,
      x: Math.max(0, Math.min(x, area.width - s.w)),
      y: Math.max(0, Math.min(y, area.height - s.h)),
      frame: false,
      transparent: true,
      alwaysOnTop: true,
      resizable: false,
      skipTaskbar: true,
      hasShadow: false,
      backgroundColor: '#00000000',
      title: 'Token Widget',
      webPreferences: {
        nodeIntegration: false,
        contextIsolation: true,
        backgroundThrottling: true,   // 隐藏时降 CPU
        preload: path.join(__dirname, 'preload.js')
      }
    });

    makeOverlay(mainWin);
    mainWin.loadFile(WIDGET_HTML);
    // 主窗口「关闭」= 销毁窗口、隐藏到托盘（不退出进程）
    mainWin.on('closed', () => { mainWin = null; });
  }

  function showMainWindow() {
    if (!mainWin) createMainWindow();
    if (mainWin) { mainWin.show(); mainWin.focus(); }
  }

  function hideMainWindow() {
    // 销毁式隐藏：释放 renderer 内存，仅托盘常驻
    rememberWindowBounds();   // 位置记忆：隐藏前保存位置
    if (popupWin) { popupWin.close(); popupWin = null; }
    if (mainWin) { mainWin.destroy(); mainWin = null; }
  }

  function createPopup() {
    if (popupWin) { popupWin.focus(); return; }
    if (!mainWin) return;
    const area = screen.getPrimaryDisplay().workAreaSize;
    const s = SIZE.popup;
    const b = mainWin.getBounds();
    let x = b.x - Math.round((s.w - b.width) / 2);
    let y = b.y + b.height + 10;
    x = Math.max(8, Math.min(x, area.width - s.w - 8));
    y = Math.max(8, Math.min(y, area.height - s.h - 8));

    popupWin = new BrowserWindow({
      width: s.w,
      height: s.h,
      x, y,
      frame: false,
      transparent: true,
      alwaysOnTop: true,
      resizable: false,
      skipTaskbar: true,
      hasShadow: false,
      backgroundColor: '#00000000',
      title: 'Token 详情',
      webPreferences: {
        nodeIntegration: false,
        contextIsolation: true,
        backgroundThrottling: true,
        preload: path.join(__dirname, 'preload.js')
      }
    });

    makeOverlay(popupWin);
    popupWin.loadFile(WIDGET_HTML, { hash: 'popup' });
    popupWin.on('closed', () => { popupWin = null; });
  }

  // ============ 托盘 ============
  function isAutoStart() {
    try { return app.getLoginItemSettings().openAtLogin; } catch (_) { return false; }
  }
  function setAutoStart(v) {
    try { app.setLoginItemSettings({ openAtLogin: v }); } catch (_) { /* 忽略 */ }
  }

  function buildTrayMenu() {
    return Menu.buildFromTemplate([
      { label: mainWin ? '隐藏浮窗' : '显示浮窗', click: () => {
          if (mainWin) hideMainWindow(); else showMainWindow();
      } },
      { type: 'separator' },
      { label: '开机自启', type: 'checkbox', checked: isAutoStart(), click: (item) => {
          setAutoStart(item.checked);
      } },
      { type: 'separator' },
      { label: '退出', click: () => {
          isQuitting = true;
          app.quit();
      } }
    ]);
  }

  function createTray() {
    let icon = nativeImage.createFromPath(TRAY_ICON);
    if (icon.isEmpty()) {
      // 图标缺失兜底：用 16x16 空图，避免 Tray 崩溃
      icon = nativeImage.createEmpty();
    }
    tray = new Tray(icon);
    tray.setToolTip('Token Widget');
    tray.on('click', () => {
      // 单击托盘：显示/隐藏切换
      if (mainWin) hideMainWindow(); else showMainWindow();
    });
    tray.setContextMenu(buildTrayMenu());

    // 每次菜单弹出时刷新「显示/隐藏」文案 + 开机自启状态
    tray.on('right-click', () => {
      tray.setContextMenu(buildTrayMenu());
    });
  }

  // ============ IPC ============
  ipcMain.on('open-popup', () => createPopup());
  ipcMain.on('close-popup', () => { if (popupWin) { popupWin.close(); popupWin = null; } });
  ipcMain.on('hide-app', () => hideMainWindow());   // 胶囊 × 按钮 = 隐藏到托盘
  ipcMain.on('quit-app', () => { isQuitting = true; app.quit(); });

  // 手动拖拽：取窗口位置（渲染进程发起，异步返回）
  ipcMain.handle('get-bounds', () => {
    if (mainWin) return mainWin.getBounds();
    return null;
  });
  // 手动拖拽：移动窗口
  ipcMain.on('move-to', (e, x, y) => {
    if (mainWin) mainWin.setPosition(Math.round(x), Math.round(y));
  });

  // ============ 生命周期 ============
  app.whenReady().then(() => {
    createTray();
    createMainWindow();
    app.on('activate', () => showMainWindow());
  });

  // 窗口全部关闭时**不退出**（托盘常驻）；仅 isQuitting 时退出
  app.on('window-all-closed', () => {
    if (isQuitting) app.quit();
  });

  app.on('before-quit', () => {
    isQuitting = true;
    rememberWindowBounds();   // 退出前保存窗口位置
  });
}
