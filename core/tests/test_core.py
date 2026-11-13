import asyncio, json, sqlite3, sys, tempfile, time, unittest
from unittest import mock
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from frosti_core import router
from frosti_core.brain import Brain, Session
from frosti_core.store import Store

FAST = [  # utterance -> (tool, args) the fast path must produce
    ("Open Spotify on my phone", ("open_app", {"name": "spotify", "device": "phone"})),
    ("launch chrome on the laptop", ("open_app", {"name": "chrome", "device": "laptop"})),
    ("How much battery does the phone have left?", ("get_status", {"metric": "battery", "device": "phone"})),
    ("what's my laptop RAM usage", ("get_status", {"metric": "ram", "device": "laptop"})),
    ("is the laptop running hot?", ("get_status", {"metric": "temperature", "device": "laptop"})),
    ("Set brightness to forty percent.", ("set_brightness", {"level": 40, "device": "phone"})),
    ("set the laptop brightness to 60", ("set_brightness", {"level": 60, "device": "laptop"})),
    ("make the screen as bright as possible", ("set_brightness", {"level": 100, "device": "phone"})),
    ("turn the volume down to 20", ("set_volume", {"level": 20})),
    ("mute the phone", ("set_volume", {"level": 0})),
    (r"open E:\frosti in vs code", ("open_vscode", {"path": r"e:\frosti"})),
    ("git status for frosti", ("git", {"project": "frosti", "action": "status"})),
    ("Show me the recent commits in frosti.", ("git", {"project": "frosti", "action": "log"})),
    ("what's the github status of frosti", ("git", {"project": "frosti", "action": "github"})),
    ("any open PRs on frosti?", ("git", {"project": "frosti", "action": "github"})),
    (r"what's the github status of E:\Personal-website", ("git", {"project": r"e:\personal-website", "action": "github"})),
    ("push frosti to github", ("git", {"project": "frosti", "action": "push"})),
    ("Run the tests for frosti.", ("run_project", {"project": "frosti", "task": "test"})),
    ("start the frosti dev server", ("run_project", {"project": "frosti", "task": "dev"})),
    ("build frosti", ("run_project", {"project": "frosti", "task": "build"})),
    ("Set a timer for ten minutes for tea.", ("set_timer", {"minutes": 10, "label": "tea"})),
    ("remind me in half an hour", ("set_timer", {"minutes": 30, "label": ""})),
    ("Remember that I prefer dark themes.", ("remember", {"fact": "i prefer dark themes"})),
    ("what did I tell you about my themes?", ("recall", {"query": "my themes"})),
    ("Kill chrome on the laptop.", ("kill_process", {"name": "chrome"})),
    ("Hey Frosti, open Spotify.", ("open_app", {"name": "spotify", "device": "phone"})),
    ("open calculator in laptop", ("open_app", {"name": "calculator", "device": "laptop"})),
    ("open paint on my pc", ("open_app", {"name": "paint", "device": "laptop"})),
    ("Close Word.", ("kill_process", {"name": "word"})),
    ("quit the calculator app on the laptop", ("kill_process", {"name": "calculator"})),
    ("Play Bohemian Rhapsody by Queen.", ("play_music", {"query": "bohemian rhapsody by queen", "device": "phone"})),
    ("play some jazz on my laptop", ("play_music", {"query": "some jazz", "device": "laptop"})),
    ("Play Believer by Imagine Dragons on Spotify.", ("play_music", {"query": "believer by imagine dragons", "device": "laptop"})),
    ("Search Believer on Spotify.", ("search_music", {"query": "believer"})),
    ("find songs by queen on spotify", ("search_music", {"query": "songs by queen"})),
    ("pause the music", ("media_control", {"action": "pause", "device": "phone"})),
    ("Resume", ("media_control", {"action": "play", "device": "phone"})),
    ("next song", ("media_control", {"action": "next", "device": "phone"})),
    ("skip this track on the laptop", ("media_control", {"action": "next", "device": "laptop"})),
    ("play the previous song", ("media_control", {"action": "previous", "device": "phone"})),
    ("keep the laptop on till the work finishes", ("power", {"action": "keep_awake"})),
    ("don't let the laptop sleep", ("power", {"action": "keep_awake"})),
    ("keep the laptop awake until chrome.exe exits", ("power", {"action": "keep_awake", "process": "chrome.exe"})),
    ("keep my laptop on till the blender process finishes", ("power", {"action": "keep_awake", "process": "blender"})),
    ("don't let the laptop sleep until process 12345 completes", ("power", {"action": "keep_awake", "process": "12345"})),
    ("let the laptop sleep", ("power", {"action": "allow_sleep"})),
    ("shutdown in 5 mins", ("power", {"action": "shutdown", "minutes": 5})),
    ("Shut down the laptop after five minutes.", ("power", {"action": "shutdown", "minutes": 5})),
    ("turn off the computer in an hour", ("power", {"action": "shutdown", "minutes": 60})),
    ("cancel the shutdown", ("power", {"action": "cancel_shutdown"})),
    ("put the laptop to sleep", ("power", {"action": "sleep"})),
    ("go to sleep", ("power", {"action": "sleep"})),
    ("add task buy milk", ("tasks", {"action": "add", "text": "buy milk"})),
    ("add call mom to my to do list", ("tasks", {"action": "add", "text": "call mom"})),
    ("what are my tasks?", ("tasks", {"action": "list"})),
    ("mark buy milk as done", ("tasks", {"action": "done", "text": "buy milk"})),
    ("what's running on the laptop", ("get_status", {"metric": "processes", "device": "laptop"})),
]
UNMATCHED = ["hey frosti, how are you?", "what is the capital of France?", "list the files in my downloads folder using powershell",
          "commit frosti with message 'add bench'", "turn off", "switch off it","Good evening, Frosti. How are the systems looking?"]

