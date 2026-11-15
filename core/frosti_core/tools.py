"""Tool registry: risk tiers enforced in code, laptop implementations.

Phone tools have no laptop implementation (run=None): the gateway forwards them to the Shell app.
Every run() returns (spoken_text, detail_text), optionally plus a media preview dict (title, artist, album, art, app).
"""
import asyncio, base64, ctypes, difflib, json, os, re, shutil, subprocess, threading, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
import psutil
from . import CONFIG, DATA, ROOT

PROJECTS = {k: dict(v) for k, v in CONFIG.get("projects", {}).items()}
NO_WINDOW = subprocess.CREATE_NO_WINDOW

@dataclass
class Tool:
    name: str
    desc: str
    props: dict
    required: list
    tier: int | Callable          # 0 read, 1 reversible, 2 consequential (confirm), 3 destructive (confirm + exact action)
    run: Callable | None = None   # None -> executed on the phone
    phone_if: Callable | None = None  # args -> True when this call must run on the phone

    def tier_for(self, args):
        return self.tier(args) if callable(self.tier) else self.tier

    def on_phone(self, args):
        return self.run is None or bool(self.phone_if and self.phone_if(args))

    def schema(self):
        return {"type": "function", "function": {"name": self.name, "description": self.desc,
                "parameters": {"type": "object", "properties": self.props, "required": self.required}}}

def sh(cmd, cwd=None, timeout=60):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW,
                       encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout + p.stderr).strip()

def project(name):
    n = (name or "").lower().strip()
    for k, v in PROJECTS.items():
        if k in n or n in k:
            return k, Path(v["path"])
    raise ValueError(f"'{name}' isn't in my projects list. Known: {', '.join(PROJECTS) or 'none'}.")

# ---------- laptop implementations ----------
SAFE_NAME = re.compile(r"^[\w .+-]{1,40}$")
APP_ALIASES = {"vs code": "code", "vscode": "code", "visual studio code": "code", "file explorer": "explorer",
               "files": "explorer", "terminal": "wt", "browser": "msedge", "edge": "msedge", "calculator": "calc"}

START_APPS_PS = r"""$s = New-Object -ComObject WScript.Shell
@{apps = @(Get-StartApps | Select-Object Name, AppID)
  lnks = @(Get-ChildItem "$env:ProgramData\Microsoft\Windows\Start Menu", "$env:APPDATA\Microsoft\Windows\Start Menu" -Recurse -Filter *.lnk |
           ForEach-Object { @{n = $_.BaseName; p = $_.FullName; t = $s.CreateShortcut($_.FullName).TargetPath} })} | ConvertTo-Json -Compress -Depth 3"""
_apps = {"t": 0, "list": []}

def start_apps():
    """Start-menu apps as [{name, id (shell:AppsFolder AppID), lnk, exe}], cached for 10 minutes."""
    if time.time() - _apps["t"] > 600:
        rc, out = sh(["powershell", "-NoProfile", "-Command", START_APPS_PS], timeout=30)
        try:
            data = json.loads(out) if rc == 0 else {}
        except json.JSONDecodeError:
            data = {}
        lnks = {l["n"].lower(): l for l in data.get("lnks") or []}
        apps = [{"name": a["Name"], "id": a["AppID"]} for a in data.get("apps") or []]
        known = {a["name"].lower() for a in apps}
        apps += [{"name": l["n"], "id": None} for k, l in lnks.items() if k not in known]
        for a in apps:
            l = lnks.get(a["name"].lower(), {})
            exe = l.get("t") or (a["id"] if (a["id"] or "").lower().endswith(".exe") else "")
            a.update(lnk=l.get("p"), exe=exe if exe.lower().endswith(".exe") else "")
        _apps.update(t=time.time(), list=[a for a in apps if "uninstall" not in a["name"].lower()])
    return _apps["list"]

def find_app(name, apps):
    """Fuzzy match a spoken name to a Start-menu entry: exact, then whole words (shortest label), then close spelling."""
    n = name.lower().strip()
    by = {a["name"].lower(): a for a in apps}
    if n in by:
        return by[n]
    words = sorted((k for k in by if re.search(rf"\b{re.escape(n)}\b", k)), key=len)
    if words:
        return by[words[0]]
    close = difflib.get_close_matches(n, by, n=1, cutoff=0.8)
    return by[close[0]] if close else None

def open_app(name, device="laptop"):
    raw = name.strip()
    name = APP_ALIASES.get(raw.lower(), raw)
    if not SAFE_NAME.match(raw) or not SAFE_NAME.match(name):  # trust boundary: the name ends up in a shell 'start'
        return "That app name looks unsafe, so I didn't run it.", name
    app = find_app(raw, start_apps()) or find_app(name, start_apps())
    if app:
        if app["lnk"]:
            os.startfile(app["lnk"])
        else:
            subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app['id']}"])
        return f"Opening {app['name']}.", app["lnk"] or app["id"]
    # PATH and App Paths (notepad, wt, msedge, code); no captured pipes: the app would inherit them and we'd wait until it closes
    rc = subprocess.run(["cmd", "/c", "start", "", name], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, creationflags=NO_WINDOW, timeout=30).returncode
    return (f"Opening {name}." if rc == 0 else f"I couldn't find {name} on the laptop."), ""

