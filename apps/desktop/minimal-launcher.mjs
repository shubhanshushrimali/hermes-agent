// Minimal Electron launcher — bypasses all bootstrap/backend logic
// Just opens the Vite renderer in a visible BrowserWindow
import { app, BrowserWindow } from 'electron';

app.whenReady().then(() => {
  const win = new BrowserWindow({
    width: 1220,
    height: 800,
    show: true,
    title: 'Hermes Desktop',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true
    }
  });

  win.loadURL('http://127.0.0.1:5174/');
  win.on('closed', () => app.quit());
  console.log('[minimal-launcher] Window created and loading http://127.0.0.1:5174/');
});

app.on('window-all-closed', () => app.quit());