class Router(unittest.TestCase):
    def test_fast_path(self):
        for utt, want in FAST:
            with self.subTest(utt):
                self.assertEqual(router.match(utt), want)

    def test_unmatched(self):
        for utt in UNMATCHED:
            with self.subTest(utt):
                self.assertIsNone(router.match(utt))

class Alarm(unittest.TestCase):
    def test_alarm_picks_next_occurrence(self):
        from datetime import datetime
        evening, dawn = datetime(2026, 1, 1, 18, 30, 20), datetime(2026, 1, 1, 6, 0)
        self.assertEqual(router.alarm(7, 0, "", evening), ("set_timer", {"minutes": 30, "label": "Alarm 19:00"}))
        self.assertEqual(router.alarm(7, 0, "", dawn), ("set_timer", {"minutes": 60, "label": "Alarm 07:00"}))
        self.assertEqual(router.alarm(7, 30, "am", evening)[1]["minutes"], 13 * 60)
        self.assertEqual(router.alarm(12, 0, "am", evening)[1]["label"], "Alarm 00:00")
        self.assertEqual(router.match("set an alarm for 7:30 pm")[1]["label"], "Alarm 19:30")
        self.assertEqual(router.match("wake me up at six thirty am")[1]["label"], "Alarm 06:30")

class Apps(unittest.TestCase):
    APPS = [{"name": "Word", "id": None, "lnk": "Word.lnk", "exe": r"C:\Office\WINWORD.EXE"},
            {"name": "Google Chrome", "id": "Chrome", "lnk": "Google Chrome.lnk", "exe": r"C:\x\chrome.exe"},
            {"name": "Chrome Remote Desktop", "id": "crd", "lnk": None, "exe": ""},
            {"name": "Calculator", "id": "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App", "lnk": None, "exe": ""},
            {"name": "Spotify", "id": "SpotifyAB.Spotify!Spotify", "lnk": None, "exe": ""}]

    def test_find_app_fuzzy(self):
        from frosti_core.tools import find_app
        name = lambda q: (find_app(q, self.APPS) or {}).get("name")
        self.assertEqual(name("word"), "Word")
        self.assertEqual(name("chrome"), "Google Chrome")  # shortest whole-word match
        self.assertEqual(name("spotfy"), "Spotify")         # speech-to-text typo
        self.assertIsNone(name("notepad"))

    def test_process_for_friendly_names(self):
        from frosti_core.tools import process_for
        running = {"winword.exe", "chrome.exe", "calculatorapp.exe", "code.exe", "codehelper.exe"}
        self.assertEqual(process_for("word", running, self.APPS), ["winword.exe"])     # via the shortcut's exe
        self.assertEqual(process_for("chrome.exe", running, self.APPS), ["chrome.exe"])
        self.assertEqual(process_for("calculator", running, self.APPS), ["calculatorapp.exe"])
        self.assertEqual(process_for("vs code", running, self.APPS), ["code.exe"])  # alias
        self.assertEqual(process_for("ode", running, self.APPS), ["code.exe", "codehelper.exe"])  # ambiguous: ask
        self.assertEqual(process_for("ab", running, self.APPS), [])
        # a Start-menu app with no exe must not match nameless (access-denied) processes
        self.assertEqual(process_for("notepad", running | {""}, [{"name": "Notepad", "id": "x", "lnk": "", "exe": ""}]), [])

    def test_open_app_keeps_trust_boundary(self):
        from frosti_core.tools import open_app
        self.assertIn("unsafe", open_app("calc & del x")[0])

