# LIGHT AI V1.0 — Personal Voice Assistant

Deterministic, rule-based Windows voice assistant built with Brave Browser, YouTube, WhatsApp Web, and PyWhatKit integration.

---

## 1. Overview & Architecture

LIGHT AI V1.0 is a secure, privacy-first personal desktop voice assistant. It features:
- **No LLM or Cloud AI Dependency**: Completely deterministic, rule-based command routing.
- **Sole STT**: Google Speech Recognition via Python's `SpeechRecognition` library (`recognize_google`).
- **Configurable Speech Output**: Microsoft Edge TTS (`hi-IN-SwaraNeural`) with automatic local Windows SAPI5 (`Microsoft Kalpana` / `pyttsx3`) fallback.
- **Acoustic Settling Guard**: Approved ~400 ms post-playback audio delay to eliminate self-recognition loops.
- **Brave Browser Primary & Process Reuse**:
  - Brave Browser (`brave.exe`) is the primary browser target.
  - Process detection via `psutil` checks if Brave is running.
  - When Brave is running, Chromium's native IPC reuses existing windows and opens new tabs rather than creating duplicate processes.
  - Commands saying `open Chrome` or `open Google Chrome` deterministically route to Brave Browser.
- **YouTube Integration**:
  - `open YouTube` opens `https://www.youtube.com` in Brave.
  - `YouTube <query>` (e.g. `YouTube Python full course`, `YouTube Arijit Singh songs`) opens search results in Brave with proper URL encoding.
- **Google Search**:
  - `search latest AI`, `search for <query>`, `google <query>` open Google search results in Brave with proper URL encoding.
- **WhatsApp Web & PyWhatKit Messaging**:
  - `open WhatsApp` / `open WhatsApp Web` opens `https://web.whatsapp.com` in Brave.
  - `message <contact>` / `send message to <contact>` initiates the messaging workflow.
  - Interactive prompts for missing contact or missing message.
  - Strict user confirmation prompt before initiating PyWhatKit sending.
  - Contact lookup from `config/contacts.json` with strict Indian phone normalization (`91XXXXXXXXXX`) and masked logging (`91******XXXX`).
  - PyWhatKit integration with authentication requirement reminders and honest delivery status.
- **State Machine Lifecycle**:
  - `WAITING_FOR_ACTIVATION`: Awaits the first valid supported command starting with `"Light"` (e.g., *"Light, open Brave"*, *"Light, who are you?"*). Unprefixed and exit commands are ignored in this state.
  - `ACTIVE_SESSION`: Subsequent supported commands require no prefix (e.g., *"Who are you?"*, *"YouTube Python full course"*, *"Search latest AI"*).
  - `AWAITING_CONFIRMATION`: Modal sub-state for WhatsApp message confirmation. Interruption via approved exit commands is fully supported.
  - `SHUTDOWN`: Graceful shutdown releasing mixer, microphone, and temporary audio files.
- **Strict Exit Command Set**: Exactly `['exit', 'stop', 'terminate', 'good bye']`. Substrings in search queries (e.g., *"Search how to stop procrastinating"*) never trigger exit.
- **Application Allowlist**: Strictly limited to Brave, Chrome, Notepad, WhatsApp Web, and Visual Studio Code. Zero arbitrary shell execution.
- **Fixed Identity Response**: Exact approved response: *"Main Light AI hoon, jise mere Boss ne banaya hai."* with phonetic variations (`hu r u`, `who r u`, `who are you`).

---

## 2. Directory Structure

```
Light_AI_V1/
├── actions/
│   ├── app_launcher.py      # Allowlist enforcement & Windows App Paths launcher
│   ├── browser.py           # Brave primary browser management & process reuse
│   ├── identity.py          # Fixed deterministic identity response
│   ├── lifecycle.py         # Graceful shutdown with independently guarded cleanups
│   ├── web_search.py        # Google and YouTube search delegation to Brave
│   └── whatsapp.py          # WhatsApp Web in Brave & PyWhatKit messaging
├── config/
│   ├── app_allowlist.json   # Approved application targets, paths, and aliases
│   ├── contacts.json.example# Safe template for user contacts
│   ├── contacts.json        # User contact mappings (git-ignored)
│   └── settings.py          # Core configurations, voices, timeouts, and constants
├── core/
│   ├── assistant.py         # Master orchestrator event loop
│   ├── normalizer.py        # Punctuation stripping and wake prefix parsing
│   ├── router.py            # Intent routing and exit command enforcement
│   └── state_machine.py     # SessionStateMachine managing assistant lifecycle
├── speech/
│   ├── listener.py          # Bounded microphone capture with ambient calibration
│   ├── stt.py               # Google Speech Recognition with error handling
│   └── tts.py               # Edge TTS primary + SAPI5 fallback + 400ms guard
├── tests/
│   ├── test_assistant.py    # Master assistant orchestration & flow tests
│   ├── test_exit_commands.py# Exit command set and substring safety tests
│   ├── test_launcher.py     # App allowlist, Brave routing, and reuse tests
│   ├── test_lifecycle.py    # Graceful shutdown and temp file purge tests
│   ├── test_normalizer.py   # Normalization and prefix extraction tests
│   ├── test_phone_normalization.py # Strict Indian mobile phone validation tests
│   ├── test_router.py       # Intent classification and routing tests
│   ├── test_search.py       # Brave search URL encoding & homepage tests
│   ├── test_speech.py       # TTS fallback, listener, and STT error tests
│   ├── test_state_machine.py# State transition tests
│   └── test_whatsapp.py     # WhatsApp Web and PyWhatKit mock tests
├── .gitignore               # Ignores contacts.json, temp mp3s, logs, caches
├── main.py                  # CLI application entrypoint
├── requirements.txt         # Pinned project dependencies
└── README.md                # Documentation and setup instructions
```