def get_status(metric, device="laptop"):
    if metric == "battery":
        b = psutil.sensors_battery()
        if not b:
            return "The laptop has no battery reading.", ""
        return f"Laptop battery is at {b.percent:.0f} percent{', charging' if b.power_plugged else ''}.", ""
    if metric == "ram":
        m = psutil.virtual_memory()
        return f"Laptop memory is {m.percent:.0f} percent used, {m.available / 2**30:.1f} gigabytes free.", ""
    if metric == "cpu":
        return f"Laptop CPU is at {psutil.cpu_percent(0.5):.0f} percent.", ""
    if metric == "storage":
        parts = [(p.device[:2], psutil.disk_usage(p.mountpoint)) for p in psutil.disk_partitions() if "fixed" in p.opts]
        detail = "\n".join(f"{d} {u.free / 2**30:.0f} GB free of {u.total / 2**30:.0f} GB" for d, u in parts)
        low = min(parts, key=lambda x: x[1].free)
        return f"Lowest free space is drive {low[0][0]} with {low[1].free / 2**30:.0f} gigabytes.", detail
    if metric == "processes":
        top = top_processes()
        spoken = ", ".join(f"{p['name'].removesuffix('.exe')} {p['cpu']:.0f} percent" for p in top[:3])
        return f"Busiest on the laptop: {spoken}.", "\n".join(f"{p['name']}  CPU {p['cpu']}%  RAM {p['ram'] / 2**20:.0f} MB" for p in top)
    if metric == "temperature":
        # shortcut: Windows exposes CPU temperature only to admin (WMI thermal zone); report load instead until a sensor helper exists
        return f"I can't read the laptop's temperature without admin rights. CPU load is {psutil.cpu_percent(0.5):.0f} percent.", ""
    return f"I don't know the metric {metric}.", ""

def top_processes(n=5):
    """Busiest programs, same-name processes summed (Chrome's many tabs = one row). CPU is % of the whole machine."""
    cores, by = psutil.cpu_count() or 1, {}
    for p in psutil.process_iter(["name", "cpu_percent", "memory_info"]):  # psutil caches Process objects, so cpu_percent is since the last call
        name, mem = p.info["name"], p.info["memory_info"]
        if not name or not mem or name == "System Idle Process":
            continue
        c, r = by.get(name, (0.0, 0))
        by[name] = (c + (p.info["cpu_percent"] or 0) / cores, r + mem.rss)
    top = sorted(by.items(), key=lambda kv: kv[1], reverse=True)[:n]
    return [dict(name=k, cpu=round(c, 1), ram=r) for k, (c, r) in top]

_top = dict(t=0.0, list=[], busy=False)
def top_processes_cached():
    """For the dashboards: a full scan costs ~0.3 s, so it runs off the event loop, at most every 5 s."""
    if not _top["busy"] and time.time() - _top["t"] > 5:
        _top["busy"] = True
        def scan():
            try:
                _top["list"] = top_processes(12)  # the Processes screen lists more than get_status speaks
            finally:
                _top.update(t=time.time(), busy=False)
        threading.Thread(target=scan, daemon=True).start()
    return _top["list"]

def open_vscode(path):
    try:
        path = str(project(path)[1])
    except ValueError:
        pass
    if not Path(path).exists():
        return f"I can't find {path}.", ""
    code = shutil.which("code") or shutil.which("code.cmd")
    if not code:
        return "VS Code's code command isn't on the PATH.", ""
    subprocess.Popen([code, path], creationflags=NO_WINDOW)
    return f"Opening {Path(path).name} in VS Code.", path

def git(project_name, action, message=None, branch=None):
    p = Path(project_name or "")
    # a folder picked in the Laptop panel; tiers and confirmation are the same as for a configured project
    name, path = (p.name or str(p), p) if p.is_absolute() and p.is_dir() else project(project_name)
    cmds = {"status": ["git", "status", "-sb"], "log": ["git", "log", "--oneline", "-5"], "diff": ["git", "diff", "--stat"],
            "pull": ["git", "pull", "--ff-only"], "push": ["git", "push"], "fetch": ["git", "fetch", "--all", "--prune"]}
    if action == "github":
        return github_status(name, path)
    if action == "switch":
        if not branch or branch.startswith("-"):
            return "Which branch?", ""
        rc, out = sh(["git", "switch", branch], path, timeout=60)
    elif action == "commit":
        if not message:
            return "What should the commit message be?", ""
        sh(["git", "add", "-A"], path)
        rc, out = sh(["git", "commit", "-m", message], path)
    elif action in cmds:
        rc, out = sh(cmds[action], path, timeout=120)
    else:
        return f"I can't do git {action}.", ""
    if rc != 0:
        return f"git {action} failed for {name}.", out
    lines = out.splitlines()
    if action == "status":
        changed = len(lines) - 1
        spoken = f"{name} is on {lines[0][3:].split('...')[0]}, " + (f"{changed} changed files." if changed else "clean.")
    elif action == "log":
        spoken = f"Latest in {name}: " + "; ".join(l.split(" ", 1)[1] for l in lines[:3]) + "."
    elif action == "diff":
        spoken = lines[-1] if lines else "No uncommitted changes."
    elif action == "switch":
        spoken = f"{name} is now on {branch}."
    else:
        spoken = f"git {action} done for {name}."
    return spoken, out