class KeepAwake(unittest.TestCase):
    def setUp(self):
        from frosti_core import tools
        self.tools = tools
        state = mock.patch.dict(tools._awake, stop=None)
        state.start(); self.addCleanup(state.stop)

    def test_watches_selected_process_without_start_menu_lookup(self):
        p = mock.Mock(pid=123, info={"name": "blender.exe"})
        with mock.patch.object(self.tools.psutil, "process_iter", return_value=[p]), \
                mock.patch.object(self.tools, "start_apps") as apps, \
                mock.patch.object(self.tools.threading, "Thread") as thread:
            reply, _ = self.tools.power("keep_awake", process="blender")
            self.assertIn("123", reply)
            self.assertIs(thread.call_args.kwargs["args"][1], p)
            thread.return_value.start.assert_called_once()
            apps.assert_not_called()

    def test_pid_and_invalid_pid(self):
        p = mock.Mock(pid=123)
        with mock.patch.object(self.tools.psutil, "Process", return_value=p) as process, \
                mock.patch.object(self.tools.threading, "Thread"):
            self.assertIn("123", self.tools.power("keep_awake", process="123")[0])
            process.assert_called_once_with(123)
        self.tools._awake["stop"] = None
        with mock.patch.object(self.tools.psutil, "Process", side_effect=self.tools.psutil.NoSuchProcess(123)), \
                mock.patch.object(self.tools.threading, "Thread") as thread:
            self.assertIn("can't monitor", self.tools.power("keep_awake", process="123")[0])
            thread.assert_not_called()

    def test_missing_or_ambiguous_process_does_not_hold_awake(self):
        p = mock.Mock(pid=123, info={"name": "python.exe"})
        other = mock.Mock(pid=456, info={"name": "python.exe"})
        with mock.patch.object(self.tools.psutil, "process_iter", return_value=[p, other]), \
                mock.patch.object(self.tools, "start_apps", return_value=[]), \
                mock.patch.object(self.tools.threading, "Thread") as thread:
            self.assertIn("No missing", self.tools.power("keep_awake", process="missing")[0])
            reply, _ = self.tools.power("keep_awake", process="python")
            self.assertIn("123, 456", reply)
            thread.assert_not_called()
            self.assertIsNone(self.tools._awake["stop"])

    def test_process_exit_releases_sleep_even_with_busy_cpu(self):
        p = mock.Mock()
        p.is_running.side_effect = [True, False]
        stop = mock.Mock()
        stop.wait.return_value = False
        self.tools._awake["stop"] = stop
        with mock.patch.object(self.tools.ctypes.windll.kernel32, "SetThreadExecutionState") as state, \
                mock.patch.object(self.tools.psutil, "cpu_percent") as cpu:
            self.tools._hold_awake(stop, p)
            self.assertEqual(state.call_args_list, [mock.call(0x80000001), mock.call(0x80000000)])
            cpu.assert_not_called()
            self.assertIsNone(self.tools._awake["stop"])

    def test_cancel_releases_sleep(self):
        stop = mock.Mock()
        stop.wait.return_value = True
        self.tools._awake["stop"] = stop
        with mock.patch.object(self.tools.ctypes.windll.kernel32, "SetThreadExecutionState") as state:
            self.tools.power("allow_sleep")
            stop.set.assert_called_once()
            self.tools._hold_awake(stop, mock.Mock())
            self.assertEqual(state.call_args_list[-1], mock.call(0x80000000))
            self.assertIsNone(self.tools._awake["stop"])