---

## 3. Installation & Setup

### Environment
The project is configured for the user's conda environment:
`.

### Step 1: Install Dependencies
From the `Light_AI_V1` directory, install required packages:
```powershell
&  pip install -r requirements.txt
```

Packages included:
- `SpeechRecognition==3.17.0`
- `PyAudio==0.2.14`
- `edge-tts==7.3.1`
- `pygame==2.6.1`
- `pyttsx3==2.99`
- `pytest==9.1.1`
- `psutil>=7.0.0`
- `pywhatkit>=5.4`

### Step 2: Configure Contacts
Ensure `config/contacts.json` is set up:
```json
{
  "rahul": "9893371769",
  "anand": "+91 98933 71769",
  "office": "09893371769"
}
```

---

## 4. Running LIGHT AI V1.0

Launch the assistant:
```powershell
& python main.py
```

### Supported Voice Commands

| Category | Example Phrases | Expected Behavior |
| :--- | :--- | :--- |
| **Session Activation** | *"Light, open Brave"*, *"Light, open Chrome"*, *"Light, who are you?"* | Required for the first command after startup |
| **Browser (Chrome)** | *"open Chrome"*, *"open Google Chrome"* | Opens or focuses existing Google Chrome window |
| **Browser (Brave)** | *"open Brave"*, *"open Brave Browser"* | Opens or focuses existing Brave Browser window |
| **Browser (Edge)** | *"open Edge"*, *"open Microsoft Edge"* | Opens or focuses existing Microsoft Edge window |
| **Generic Browser** | *"open Browser"*, *"open Internet"* | Opens or focuses configured preferred browser (Brave) |
| **YouTube** | *"open YouTube"*, *"YouTube Python full course"*, *"YouTube Arijit Singh songs"* | Opens YouTube homepage or search query in preferred browser |
| **Google Search** | *"search latest AI"*, *"search for quantum computing"*, *"google machine learning"* | Opens Google search query in preferred browser |
| **WhatsApp Web** | *"open WhatsApp"*, *"open WhatsApp Web"* | Opens `https://web.whatsapp.com` in preferred browser |
| **WhatsApp Messaging** | *"message Anand"*, *"send message to Anand"*, *"message Anand that I will be late"* | Validates contact, prompts for message if missing, confirms (accepts "han", "yes", etc.), and sends via PyWhatKit |
| **Identity** | *"Who are you?"*, *"hu r u"*, *"who r u"*, *"Tum kaun ho"* | Fixed response: *"Main Light AI hoon, jise mere Boss ne banaya hai."* |
| **Exit / Shutdown** | *"exit"*, *"stop"*, *"terminate"*, *"good bye"* | Exact standalone exit commands; shuts down gracefully |

---

## 5. Automated Tests

Run the full automated test suite using `pytest`:
```powershell
& python pytest tests/
```
All **97 tests** pass cleanly with 0 failures across 11 test modules. External actions (PyWhatKit, audio devices, browser execution) are fully mocked during test runs.

---

## 6. Important Notes & Safety Boundaries

- **Browser Reuse**: Brave is launched via its executable CLI. Chromium automatically delegates new URL requests to the running browser process without creating duplicate application windows.
- **WhatsApp Sending Confirmation**: PyWhatKit is only invoked after the user explicitly answers affirmative (`"haan"`, `"yes"`, `"bhejo"`).
- **Authentication**: PyWhatKit relies on WhatsApp Web being logged in. LIGHT AI reminds the user if authentication is needed and never claims a message was delivered merely because PyWhatKit was called.
- **Privacy**: Full phone numbers are masked in all console logs and terminal output (`91******XXXX`).