_repos = {"t": 0, "list": []}

def git_repos():
    """Configured projects, then git folders one level under each fixed drive and the home folders (cached 5 min)."""
    if time.time() - _repos["t"] > 300:
        roots = [Path(d.mountpoint) for d in psutil.disk_partitions() if "fixed" in d.opts]
        roots += [Path.home() / s for s in ("", "Documents", "Desktop", "source/repos")]
        found = {str(Path(v["path"]).resolve()).lower(): dict(name=k, path=str(Path(v["path"]))) for k, v in PROJECTS.items()}
        for r in roots:
            try:
                for d in r.iterdir():
                    if (d / ".git").exists():
                        found.setdefault(str(d.resolve()).lower(), dict(name=d.name, path=str(d)))
            except OSError:
                continue  # locked drive or missing folder
        _repos.update(t=time.time(), list=list(found.values()))
    return _repos["list"]

def list_dirs(path):
    """Subfolders of `path` for the Laptop panel's folder browser: [{name, git}], hidden and system ones left out."""
    p = Path(path)
    if not p.is_absolute() or not p.is_dir():
        raise OSError(f"not a folder: {path}")
    out = []
    for d in p.iterdir():
        try:
            if d.is_dir() and not d.name.startswith((".", "$")) and d.name not in ("System Volume Information", "node_modules"):
                out.append(dict(name=d.name, git=(d / ".git").exists()))
        except OSError:
            continue  # no access
    return sorted(out, key=lambda d: d["name"].lower())[:300]

def browse_start():
    """Where the folder browser opens: the first project's drive (E:\\ here), else the home folder."""
    for v in PROJECTS.values():
        return Path(v["path"]).anchor or str(Path.home())
    return str(Path.home())

def repo_info(path):
    """What the Laptop panel's git view shows: branch, ahead/behind, changed files, local branches and a commit graph."""
    p = Path(path)
    rc, out = sh(["git", "status", "--porcelain=v1", "-b"], p, timeout=20)
    if rc != 0:
        raise OSError(out.splitlines()[0] if out else "not a git folder")
    head, *changes = out.splitlines()
    m = re.match(r"## (?:No commits yet on )?(\S+?)(?:\.\.\.(\S+))?(?: \[(.*)\])?$", head)
    _, branches = sh(["git", "branch", "--format=%(refname:short)"], p, timeout=20)
    track = (m[3] if m else None) or ""
    ahead, behind = (int(x[1]) if (x := re.search(rf"{w} (\d+)", track)) else 0 for w in ("ahead", "behind"))
    return dict(path=str(p), name=p.name or str(p), branch=m[1] if m else head[3:], upstream=(m[2] if m else None) or "",
                ahead=ahead, behind=behind, gone="gone" in track, changes=changes[:50], changed=len(changes),
                branches=branches.splitlines()[:50], graph=commit_graph(p))

def commit_graph(path, n=40):
    """The last `n` commits of all branches laid out in lanes, ready to draw row by row:
    lane = the dot's column; up = lanes whose line runs from the row's top into the dot; down = lanes the dot's lines
    run to at the row's bottom (its parents); pass = lanes that run straight through. Lanes keep their column."""
    rc, out = sh(["git", "log", "--all", "--topo-order", "-n", str(n), "--format=%H%x1f%P%x1f%D%x1f%s%x1f%cr"], path, timeout=20)
    if rc != 0:
        return []
    lanes, rows = [], []
    for line in out.splitlines():
        sha, parents, refs, subject, when = (line.split("\x1f") + [""] * 5)[:5]
        parents = parents.split()
        up = [i for i, v in enumerate(lanes) if v == sha]
        lane = up[0] if up else (lanes.index(None) if None in lanes else len(lanes))
        if lane == len(lanes):
            lanes.append(None)
        through = [i for i, v in enumerate(lanes) if v is not None and v != sha]
        for i in up:
            lanes[i] = None
        down = []
        for k, par in enumerate(parents):
            if k == 0:
                j = lane
            elif par in lanes:
                j = lanes.index(par)
            else:
                j = next((i for i, v in enumerate(lanes) if v is None and i != lane), len(lanes))
                if j == len(lanes):
                    lanes.append(None)
            lanes[j] = par
            down.append(j)
        while lanes and lanes[-1] is None:
            lanes.pop()
        rows.append(dict(sha=sha[:7], subject=subject, when=when, lane=lane, up=up, down=down, pass_=through,
                         refs=[r.replace("HEAD -> ", "") for r in refs.split(", ") if r and r != "origin/HEAD"],
                         head="HEAD ->" in refs or refs == "HEAD"))
    return rows

