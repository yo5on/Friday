# Friday — FROSTI

**FROSTI** is a local-first, voice-driven assistant built around a simple split: an Android phone provides the screen, microphone, speaker and device controls, while a Windows laptop runs the assistant core and heavier speech processing. The project aims to make an older phone feel like a dedicated personal assistant console—without relying on cloud AI.

> **Project status:** Working MVP with a rule-based command router. The repository's running guide documents measured phone workflows and current limitations. Some capabilities in the technical proposal and design documents are future work, not implemented features.

## What it does

- **Voice interaction:** Wake phrase detection on the phone, push-to-talk, speech recognition and spoken responses.
- **Phone + laptop control:** Route supported commands to the device that can perform them.
- **Laptop console:** A browser-based dashboard at `http://127.0.0.1:8765/` mirrors the phone conversation and exposes system information.
- **System tools:** Check resource usage, open applications and folders, inspect running processes, and perform supported Git and project workflows.
- **Timers, tasks and memory:** Create timers, manage a lightweight task list, and remember or recall user-provided facts.
- **Music controls:** Display current laptop media and control supported playback actions; optional Spotify search/play integration is documented separately.
- **Offline fallback:** When the laptop is unavailable, the phone can handle a limited fixed set of Satellite-mode commands using its local wake detector and Android text-to-speech.

The Core enforces confirmation for higher-risk actions. Tool calls are recorded in an append-only audit table.

## Architecture

```text
┌──────────────────────────────┐       LAN / USB / laptop hotspot
│ Android phone — FROSTI Shell │  ◄──────────────────────────────►
│ Kotlin · UI · mic · wake word│
│ phone actions · offline mode │
└──────────────────────────────┘
                                      ┌─────────────────────────────┐
                                      │ Windows laptop — FROSTI Core│
                                      │ Python · gateway · router   │
                                      │ speech · tools · SQLite     │
                                      │ browser console · audit log │
                                      └─────────────────────────────┘
```

The Android Shell is an ordinary Android application (not a custom ROM). The laptop Core is the source of truth for assistant memory and task/timer state. The phone remains responsible for phone-side actions and local wake-word detection.

## Repository layout

| Path | Purpose |
|---|---|
| `core/frosti_core/` | Python Core: command handling, gateway, tools, voice and persistent store |
| `core/config/` | Core and speech configuration, command and wake-word lists |
| `core/tests/` | Core tests |
| `shell/` | Android application built with Kotlin and Gradle |
| `scripts/` | Windows setup, build, provisioning, startup and diagnostics scripts |
| `bench/` | Speech runtime dependencies and experiments |
| `docs/RUNNING.md` | Setup, daily use, wireless mode and supported commands |
| `docs/UI.md` | User interface and design specification |
| `docs/FROSTI_Technical_Proposal.md` | System architecture and technical rationale |
| `docs/phase0-results.md` | Initial hardware and model measurements |

## Requirements

The current setup is designed around:

- Windows 11 laptop with Python 3.12 available for the Core environment.
- Android 9 or later; the original target device is a Samsung Galaxy J7 Pro.
- Android SDK / Android Studio command-line build tools and Java 17 for the Shell build.
- ADB for initial phone installation and provisioning.
- Local speech assets and the sherpa-onnx 1.13.8 runtime.
- Optional Spotify developer credentials for the Spotify Web API integration.

The repository's scripts and Gradle configuration currently reference local model/tool directories such as `D:\\frosti-models` and `D:\\frosti-tools`. Adjust those paths for your machine before building. Do not commit pairing tokens, private keys, API credentials or generated `data/` contents.

## Getting started

The exact setup is Windows-specific and includes downloading speech assets, preparing the phone, and generating local pairing data. Follow the maintained runbook rather than treating these abbreviated commands as a complete installation.

1. Review [docs/RUNNING.md](docs/RUNNING.md), especially the one-time setup and offline wireless sections.
2. Install the required Python, Java, Android and ADB toolchains.
3. Fetch the speech models and Android wake-word runtime using the scripts in `scripts/`.
4. Build the Android APK:
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build-shell.ps1
   ```
5. Connect the phone over USB and provision/install the Shell:
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\provision-phone.ps1 -SetHome
   ```
6. Start the Core:
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-frosti.ps1
   ```
7. Open the laptop console at [http://127.0.0.1:8765/](http://127.0.0.1:8765/) and connect the phone.

For automatic wireless startup and the laptop hotspot workflow, see [docs/RUNNING.md](docs/RUNNING.md). The `-SetHome` option makes the Shell the default Home app; it does not enable Device Owner mode.

## Example interactions

Commands are matched by the current rule-based router. Use direct, supported phrases, for example:

- “Frosti, what's my laptop RAM usage?”
- “Open Notepad”
- “Set a timer for five minutes”
- “Remember that my project demo is on Friday”
- “What's running?”
- “Play Believer on Spotify” (with the optional Spotify integration configured)

The currently supported command set and Satellite-mode phrases are described in [docs/RUNNING.md](docs/RUNNING.md). Requests outside the configured rules are not sent to an LLM; the MVP responds that it did not understand the command.

## Security and privacy notes

- The design is local-first: phone and laptop communicate over a local connection.
- Wireless mode uses TLS with a paired server certificate and a pairing token. USB mode uses a token over the local reverse connection.
- Keep generated credentials, certificates, tokens and the `data/` directory private.
- Higher-risk operations require explicit confirmation, and tool execution is audited.
- The J7 Pro runs an old Android release; use it as a dedicated endpoint and avoid storing sensitive personal accounts on it.
- Review every Windows script before running it, particularly scripts that create scheduled tasks, firewall rules or execute system commands.

## Current limitations

FROSTI is an evolving MVP, not a general-purpose autonomous agent or a replacement operating system.

- The Core currently uses deterministic command rules; there is no conversational LLM in the documented MVP.
- Satellite mode supports only a fixed phrase list and a limited set of offline actions.
- Screen understanding, proactive watchers, full notification management and several privileged OS-style features are listed as future work.
- The app and scripts are tailored to a specific Windows + Android setup; paths and dependencies may need adaptation.
- Spotify Web API features depend on a separately configured developer application and account eligibility.

See [docs/RUNNING.md](docs/RUNNING.md) for verified behaviour and [docs/FROSTI_Technical_Proposal.md](docs/FROSTI_Technical_Proposal.md) for planned architecture.

## Development

The Python package can be launched as a module from the configured Core environment:

```powershell
.venv\Scripts\python.exe -m frosti_core --no-voice
```

Omit `--no-voice` to initialize the configured speech pipeline. The project's startup scripts set up the expected environment and paths; see [docs/RUNNING.md](docs/RUNNING.md).

Android build configuration is in `shell/`. The current Gradle build expects Java 17 and local sherpa-onnx/model assets at the paths configured in `shell/app/build.gradle.kts`.

## Documentation

- [Running FROSTI](docs/RUNNING.md)
- [UI specification](docs/UI.md)
- [Technical proposal](docs/FROSTI_Technical_Proposal.md)
- [Phase 0 measurements](docs/phase0-results.md)

---

Made as an experiment in building a useful, private, local-first personal assistant from a phone and a laptop.
