const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    width: 1600,
    height: 960,
    show: false,
    webPreferences: {
      offscreen: true,
      contextIsolation: false,
      nodeIntegration: true,
      webSecurity: false,
    },
  });

  const distPath = path.join(__dirname, 'dist', 'index.html');
  console.log('Loading dist path:', distPath);

  try {
    await win.loadFile(distPath);
  } catch (err) {
    console.error('Failed to load file:', err);
    app.exit(1);
  }

  // Wait 4.5 seconds for Three.js WebGL and WebSocket bridge events to sync
  await new Promise((r) => setTimeout(r, 4500));

  const image = await win.webContents.capturePage();
  const outPath = 'C:\\Users\\Sundaram\\.gemini\\antigravity\\brain\\119bb60d-1a51-4d80-87d0-24a2d0c01640\\phase_d4_2_preview.png';
  fs.writeFileSync(outPath, image.toPNG());
  console.log(`Phase D4.2 preview saved to: ${outPath}`);
  app.exit(0);
});