def github_status(name, path):
    """Branch, local changes and ahead/behind from git; open PRs and the latest CI run from the gh CLI."""
    rc, out = sh(["git", "status", "-sb"], path)
    if rc != 0:
        return f"git status failed for {name}.", out
    head, *changed = out.splitlines()
    m = re.match(r"## (\S+?)(?:\.\.\.\S+)?(?: \[(.*)\])?$", head)
    spoken = f"{name} is on {m[1] if m else head[3:]}, " + (f"{len(changed)} changed files" if changed else "clean")
    spoken += f", {m[2]}." if m and m[2] else "."
    if not shutil.which("gh"):
        return spoken + " Install the GitHub CLI for pull requests and CI.", out
    rc1, prs = sh(["gh", "pr", "list", "--json", "number,title"], path, timeout=20)
    rc2, runs = sh(["gh", "run", "list", "-L", "1", "--json", "workflowName,status,conclusion,headBranch"], path, timeout=20)
    if rc1 != 0:
        return spoken + " I couldn't reach GitHub.", out + "\n" + prs
    prs, runs = json.loads(prs or "[]"), (json.loads(runs or "[]") if rc2 == 0 else [])
    spoken += f" {len(prs) or 'No'} open pull request{'' if len(prs) == 1 else 's'}."
    if runs:
        r = runs[0]
        spoken += f" Last CI run, {r['workflowName']} on {r['headBranch']}: {r['conclusion'] or r['status'].replace('_', ' ')}."
    return spoken, "\n".join([out] + [f"#{p['number']} {p['title']}" for p in prs])

def run_project(project_name, task):
    name, path = project(project_name)
    cmd = PROJECTS[name].get(task)
    if not cmd:
        return f"{name} has no {task} command configured.", ""
    if task == "dev":  # long-running: own console window
        subprocess.Popen(cmd, cwd=path, shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
        return f"Started the {name} dev server.", cmd
    t = time.time()
    rc, out = sh(cmd, path, timeout=900)
    tail = "\n".join(out.splitlines()[-15:])
    return (f"{name} {task} {'passed' if rc == 0 else 'failed'} in {time.time() - t:.0f} seconds."), tail

def run_powershell(command):
    rc, out = sh(["powershell", "-NoProfile", "-Command", command], timeout=120)
    first = out.splitlines()[0][:120] if out else ""
    return (f"Done. {first}" if rc == 0 else f"That failed. {first}"), out

PROTECTED = {"system", "csrss.exe", "wininit.exe", "winlogon.exe", "lsass.exe", "services.exe", "smss.exe",
             "svchost.exe", "dwm.exe", "explorer.exe", "msmpeng.exe", "python.exe"}

def process_for(name, running, apps):
    """Spoken app name -> exe names to close: the exe itself, the exe behind its Start-menu shortcut,
    or running exes whose name contains it ("word" -> winword.exe). Returns a list: several means ambiguous."""
    n = APP_ALIASES.get(name.lower().strip(), name.lower().strip()).removesuffix(".exe")
    if n + ".exe" in running:
        return [n + ".exe"]
    app = find_app(n, apps)
    exe = Path(app["exe"]).name.lower() if app and app["exe"] else ""
    if exe and exe in running:  # nameless (access-denied) processes show up as "" too
        return [exe]
    if len(n) < 3:
        return []
    return sorted({p for p in running if n.replace(" ", "") in p.removesuffix(".exe")})

def kill_target(name):
    """(matches, exe) for a kill request; exe is None when the name is ambiguous."""
    running = {(p.info["name"] or "").lower() for p in psutil.process_iter(["name"])}
    found = process_for(name, running, start_apps())
    if len(found) > 1:
        return found, None
    return found, found[0] if found else name.lower().strip().removesuffix(".exe") + ".exe"

def kill_preview(name):
    """What the confirmation should say, e.g. 'Close 11 chatgpt.exe processes'."""
    _, n = kill_target(name)
    count = sum((p.info["name"] or "").lower() == n for p in psutil.process_iter(["name"])) if n else 0
    if not count or n == "explorer.exe" or n in PROTECTED:
        return f"Kill process {name}"
    return f"Close {count} {n} process{'es' if count != 1 else ''}"

def kill_process(name):
    found, n = kill_target(name)
    if n is None:
        return f"{name} could be {', '.join(found)}. Which one?", ""
    if n == "explorer.exe":  # the same process draws the taskbar and desktop, so close only its folder windows
        sh(["powershell", "-NoProfile", "-Command",
            "(New-Object -ComObject Shell.Application).Windows() | ForEach-Object { $_.Quit() }"], timeout=20)
        return "Closed the File Explorer windows.", ""
    if n in PROTECTED:
        return f"{n} is protected, so I won't kill it.", ""
    procs = [p for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == n]
    for p in procs:
        try:
            p.kill()
        except psutil.Error:
            pass
    # Chromium/Electron apps (ChatGPT, Chrome, Discord) run one process per tab, GPU, helper: one app, many processes
    return (f"Closed {n.removesuffix('.exe')}{f' ({len(procs)} processes)' if len(procs) > 1 else ''}." if procs else f"No {n} is running."), ""

MEDIA_KEYS = {"play": 0xB3, "pause": 0xB3, "next": 0xB0, "previous": 0xB1}  # play and pause share the toggle key

def media_control(action, device="laptop"):
    vk = MEDIA_KEYS.get(action)
    if vk is None:
        return f"I can't do {action} on the music.", ""
    for flags in (0, 2):  # key down, key up
        ctypes.windll.user32.keybd_event(vk, 0, flags, 0)
    return {"next": "Next track.", "previous": "Previous track."}.get(action, "Okay."), ""

class _GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]