class BrainPolicy(unittest.TestCase):
    def setUp(self):
        self.store = Store(Path(tempfile.mkdtemp()) / "t.db")

    def session(self, approve):
        class S(Session):
            asked = []
            async def confirm(s, summary, tier): S.asked.append((summary, tier)); return approve
        return S()

    def run_(self, text, approve=False):
        s = self.session(approve)
        return asyncio.run(Brain(self.store).handle(text, s)), s.asked

    def test_powershell_needs_confirmation_and_is_audited(self):
        s = self.session(False)
        reply, _, _ = asyncio.run(Brain(self.store).run_tool("run_powershell", {"command": "Remove-Item x"}, s))
        self.assertEqual(s.asked, [("Run PowerShell: Remove-Item x", 3)])
        self.assertEqual(reply, "Okay, cancelled.")
        self.assertEqual(self.store.db.execute("SELECT tool, approved FROM audit").fetchall(), [("run_powershell", 0)])

    def test_shutdown_needs_confirmation(self):
        r, asked = self.run_("shutdown in 5 mins", approve=False)  # declined, so nothing is scheduled
        self.assertEqual(asked, [("Shut down the laptop in 5 minutes", 2)])
        self.assertEqual(r["reply"], "Okay, cancelled.")

    def test_kill_confirmation_says_how_many(self):
        from frosti_core import tools
        procs = [mock.Mock(info={"name": "chatgpt.exe"})] * 3
        with mock.patch.object(tools, "kill_target", return_value=([], "chatgpt.exe")), \
             mock.patch.object(tools.psutil, "process_iter", return_value=procs):
            r, asked = self.run_("kill chatgpt", approve=False)  # declined, so nothing is killed
        self.assertEqual(asked, [("Close 3 chatgpt.exe processes", 2)])
        with mock.patch.object(tools, "kill_target", return_value=(["a.exe", "b.exe"], None)):
            self.assertEqual(tools.kill_preview("x"), "Kill process x")  # ambiguous: no count

    def test_spotify_plays_track_with_preview(self):
        from frosti_core import tools
        track = {"name": "Believer", "uri": "spotify:track:abc", "artists": [{"name": "Imagine Dragons"}],
                 "album": {"name": "Evolve", "images": [{"url": "big"}, {"url": "mid"}]}}
        opened = []
        with mock.patch.object(tools, "start_apps", return_value=[{"name": "Spotify"}]), \
             mock.patch.object(tools, "spotify_track", return_value=track) as search, \
             mock.patch.object(tools, "_fetch", return_value=b"jpg") as fetch, \
             mock.patch.object(tools.os, "startfile", opened.append, create=True):
            r, _ = self.run_("play believer by imagine dragons on spotify")
        search.assert_called_once_with("believer imagine dragons")
        fetch.assert_called_once_with("mid", timeout=2)
        self.assertEqual(opened, ["spotify:track:abc"])
        self.assertEqual(r["reply"], "Playing Believer by Imagine Dragons.")
        self.assertEqual(r["media"], {"title": "Believer", "artist": "Imagine Dragons", "album": "Evolve",
                                      "art": "data:image/jpeg;base64,anBn", "app": "Spotify"})

    def test_spotify_error_falls_back_to_search(self):
        from frosti_core import tools
        opened = []
        with mock.patch.object(tools, "start_apps", return_value=[{"name": "Spotify"}]), \
             mock.patch.object(tools, "spotify_track", side_effect=OSError("offline")), \
             mock.patch.object(tools.os, "startfile", opened.append, create=True):
            r, _ = self.run_("play believer on spotify")
        self.assertEqual(opened, ["spotify:search:believer"])
        self.assertEqual(r["reply"], "Searching Spotify for believer.")

    def test_spotify_search_lists_playable_tracks(self):
        from frosti_core import tools
        track = {"name": "Believer", "uri": "spotify:track:abc", "artists": [{"name": "Imagine Dragons"}],
                 "album": {"name": "Evolve", "images": [{"url": "big"}, {"url": "mid"}, {"url": "small"}]}}
        with mock.patch.object(tools, "spotify_search", return_value=[track, track]) as search, \
             mock.patch.object(tools, "_fetch", return_value=b"jpg") as fetch:
            r, _ = self.run_("search believer by imagine dragons on spotify")
        search.assert_called_once_with("believer imagine dragons", 8)
        fetch.assert_called_with("small", timeout=2)
        self.assertEqual(r["media"]["tracks"], [{"title": "Believer", "artist": "Imagine Dragons", "album": "Evolve",
                                                 "art": "data:image/jpeg;base64,anBn", "uri": "spotify:track:abc"}] * 2)

    def test_song_search_without_spotify_keys_uses_itunes(self):
        from frosti_core import tools
        found = json.dumps({"results": [{"trackName": "Punchiri", "artistName": "Eechuu/AC, Suhas & Chris", "collectionName": "Punchiri - Single",
                                         "artworkUrl60": "small"}]}).encode()
        with mock.patch.object(tools, "spotify_search", return_value=None), \
             mock.patch.object(tools, "_fetch", side_effect=[found, b"jpg"]):
            r, _ = self.run_("search punchiri on spotify")
        t = r["media"]["tracks"][0]
        self.assertEqual((t["title"], t["art"]), ("Punchiri", "data:image/jpeg;base64,anBn"))
        self.assertEqual(t["uri"], "spotify:search:Punchiri%20Eechuu%2FAC")
        self.assertRegex(t["uri"], r"spotify:(track:[A-Za-z0-9]{22}|search:[\w%.~-]{1,300})")  # what the gateway accepts

    def test_task_planner(self):
        self.run_("add task buy milk"); self.run_("add call mom to my to do list")
        r, _ = self.run_("what are my tasks")
        self.assertEqual(r["reply"], "You have 2 tasks: buy milk; call mom.")
        r, _ = self.run_("mark milk as done")  # partial name is enough
        self.assertEqual(r["reply"], "Done: buy milk.")
        r, _ = self.run_("mark taxes as done")
        self.assertIn("couldn't find", r["reply"])
        self.assertEqual([t["text"] for t in self.store.tasks()], ["call mom"])

    def test_audit_is_append_only(self):
        self.store.audit("t", "x", {}, 0, True, "ok")
        with self.assertRaises(sqlite3.DatabaseError):
            self.store.db.execute("DELETE FROM audit")

    def test_memory_roundtrip(self):
        self.run_("remember that I prefer dark themes")
        r, _ = self.run_("what did I tell you about my themes?")
        self.assertIn("dark themes", r["reply"])

    def test_read_tool_runs_without_confirmation(self):
        r, asked = self.run_("what's my laptop RAM usage")
        self.assertEqual(asked, [])
        self.assertIn("percent used", r["reply"])

    def test_open_app_falls_back_to_laptop_unless_phone_named(self):
        from unittest import mock
        from frosti_core.tools import TOOLS
        with mock.patch.object(TOOLS["open_app"], "run", lambda name, device: (f"Opening {name}.", "")):
            r, _ = self.run_("open notepad")  # no phone connected in this test
            self.assertEqual((r["reply"], r["args"]["device"]), ("Opening notepad.", "laptop"))
            r, _ = self.run_("open notepad on my phone")
            self.assertEqual(r["reply"], "The phone isn't connected.")

    def test_phone_tool_without_phone(self):
        r, _ = self.run_("set brightness to 40")
        self.assertEqual(r["reply"], "The phone isn't connected.")

    def test_unmatched_gets_a_hint(self):
        r, asked = self.run_("how are you")
        self.assertIn("didn't catch that", r["reply"])
        self.assertEqual((r["tool"], asked), (None, []))

