<div align="center">
<samp><b>Friday</b></samp>
</div>

---

<samp>**Friday** is a local-first, voice-driven personal assistant that connects an Android phone to a Windows laptop. The phone provides the interface, microphone, speaker, wake-word detection and phone-side controls; the laptop runs the Python Core, speech processing, tools and persistent data.</samp>

> **Project status:** Friday is a working MVP. Commands are handled by a deterministic rule-based router; there is no language model in the current Core. See [docs/RUNNING.md](docs/RUNNING.md) for measured behaviour and known limitations.


---

<div align="center"><samp><b>Features</b></samp></div>

- <samp>**Voice interaction:** Say “Friday” or “Hey Friday”, wait for the acknowledgement, and speak a request. Push-to-talk and typed commands are also supported.</samp>
- <samp>**Phone and laptop tools:** Run supported actions on the device that can perform them.</samp>
- <samp>**Laptop console:** A local browser dashboard at [http://127.0.0.1:8765/](http://127.0.0.1:8765/) mirrors the phone conversation and exposes assistant screens.</samp>
- <samp>**Phone status and controls:** Check battery, RAM, storage and temperature; control supported phone settings and open apps.</samp>
- <samp>**Laptop tools:** Check system status, open apps and folders, inspect processes, and run supported Git, test, build and development workflows.</samp>
- <samp>**Timers, alarms, tasks and memory:** Manage reminders and tasks, create timers and alarms, and store or recall user-provided facts.</samp>
- <samp>**Music controls:** Control the laptop's current media session from the phone. Optional Spotify search and playback integration is available.</samp>
- <samp>**Offline Satellite mode:** When the laptop is unavailable, the phone can handle a limited set of local commands using its wake detector and Android text-to-speech.</samp>
- <samp>**Local-first communication:** USB pairing is supported, as is a laptop-hosted wireless connection using TLS and a paired certificate.</samp>


---

<div align="center"><samp><b>Architecture</b></samp></div>

```text
┌──────────────────────────────┐       USB / local Wi-Fi
│ Android phone — Friday Shell │  ◄──────────────────────────────►
│ Kotlin · UI · mic · wake word│
│ phone actions · offline mode │
└──────────────────────────────┘
                                      ┌─────────────────────────────┐
                                      │ Windows laptop — Friday Core│
                                      │ Python · gateway · router   │
                                      │ speech · tools · SQLite     │
                                      │ browser console · audit log │
                                      └─────────────────────────────┘
```

<samp>The Android Shell is a regular Android application, not a custom ROM. The laptop Core manages assistant memory, tasks and laptop-side tools. The phone handles phone-side actions and local wake-word detection.</samp>


---

<div align="center"><samp><b>Repository layout</b></samp></div>

| Path | Purpose |
|---|---|
| `core/friday_core/` | Python Core: command router, gateway, tools, voice and persistent store |
| `core/config/` | Core, speech, command and wake-word configuration |
| `core/tests/` | Core tests |
| `shell/` | Android application built with Kotlin and Gradle |
| `scripts/` | Windows setup, build, provisioning, startup and diagnostics |
| `bench/` | Speech runtime dependencies and experiments |
| `docs/RUNNING.md` | Setup, daily use, wireless mode and supported commands |
| `docs/UI.md` | User interface and design system |
| `docs/FRIDAY_Technical_Proposal.md` | Architecture and technical rationale |
| `docs/phase0-results.md` | Initial hardware and model measurements |


---

<div align="center"><samp><b>Requirements</b></samp></div>

<samp>The current setup is designed around:</samp>

- <samp>Windows 11 laptop with Python 3.12 for the Core environment.</samp>
- <samp>Android 9 or later; the original target device is a Samsung Galaxy J7 Pro.</samp>
- <samp>Java 17 and Android SDK / Android Studio command-line build tools.</samp>
- <samp>ADB for initial phone installation and provisioning.</samp>
- <samp>Local speech assets and the sherpa-onnx 1.13.8 runtime.</samp>
- <samp>Optional Spotify developer credentials for Spotify Web API search.</samp>

<samp>The scripts and Gradle configuration use local model and tool directories. Review the paths in the setup scripts and Android Gradle configuration and adjust them for your machine. Keep pairing tokens, private keys, API credentials and generated `data/` contents out of version control.</samp>


---

<div align="center"><samp><b>Getting started</b></samp></div>

<samp>The full setup is Windows-specific and includes fetching speech assets, preparing the phone and creating local pairing data. Follow the [running guide](docs/RUNNING.md) for the complete and current procedure.</samp>

1. <samp>Review [docs/RUNNING.md](docs/RUNNING.md), especially **One-time setup** and **Offline wireless**.</samp>
2. <samp>Install the required Python, Java, Android SDK and ADB toolchains.</samp>
3. <samp>Fetch the speech models and Android wake-word runtime using the scripts in `scripts/`.</samp>
4. <samp>Build the Android APK:</samp>

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build-shell.ps1
   ```

5. <samp>Connect the phone over USB and provision the Shell:</samp>

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\provision-phone.ps1 -SetHome
   ```

6. <samp>Start Friday:</samp>

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-friday.ps1
   ```

7. <samp>Open the laptop console at [http://127.0.0.1:8765/](http://127.0.0.1:8765/) and connect the phone.</samp>

<samp>For wireless startup, laptop hotspot setup and re-pairing instructions, see [docs/RUNNING.md](docs/RUNNING.md). The `-SetHome` option sets Friday as the default Home app; it does not enable Device Owner mode.</samp>


---

<div align="center"><samp><b>Example interactions</b></samp></div>

<samp>The current rule-based router supports commands such as:</samp>

- <samp>“Friday, what's my laptop RAM usage?”</samp>
- <samp>“Open Notepad”</samp>
- <samp>“Set a timer for five minutes”</samp>
- <samp>“Remember that my project demo is on Friday”</samp>
- <samp>“What's running?”</samp>
- <samp>“Play Believer on Spotify” (with the optional Spotify integration configured)</samp>

<samp>The supported command set and offline Satellite phrases are documented in [docs/RUNNING.md](docs/RUNNING.md). Requests outside the configured rules are not sent to an LLM; Friday responds that it did not understand the command.</samp>


---

<div align="center"><samp><b>Security and privacy</b></samp></div>

- <samp>Phone and laptop communicate over a local connection.</samp>
- <samp>Wireless mode uses TLS with a paired server certificate and pairing token. USB mode uses a token over the local reverse connection.</samp>
- <samp>Keep generated credentials, certificates, tokens and the `data/` directory private.</samp>
- <samp>Higher-risk operations require explicit confirmation, and tool calls are recorded in an append-only audit table.</samp>
- <samp>Review Windows scripts before running them, particularly scripts that create scheduled tasks, firewall rules or execute system commands.</samp>


---

<div align="center"><samp><b>Current limitations</b></samp></div>

<samp>Friday is an evolving MVP, not a general-purpose autonomous agent or a replacement operating system.</samp>

- <samp>The Core currently uses deterministic command rules; there is no conversational LLM.</samp>
- <samp>Satellite mode supports a fixed phrase list and a limited set of offline actions.</samp>
- <samp>Screen understanding, proactive watchers, full notification management and several privileged OS-style features are not implemented yet.</samp>
- <samp>The app and scripts are tailored to a Windows + Android setup and may need adaptation.</samp>
- <samp>Spotify Web API features require a separately configured developer application and an eligible account.</samp>

<samp>See [docs/RUNNING.md](docs/RUNNING.md) for verified behaviour and [docs/FRIDAY_Technical_Proposal.md](docs/FRIDAY_Technical_Proposal.md) for the broader architecture.</samp>


---

<div align="center"><samp><b>Development</b></samp></div>

<samp>The Python package is `friday_core`. The Android application and its Gradle configuration are under `shell/`. For daily startup, use:</samp>

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-friday.ps1
```

<samp>For test, build and development workflows, use the commands and environment described in [docs/RUNNING.md](docs/RUNNING.md).</samp>


---

<div align="center"><samp><b>Documentation</b></samp></div>

- <samp>[Running Friday](docs/RUNNING.md)</samp>
- <samp>[UI and design system](docs/UI.md)</samp>
- <samp>[Technical proposal](docs/FRIDAY_Technical_Proposal.md)</samp>
- <samp>[Phase 0 measurements](docs/phase0-results.md)</samp>

---

<samp>Built as an experiment in creating a useful, private, local-first personal assistant from a phone and a laptop.</samp>