def _guid(s):
    g = _GUID(); ctypes.windll.ole32.CLSIDFromString(s, ctypes.byref(g)); return g

def _call(obj, slot, *args):
    """Call COM method number `slot` of interface pointer `obj` (raises OSError on a failed HRESULT)."""
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    types = (type(a) if hasattr(type(a), "from_param") else ctypes.c_void_p for a in args)  # byref() args are pointers
    return ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *types)(vtbl[slot])(obj, *args)

# One PowerShell kept running for brightness: starting one per change took ~1 s, so a dragged slider lagged.
# It reads "get" or a level per line and answers with the level (or "ERR ...").
BRIGHT_PS = r"""$ErrorActionPreference = 'Stop'
while ($null -ne ($l = [Console]::In.ReadLine())) {
  try {
    if ($l -eq 'get') { $v = (Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness | Select-Object -First 1).CurrentBrightness }
    else { if (-not $m) { $m = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | Select-Object -First 1 }
           $null = Invoke-CimMethod -InputObject $m -MethodName WmiSetBrightness -Arguments @{Timeout = [uint32]0; Brightness = [byte]$l}; $v = $l }
    [Console]::Out.WriteLine("$v")
  } catch { [Console]::Out.WriteLine("ERR $($_.Exception.Message)") }
  [Console]::Out.Flush()
}"""
_bright = {"proc": None, "lock": threading.Lock(), "want": None}

def _bright_ask(line):
    p = _bright["proc"]
    if p is None or p.poll() is not None:
        p = _bright["proc"] = subprocess.Popen(["powershell", "-NoProfile", "-Command", BRIGHT_PS], stdin=subprocess.PIPE,
                                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1,
                                               creationflags=NO_WINDOW)
    p.stdin.write(line + "\n"); p.stdin.flush()
    out = p.stdout.readline().strip()
    if not out.isdigit():
        raise OSError(f"brightness: {out[:200] or 'no answer'}")
    return int(out)

def laptop_brightness(level=None):
    """Set the built-in screen to `level` 0-100 (None just reads it) through WMI; returns the level, or None when a set
    already running will apply this newer level (so a dragged slider never queues up). Raises OSError where unsupported."""
    if level is None:
        with _bright["lock"]:
            return _bright_ask("get")
    _bright["want"] = max(0, min(100, int(level)))
    cur = None
    while _bright["want"] is not None:  # re-check after release: a level that arrived just then still gets applied
        if not _bright["lock"].acquire(blocking=False):
            return cur
        try:
            while (lv := _bright["want"]) is not None:
                _bright["want"] = None
                cur = _bright_ask(str(lv))
        finally:
            _bright["lock"].release()
    return cur

def set_laptop_brightness(level):
    try:
        return f"Laptop brightness {laptop_brightness(level)}%.", ""
    except OSError as e:
        return "I can't change this laptop's brightness.", str(e)

def laptop_volume(step=0, level=None):
    """Move the laptop's master volume by `step` x 5 %, or set it to `level` 0-100 (neither just reads it), unmuting;
    returns the level 0-100.
    Plain ctypes over Windows Core Audio (IMMDeviceEnumerator -> IMMDevice -> IAudioEndpointVolume): no extra dependency."""
    ole, P = ctypes.windll.ole32, ctypes.c_void_p
    ole.CoInitializeEx(None, 0)  # multithreaded: a plain CoInitialize made the event loop single-threaded and hung WinRT cover reads
    enum, dev, vol = P(), P(), P()
    try:
        hr = ole.CoCreateInstance(ctypes.byref(_guid("{BCDE0395-E52F-467C-8E3D-C4579291692E}")), None, 1,
                                  ctypes.byref(_guid("{A95664D2-9614-4F35-A746-DE8DB63617E6}")), ctypes.byref(enum))
        if hr < 0:
            raise OSError(hr, "MMDeviceEnumerator")
        _call(enum, 4, ctypes.c_int(0), ctypes.c_int(1), ctypes.byref(dev))  # default render endpoint, multimedia role
        _call(dev, 3, ctypes.byref(_guid("{5CDF2C82-841E-4546-9722-0CF74078229A}")), ctypes.c_ulong(23), P(), ctypes.byref(vol))
        cur = ctypes.c_float(); _call(vol, 9, ctypes.byref(cur))  # GetMasterVolumeLevelScalar
        if not step and level is None:
            return round(cur.value * 100)
        new = min(100, max(0, level)) / 100 if level is not None else min(20, max(0, round(cur.value * 20) + step)) / 20
        _call(vol, 7, ctypes.c_float(new), P())  # SetMasterVolumeLevelScalar
        _call(vol, 14, ctypes.c_int(0), P())     # SetMute(False)
        return round(new * 100)
    finally:
        for p in (vol, dev, enum):
            if p:
                ctypes.WINFUNCTYPE(ctypes.c_ulong, P)(ctypes.cast(p, ctypes.POINTER(ctypes.POINTER(P)))[0][2])(p)  # Release

_spotify = {"token": "", "until": 0.0}

def _fetch(url, data=None, headers=None, timeout=8):
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers or {}), timeout=timeout) as r:
        return r.read()