class Dashboards(unittest.TestCase):
    def setUp(self):
        self.store = Store(Path(tempfile.mkdtemp()) / "t.db")
        self.brain = Brain(self.store)

    def test_memory_lists_and_forgets_facts(self):
        from frosti_core.gateway import memory
        self.store.remember("I like tea"); self.store.remember("my cat is Io")
        facts = memory(self.brain)["facts"]
        self.assertEqual({f["fact"] for f in facts}, {"I like tea", "my cat is Io"})
        self.assertEqual(self.store.forget(facts[0]["id"]), 1)
        self.assertEqual(len(memory(self.brain)["facts"]), 1)

    def test_timer_shows_in_tasks_until_due(self):
        asyncio.run(self.brain.handle("set a timer for 5 minutes for tea", Session()))
        self.assertEqual([t["label"] for t in self.brain.active_timers()], ["tea"])
        self.brain.timers[0]["due"] = 0
        self.assertEqual(self.brain.active_timers(), [])

    def test_top_apps_counts_successful_opens(self):
        for _ in range(3): self.store.audit("phone", "open_app", {"name": "notepad", "device": "laptop"}, 1, True, "Opening Notepad.")
        self.store.audit("phone", "open_app", {"name": "notepad", "device": "phone"}, 1, True, "I couldn't find notepad on the phone.")
        self.store.audit("desk", "open_app", {"name": "youtube", "device": "phone"}, 1, True, "Opening YouTube.")
        self.assertEqual(self.store.top_apps(), [dict(label="Notepad", cmd="open notepad on the laptop"),
                                                 dict(label="YouTube", cmd="open youtube on the phone")])
        from frosti_core import router
        self.assertEqual(router.match("open notepad on the laptop"), ("open_app", {"name": "notepad", "device": "laptop"}))

    def test_timers_survive_a_restart(self):
        heard = []
        class Desk(Session):
            async def notify(s, text): heard.append(text)
        asyncio.run(self.brain.handle("set a timer for 5 minutes for tea", Session()))
        self.store.add_timer(time.time() - 60, "eggs")  # came due while the Core was off
        brain = Brain(self.store)  # the restarted Core
        self.assertEqual([t["label"] for t in brain.active_timers()], ["tea"])
        brain.sessions.add(Desk())
        async def start():
            brain.resume_timers(asyncio.get_running_loop(), overdue_delay=0)
            await asyncio.sleep(0.05)
        asyncio.run(start())
        self.assertEqual(heard, ["Timer done: eggs."])
        self.assertEqual([t["label"] for t in self.store.timers()], ["tea"])  # fired timers are removed

    def test_phone_timer_runs_on_phone_without_laptop_countdown(self):
        calls = []
        class Phone(Session):
            name = "phone"
            async def phone(self, tool, args):
                calls.append((tool, args))
                return "Timer started on the phone."
        result = asyncio.run(self.brain.handle("set a timer for 5 minutes for tea", Phone()))
        self.assertEqual(calls, [("set_timer", {"minutes": 5, "label": "tea"})])
        self.assertEqual(result["reply"], "Timer started on the phone.")
        self.assertEqual(self.brain.active_timers(), [])

    def test_activity_log_has_args_newest_first(self):
        self.store.audit("phone", "set_brightness", {"level": 40}, 1, True, "Brightness 40%")
        self.store.audit("desk", "kill", {"name": "notepad"}, 2, False, "declined")
        log = self.store.recent(300)
        self.assertEqual([e["tool"] for e in log[:2]], ["kill", "set_brightness"])
        self.assertEqual(log[0]["args"], '{"name": "notepad"}')
        self.assertFalse(log[0]["approved"])

    def test_stats_shape(self):
        from frosti_core.gateway import stats
        s = stats(self.brain)
        for k in ("cpu", "ram", "top", "voice", "phone", "uptime"):
            self.assertIn(k, s)

    def test_console_page_is_loopback_only(self):
        from frosti_core.gateway import console_page
        class R:
            def __init__(self, host, path="/"): self.headers, self.path = {"Host": host}, path
        class C:
            def __init__(self, ip): self.remote_address = (ip, 1)
            def respond(self, status, text):
                class Resp: pass
                r = Resp(); r.status, r.body = status, text
                r.headers = {"Content-Type": "text/plain"}
                return r
        self.assertEqual(console_page(C("192.168.1.5"), R("127.0.0.1:8765")).status, 403)
        self.assertEqual(console_page(C("127.0.0.1"), R("evil.example:8765")).status, 403)  # DNS rebinding
        ok = console_page(C("127.0.0.1"), R("127.0.0.1:8765"))
        self.assertEqual(ok.status, 200)
        self.assertNotIn("__FROSTI_TOKEN__", ok.body)
        self.assertIn("text/html", ok.headers["Content-Type"])

