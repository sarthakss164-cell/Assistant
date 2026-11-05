const { contextBridge, ipcRenderer } = require('electron');

// Secure context bridge exposing only specific, safe channels to renderer
contextBridge.exposeInMainWorld('electronAPI', {
  platform: process.platform,
  minimize: () => ipcRenderer.send('window:minimize'),
  maximize: () => ipcRenderer.send('window:maximize'),
  close: () => ipcRenderer.send('window:close'),
  sendAction: (action, payload) => {
    // Explicit action allowlist
    const ALLOWED_ACTIONS = ['STOP_TTS', 'PANIC_ABORT', 'MUSIC_CONTROL', 'VOLUME_CHANGE', 'MIC_TOGGLE'];
    if (ALLOWED_ACTIONS.includes(action)) {
      ipcRenderer.send('action:execute', { action, payload });
    } else {
      console.warn(`[PRELOAD SECURITY] Blocked unauthorized action: ${action}`);
    }
  },
  onStateUpdate: (callback) => {
    const subscription = (event, data) => callback(data);
    ipcRenderer.on('state:update', subscription);
    return () => ipcRenderer.removeListener('state:update', subscription);
  }
});