def spotify_track(query):
    """Top Spotify track for a query, or None if no developer keys are set up (data/spotify.json)."""
    found = spotify_search(query, 1)
    return found[0] if found else None

def spotify_search(query, limit):
    """Spotify tracks for a query, or None if no developer keys are set up (data/spotify.json)."""
    keys = DATA / "spotify.json"
    if not keys.exists():
        return None
    if _spotify["until"] < time.time():
        k = json.loads(keys.read_text(encoding="utf-8-sig"))
        basic = base64.b64encode(f"{k['client_id']}:{k['client_secret']}".encode()).decode()
        t = json.loads(_fetch("https://accounts.spotify.com/api/token", b"grant_type=client_credentials",
                              {"Authorization": "Basic " + basic, "Content-Type": "application/x-www-form-urlencoded"}))
        _spotify.update(token=t["access_token"], until=time.time() + t["expires_in"] - 60)
    found = json.loads(_fetch(f"https://api.spotify.com/v1/search?type=track&limit={limit}&q=" + urllib.parse.quote(query),
                              headers={"Authorization": "Bearer " + _spotify["token"]}))
    return found["tracks"]["items"]

def _art(images, i):
    """Cover as a data: URI (the phone on the offline hotspot can't reach Spotify's image server); images go largest first."""
    try:
        # 4 s: a cover is optional and shouldn't hold the song list for the full 8 s, but a cold connect to the
        # image server took 2.1 s here, and at 2 s every cover in the list went missing
        return "data:image/jpeg;base64," + base64.b64encode(_fetch(images[min(i, len(images) - 1)]["url"], timeout=4)).decode() if images else None
    except OSError:
        return None

def search_music(query):
    """Up to 8 songs, each with a play button in the chat (the button sends {"type":"play_track","uri"}).
    With Spotify keys (Web API needs Premium) the button plays the exact track; without them the list comes from
    Apple's free iTunes search and the button opens Spotify's search for that song."""
    q = re.sub(r"\s+by\s+", " ", query.strip())
    why = ""
    try:
        found = spotify_search(q, 8)
    except (OSError, ValueError, KeyError) as e:
        found, why = None, f"Spotify lookup failed ({e!r}); used iTunes search instead."
    with ThreadPoolExecutor(8) as ex:  # smallest cover for each row, fetched side by side
        if found is not None:
            arts = list(ex.map(lambda t: _art(t["album"]["images"], 9), found))
            tracks = [dict(title=t["name"], artist=", ".join(a["name"] for a in t["artists"]), album=t["album"]["name"], art=art, uri=t["uri"])
                      for t, art in zip(found, arts)]
        else:
            try:
                found = json.loads(_fetch("https://itunes.apple.com/search?entity=song&limit=8&term=" + urllib.parse.quote(q)))["results"]
            except (OSError, ValueError, KeyError) as e:  # offline: Spotify's own search page is all that's left
                os.startfile(f"spotify:search:{urllib.parse.quote(query.strip())}")
                return f"Searching Spotify for {query}.", f"Song search failed ({e!r})."
            arts = list(ex.map(lambda r: _art([{"url": r["artworkUrl60"]}] if r.get("artworkUrl60") else [], 0), found))
            tracks = [dict(title=r["trackName"], artist=r["artistName"], album=r.get("collectionName", ""), art=art,
                           uri="spotify:search:" + urllib.parse.quote(f"{r['trackName']} {re.split(r' *[,&] *', r['artistName'])[0]}", safe=""))
                      for r, art in zip(found, arts)]
    if not tracks:
        return f"I found no songs for {query}.", why
    return f"Here's what I found for {query}.", why, {"tracks": tracks}

def play_music(query, device="laptop"):
    q = urllib.parse.quote(query.strip())
    if any(a["name"].lower() == "spotify" for a in start_apps()):
        try:
            track = spotify_track(re.sub(r"\s+by\s+", " ", query.strip()))
            why = "Add Spotify keys to data/spotify.json to play songs directly."
        except (OSError, ValueError, KeyError) as e:  # offline, Spotify down, or a broken keys file: search instead
            track, why = None, f"Spotify lookup failed ({e!r}); searched instead."
        if not track:
            os.startfile(f"spotify:search:{q}")
            return f"Searching Spotify for {query}.", why
        os.startfile(track["uri"])  # the desktop app starts playing a track link it is given
        artist = ", ".join(a["name"] for a in track["artists"])
        art = _art(track["album"]["images"], 1)  # ~300 px is enough for the card
        media = dict(title=track["name"], artist=artist, album=track["album"]["name"], art=art, app="Spotify")
        return f"Playing {track['name']} by {artist}.", "", media
    os.startfile(f"https://music.youtube.com/search?q={q}")
    return f"Opening YouTube Music for {query}.", ""

_np = {"key": None, "art": None, "stale": None, "since": 0.0}

