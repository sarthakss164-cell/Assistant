const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    width: 1400,
    height: 860,
    show: false,
    webPreferences: {
      offscreen: true,
      contextIsolation: false,
      nodeIntegration: true,
    },
  });

  const targetUrl = process.argv[2] || 'http://localhost:5173';
  console.log(`Loading: ${targetUrl}`);

  try {
    if (targetUrl.startsWith('http')) {
      await win.loadURL(targetUrl);
    } else {
      await win.loadFile(targetUrl);
    }
  } catch (err) {
    console.error('Failed to load URL:', err);
    app.exit(1);
  }

  // Wait 3.5 seconds for Three.js WebGL rendering and animations to initialize
  await new Promise((r) => setTimeout(r, 3500));

  const image = await win.webContents.capturePage();
  const outPath = process.argv[3] || 'C:\\Users\\Sundaram\\.gemini\\antigravity\\brain\\119bb60d-1a51-4d80-87d0-24a2d0c01640\\phase_d4_2_preview.png';
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, image.toPNG());
  console.log(`Screenshot saved to: ${outPath}`);
  app.exit(0);
});
