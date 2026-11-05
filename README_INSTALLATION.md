# LIGHT AI V1.0 — Windows Installation & Setup Guide

Welcome to **LIGHT AI V1.0**, an intelligent voice assistant featuring a futuristic 3D Tactical HUD, real-time voice activity monitoring, YouTube music playback, conversational memory, and direct text command integration.

This guide walks you through setting up and running LIGHT AI on any 64-bit Windows computer without needing developer tools or pre-existing Python environments.

---

## 1. System Requirements

- **Operating System**: Windows 10 or Windows 11 (64-bit only).
- **Processor**: Dual-Core 2.0 GHz or higher (x86_64).
- **Memory (RAM)**: Minimum 8 GB (16 GB recommended for smooth 3D orb rendering).
- **Disk Space**: Approximately 1.5 GB free space (for virtual environment and dashboard packages).
- **Audio Hardware**: Working microphone (for voice commands) and speakers/headphones (for voice responses and music).
- **Network**: Active internet connection (required during first-time setup to download Python/npm packages and for AI reasoning / neural TTS at runtime).

---

## 2. Quick-Start (3 Simple Steps)

1. **Extract the ZIP file**:
   - Right-click the downloaded `LIGHT_AI_V1.0_Windows.zip` and select **Extract All...**.
   - Choose a destination folder (e.g., `C:\LIGHT_AI` or your `Desktop`) and complete extraction.
   - *Note: Do not run files from inside the compressed zip folder.*

2. **Run One-Click Setup**:
   - Open the extracted folder.
   - Double-click **`SETUP.bat`**.
   - The setup wizard will automatically verify Python, initialize a private `.venv` environment, install dependencies, compile the desktop HUD, and place a shortcut on your Desktop.

3. **Configure Your API Key**:
   - Open the `.env` file in Notepad (created automatically from template).
   - Locate `COE_AI_KEY=PASTE_YOUR_API_KEY_HERE`.
   - Replace `PASTE_YOUR_API_KEY_HERE` with your personal CoE AI Gateway API key.
   - Save and close the file.

4. **Launch LIGHT AI**:
   - Double-click the **`LIGHT AI V1.0`** shortcut on your Desktop!

---

## 3. Prerequisite Software

The setup script (`SETUP.bat`) checks for all required prerequisites automatically. If any are missing, install them using the official links below:

### A. Python (Required)
- **Version**: Python **3.12 (64-bit)** (Python 3.10 to 3.12 are supported).
- **Official Download**: [https://www.python.org/downloads/](https://www.python.org/downloads/)
- **CRITICAL STEP DURING INSTALLATION**:
  - When the Python installer opens, check the box that says **"Add python.exe to PATH"** before clicking "Install Now".

### B. Node.js & npm (Required)
- **Version**: Node.js **20 LTS** or **22 LTS** (64-bit).
- **Official Download**: [https://nodejs.org/](https://nodejs.org/)
- **Note**: Node.js powers the Electron desktop shell and HUD interface. Standard installation includes the `npm` package manager.

### C. VLC Media Player (Optional — for Music Playback)
- **Version**: VLC Media Player **64-bit** for Windows.
- **Official Download**: [https://www.videolan.org/vlc/](https://www.videolan.org/vlc/)
- **Note**: VLC provides the audio decoding engine for streaming YouTube songs and playlists. If VLC is not installed, all assistant features (voice recognition, AI questions, app launching, WhatsApp) will still work normally; only background music playback will be disabled.

---

## 4. First-Run Configuration (`.env`)

LIGHT AI connects to an OpenAI-compatible vLLM inference gateway. During setup, a `.env` configuration file is automatically created in the project folder.

Open `.env` in Notepad and verify your settings:

```env
# CoE AI Gateway Endpoint
COE_AI_BASE_URL=https://ai.tcetcercd.in/v1

# Target AI Model
COE_AI_MODEL=qwen3.6

# Your Personal API Key (Required for conversational responses)
COE_AI_KEY=your_actual_api_key_here

# Request Timeout in seconds
COE_AI_TIMEOUT_SECONDS=10.0

# Context Capacity in tokens (Optional - defaults to Unknown if left empty)
COE_AI_CONTEXT_CAPACITY=
```

---

## 5. How to Launch & Use LIGHT AI

### Launching
- Double-click the **`LIGHT AI V1.0`** shortcut on your Windows Desktop.
- Alternatively, double-click **`Launch_LIGHT_AI.bat`** in the project folder.

### Using the Assistant
- **Voice Commands**: Say `"Light"` followed by your command (e.g., *"Light, play Zaalima song"* or *"Light, who are you?"*).
- **Direct Text Input**: Type any command directly into the **TEXT COMMAND CONSOLE** at the bottom-right of the dashboard without needing the wake word.
- **Push-to-Talk (PTT)**: Press the **Spacebar** while focused on the assistant window to trigger instant voice listening.
- **Music Controls**: Use the interactive music controls on the dashboard to Play, Pause, Skip, adjust Volume, or Mute.
- **Emergency Stop**: Click the **PANIC / ABORT** button or say *"Light, stop"* to immediately halt audio and cancel in-flight tasks.

### Clean Shutdown
- Simply close the Electron dashboard window, or press `Ctrl + C` in the launcher console window. All background processes and ports are cleaned up automatically.

---

## 6. Troubleshooting & FAQs

### Q1: The launcher says "Port 8765 is active / in use".
- **Cause**: A previous session of LIGHT AI did not exit completely, or another application is using port 8765.
- **Solution**: Open Task Manager (`Ctrl + Shift + Esc`), look for any lingering `python.exe` or `electron.exe` processes and end them, or wait 10 seconds for Windows to release the port and relaunch.

### Q2: Speech recognition doesn't hear me.
- **Cause**: Windows microphone privacy settings or muted microphone.
- **Solution**:
  1. Open Windows **Settings > Privacy & Security > Microphone**.
  2. Ensure **"Microphone access"** and **"Let desktop apps access your microphone"** are turned **ON**.
  3. Ensure your microphone is set as the default recording device in Windows Sound settings.

### Q3: Music says "Stream Unavailable" or fails to play.
- **Cause**: VLC Media Player 64-bit is missing or YouTube stream was temporarily blocked.
- **Solution**:
  1. Ensure VLC 64-bit is installed at `C:\Program Files\VideoLAN\VLC`.
  2. Restart LIGHT AI.

### Q4: Responses are slow or failing with "Gateway Error".
- **Cause**: Invalid API key or internet connectivity issue.
- **Solution**: Check your `.env` file to confirm `COE_AI_KEY` is correct and test your network connection to `https://ai.tcetcercd.in/v1`.

---

## 7. Uninstallation & Removal

LIGHT AI V1.0 is completely self-contained within its extracted directory. It does not install background services or modify Windows registry keys.

To completely remove LIGHT AI:
1. Delete the desktop shortcut **`LIGHT AI V1.0.lnk`**.
2. Delete the extracted `LIGHT_AI_V1.0_Windows` folder.