async def now_playing():
    """What the laptop is playing right now (any app, via Windows media sessions), as a media dict plus "playing";
    None when nothing is. Needs the winrt-Windows.Media.Control packages."""
    try:
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager
        from winrt.windows.storage.streams import Buffer, InputStreamOptions
    except ImportError:
        return None
    s = (await Manager.request_async()).get_current_session()
    if not s:
        return None
    p = await s.try_get_media_properties_async()
    if not p.title:
        return None
    app = s.source_app_user_model_id.rsplit("\\", 1)[-1].split("!")[0].removesuffix(".exe")
    app = "Spotify" if "spotify" in app.lower() else app
    key = (p.title, p.artist, app)
    if key != _np["key"]:
        # right after Next, Windows reports the new title with the old track's cover for a moment: don't keep that one
        _np.update(key=key, art=None, stale=_np["art"], since=time.monotonic())
    # cover in the background, retried each poll until it lands: a cover read can hang for good (seen with Spotify
    # right at a track change), and awaiting it here froze the phone on the old track
    cover = _np.get("cover")
    if p.thumbnail and _np["art"] is None and (cover is None or cover.done()):
        async def read(thumb):
            stream = await thumb.open_read_async()
            buf = Buffer(stream.size)
            await stream.read_async(buf, buf.capacity, InputStreamOptions.READ_AHEAD)
            return f"data:{stream.content_type or 'image/png'};base64," + base64.b64encode(bytes(buf)).decode()
        async def fetch(thumb):
            task = asyncio.ensure_future(read(thumb))
            done, _ = await asyncio.wait({task}, timeout=3)  # not wait_for: a hung WinRT call ignores cancel
            if not done:
                task.add_done_callback(lambda t: t.cancelled() or t.exception())
                print(f"[media] cover read stuck for {key[0]}; retrying", flush=True)
            elif not task.exception() and _np["key"] == key:
                art = task.result()
                if art != _np["stale"] or time.monotonic() - _np["since"] > 6:  # after 6 s it's a same-album cover
                    _np["art"] = art
        _np["cover"] = asyncio.ensure_future(fetch(p.thumbnail))  # held so it isn't garbage-collected mid-read
    info = s.get_playback_info()
    playing = info.playback_status == 4  # GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING
    tl = s.get_timeline_properties()
    length = (tl.end_time - tl.start_time).total_seconds()
    position = tl.position.total_seconds()
    if playing:  # apps report the position only now and then; add the time since that report
        seen = tl.last_updated_time
        position += (datetime.now(timezone.utc) - (seen if seen.tzinfo else seen.replace(tzinfo=timezone.utc))).total_seconds()
    shuffle = info.is_shuffle_active if info.controls.is_shuffle_enabled else None  # None: the app can't shuffle
    return dict(title=p.title, artist=p.artist, album=p.album_title, art=_np["art"], app=app, playing=playing,
                position=round(min(max(position, 0), length), 1) if length > 0 else None,
                length=round(length, 1) if length > 0 else None, shuffle=shuffle)

async def media_session(action):
    """Desk panel buttons: play/pause, next, previous or shuffle on the laptop's current media session (no reply)."""
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager
    s = (await Manager.request_async()).get_current_session()
    if not s:
        return
    if action == "shuffle":
        await s.try_change_shuffle_active_async(not s.get_playback_info().is_shuffle_active)
    else:
        await {"play": s.try_play_async, "pause": s.try_pause_async, "next": s.try_skip_next_async,
               "previous": s.try_skip_previous_async}[action]()

ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
_awake = {"stop": None}

def _hold_awake(stop, process=None, idle_cpu=10, idle_minutes=5):
    """Block automatic sleep until cancelled, the selected process exits, or generic work goes idle."""
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    quiet = 0
    try:
        while not stop.wait(3 if process else 30):
            if process:
                if not process.is_running():
                    break
            else:
                quiet = quiet + 1 if psutil.cpu_percent(1) < idle_cpu else 0
                if quiet >= idle_minutes * 2:
                    break
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)  # sleep allowed again
        if _awake["stop"] is stop:
            _awake["stop"] = None

def power(action, minutes=0, process=""):
    if action == "keep_awake":
        if _awake["stop"]:
            return "The laptop is already staying awake. Say 'let the laptop sleep' before choosing another process.", ""
        target = None
        if process:
            if not isinstance(process, str) or not SAFE_NAME.fullmatch(process):
                return "Give me a running process name or PID.", ""
            if process.isdecimal():
                try:
                    target = psutil.Process(int(process))
                    target.name()
                except (psutil.Error, ValueError, OverflowError):
                    return f"I can't monitor process {process}. Check that it is running and accessible.", ""
            else:
                procs = list(psutil.process_iter(["name"]))
                running = {(p.info["name"] or "").lower() for p in procs}
                found = process_for(process, running, []) or process_for(process, running, start_apps())
                if len(found) > 1:
                    return f"{process} could be {', '.join(found)}. Give me the exact process name or PID.", ""
                matches = [p for p in procs if (p.info["name"] or "").lower() in found]
                if not matches:
                    return f"No {process} process is running.", ""
                if len(matches) > 1:
                    return f"Several {found[0]} processes are running. Give me a PID: {', '.join(str(p.pid) for p in matches)}.", ""
                target = matches[0]
        _awake["stop"] = threading.Event()
        threading.Thread(target=_hold_awake, args=(_awake["stop"], target), daemon=True).start()
        if target:
            return f"The laptop will stay awake until process {target.pid} exits.", f"Watching {process}; sleep allowed again within 3 seconds of exit."
        # shortcut: "work finished" = CPU under 10% for 5 minutes; closing the lid still sleeps (Windows lid setting)
        return "Okay, the laptop stays awake until the CPU has been quiet for five minutes.", "Name a process to track its actual exit instead."
    if action == "sleep":
        # 2 s head start so the reply reaches the phone before the network drops
        threading.Timer(2, ctypes.windll.powrprof.SetSuspendState, (False, False, False)).start()
        return "Putting the laptop to sleep.", ""
    if action == "allow_sleep":
        if _awake["stop"]:
            _awake["stop"].set()
        return "Okay, the laptop can sleep again.", ""
    if action == "shutdown":
        minutes = max(0, int(minutes or 0))
        rc, out = sh(["shutdown", "/s", "/t", str(minutes * 60)])
        if rc != 0:
            return "I couldn't schedule the shutdown.", out
        return (f"Shutting down in {minutes} minute{'s' if minutes != 1 else ''}." if minutes else "Shutting down now."), out
    if action == "cancel_shutdown":
        rc, out = sh(["shutdown", "/a"])
        return ("Shutdown cancelled." if rc == 0 else "There was no shutdown scheduled."), out
    return f"I can't do {action}.", ""