class NowPlayingPush(unittest.TestCase):
    def test_pushes_only_changes(self):
        from frosti_core import gateway
        track = dict(title="Song", artist="A", album="", art=None, app="Spotify", playing=True)
        reads = iter([track, track, {**track, "playing": False}, None])
        async def fake():
            try:
                return next(reads)
            except StopIteration:
                raise asyncio.CancelledError
        class WS:
            sent = []
            async def send(self, m): self.sent.append(m)
        class S: ws = WS()
        brain = mock.Mock(sessions={S(), Session()})  # Session: the terminal console, which has no socket
        with mock.patch.object(gateway, "now_playing", fake):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(gateway.watch_media(brain, every=0))
        got = [json.loads(m)["media"] for m in WS.sent]
        self.assertEqual(got, [track, {**track, "playing": False}, None])

    def test_position_pushes_only_on_seek(self):
        from frosti_core import gateway
        t = dict(title="Song", artist="A", album="", art=None, app="Spotify", playing=False, length=200, shuffle=None)
        reads = iter([{**t, "position": 10}, {**t, "position": 11}, {**t, "position": 60}, {**t, "position": 61}])
        async def fake():
            try:
                return next(reads)
            except StopIteration:
                raise asyncio.CancelledError
        class WS:
            sent = []
            async def send(self, m): self.sent.append(m)
        class S: ws = WS()
        brain = mock.Mock(sessions={S()})
        with mock.patch.object(gateway, "now_playing", fake):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(gateway.watch_media(brain, every=0))
        self.assertEqual([json.loads(m)["media"]["position"] for m in WS.sent], [10, 60])  # drift ignored, seek pushed
        self.assertEqual(brain.now_playing["position"], 61)  # late joiners get the fresh position

    def test_hung_read_does_not_freeze_the_feed(self):
        from frosti_core import gateway
        async def stubborn():  # like a WinRT call that ignores cancel: wait_for would sit here 10 s
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                await asyncio.sleep(10)  # the second cancel (asyncio.run's shutdown) ends it
        async def main():
            t = time.monotonic()
            with self.assertRaises(asyncio.TimeoutError):
                await gateway.bounded(stubborn(), 0.05)
            return time.monotonic() - t
        self.assertLess(asyncio.run(asyncio.wait_for(main(), 2)), 1)

class DroppedReply(unittest.TestCase):
    def test_reply_kept_when_phone_drops_and_sent_on_reconnect(self):
        import websockets
        from frosti_core.gateway import PhoneSession
        r = dict(reply="It's 5 pm.", detail="", tool="time", path="fast", seconds=0.1)
        class Dropped:
            async def send(self, m): raise websockets.ConnectionClosed(None, None)
        class Live:
            sent = []
            async def send(self, m): self.sent.append(json.loads(m))
        brain = mock.Mock(sessions=set())
        asyncio.run(PhoneSession(Dropped(), brain, None).deliver(r))  # must not raise
        _, rid, kept = brain.last_reply
        self.assertEqual(kept, r)
        asyncio.run(PhoneSession(Live(), brain, None).deliver(kept, rid))  # the resend keeps its number
        self.assertEqual([(m["type"], m.get("rid"), m.get("text")) for m in Live.sent],
                         [("reply", rid, "It's 5 pm."), ("state", None, None)])

if __name__ == "__main__":
    unittest.main()
