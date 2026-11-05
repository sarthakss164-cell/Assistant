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

  // Wait 4 seconds for Three.js WebGL and React rendering
  await new Promise((r) => setTimeout(r, 4000));

  // Populate sample direct command and focus textarea to showcase active console UI
  await win.webContents.executeJavaScript(`
    (() => {
      const ta = document.querySelector('textarea');
      if (ta) {
        // Set sample text command
        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
        nativeInputValueSetter.call(ta, 'play Hindi playlist');
        ta.dispatchEvent(new Event('input', { bubbles: true }));
        ta.focus();
      }
    })();
  `);

  await new Promise((r) => setTimeout(r, 1000));

  const image = await win.webContents.capturePage();
  const outPath = 'C:\\Users\\Sundaram\\.gemini\\antigravity\\brain\\119bb60d-1a51-4d80-87d0-24a2d0c01640\\phase_d4_3_preview.png';
  fs.writeFileSync(outPath, image.toPNG());
  console.log(`Phase D4.3 preview saved to: ${outPath}`);
  app.exit(0);
});