def describe_screen(device="laptop"):
    # shortcut: screen understanding is Phase 7 (Windows OCR + UIA, phone accessibility tree); upgrade there
    return "I can't see screens yet. That arrives with the vision update.", ""

# set_timer / remember / recall / tasks need the running Brain, so it binds them (see brain.py).

S, I = {"type": "string"}, {"type": "integer"}
DEV = {"type": "string", "enum": ["phone", "laptop"]}
GIT_TIER = {"status": 0, "github": 0, "log": 0, "diff": 0, "fetch": 0, "pull": 1, "switch": 1, "commit": 2, "push": 3}

TOOLS = {t.name: t for t in [
    Tool("open_app", "Open an app on the phone or laptop", {"name": S, "device": DEV}, ["name", "device"], 1,
         open_app, phone_if=lambda a: a.get("device") != "laptop"),
    Tool("get_status", "Read a system metric",
         {"metric": {"type": "string", "enum": ["battery", "ram", "cpu", "storage", "temperature", "processes"]}, "device": DEV},
         ["metric", "device"], 0, get_status, phone_if=lambda a: a.get("device") == "phone"),
    Tool("set_brightness", "Set phone or laptop screen brightness percent", {"level": I, "device": DEV}, ["level"], 1,
         lambda level, device="laptop": set_laptop_brightness(level), phone_if=lambda a: a.get("device") != "laptop"),
    Tool("set_volume", "Set phone media volume percent", {"level": I}, ["level"], 1),
    Tool("open_vscode", "Open a folder in VS Code on the laptop", {"path": S}, ["path"], 1, open_vscode),
    Tool("git", "Run a read-only or commit git action in a project",
         {"project": S, "action": {"type": "string", "enum": list(GIT_TIER)}, "message": S, "branch": S}, ["project", "action"],
         lambda a: GIT_TIER.get(a.get("action"), 3),
         lambda project, action, message=None, branch=None: git(project, action, message, branch)),
    Tool("run_project", "Run a project's configured task",
         {"project": S, "task": {"type": "string", "enum": ["dev", "test", "build"]}}, ["project", "task"], 1,
         lambda project, task: run_project(project, task)),
    Tool("run_powershell", "Run an arbitrary PowerShell command on the laptop (requires user confirmation)",
         {"command": S}, ["command"], 3, run_powershell),
    Tool("set_timer", "Start a countdown timer", {"minutes": I, "label": S}, ["minutes"], 0),
    Tool("remember", "Store a fact about the user for later", {"fact": S}, ["fact"], 1),
    Tool("recall", "Search FROSTI's memory", {"query": S}, ["query"], 0),
    Tool("tasks", "Task planner: add, list or finish a task",
         {"action": {"type": "string", "enum": ["add", "list", "done"]}, "text": S}, ["action"], lambda a: 0 if a.get("action") == "list" else 1),
    Tool("kill_process", "Close or terminate a laptop program by app or process name", {"name": S}, ["name"], 2, kill_process),
    Tool("play_music", "Play a song, artist or playlist", {"query": S, "device": DEV}, ["query", "device"], 1,
         play_music, phone_if=lambda a: a.get("device") != "laptop"),
    Tool("search_music", "Search Spotify and list songs to pick from", {"query": S}, ["query"], 0, search_music),
    Tool("media_control", "Pause, resume or skip the music that is playing",
         {"action": {"type": "string", "enum": list(MEDIA_KEYS)}, "device": DEV}, ["action", "device"], 1,
         media_control, phone_if=lambda a: a.get("device") != "laptop"),
    Tool("power", "Laptop power: keep awake until a named process or PID exits (process), or until CPU idle if unspecified; allow sleep, sleep now, shut down after N minutes, or cancel shutdown",
         {"action": {"type": "string", "enum": ["keep_awake", "allow_sleep", "sleep", "shutdown", "cancel_shutdown"]}, "minutes": I, "process": S},
         ["action"], lambda a: 2 if a.get("action") == "shutdown" else 1, power),
    Tool("describe_screen","Look at the current screen and describe it", {"device": DEV}, ["device"], 0, describe_screen),
]}
