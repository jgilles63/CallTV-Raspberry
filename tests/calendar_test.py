# Calendar of the TV (calendar_store.py, agent.py; ROADMAP 2.17): notes kept
# on the Raspberry only, in calendar.json. Checks: each note checked (date,
# text cleaned and cut, yearly), added with a new id or changed by its id,
# deleted, sorted, at most MAX_NOTES; a broken or hand-edited file never
# stops anything (bad notes left out); agent: notes sent after the
# registration and when asked, saved / deleted with their answer.
import asyncio
import json
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Raspberry_receiver/

cfg = types.ModuleType("config")
cfg.LANGUAGE = "fr"; cfg.RASPBERRY_ID = "rpi-calendar"; cfg.DEVICE_SECRET = "secret"
cfg.SERVER_URL = "wss://x"; cfg.UNAUTHORIZED_RETRY_DELAY = 30; cfg.CALL_DURATION = 30
cfg.MOUSE_DEVICE = None; cfg.MOUSE_RETRY_DELAY = 5; cfg.BASE_DIR = Path(tempfile.mkdtemp())
cfg.CACHE_DIR = Path(tempfile.mkdtemp()); cfg.VOICE_VOLUME = 1.5; cfg.AUDIO_DEVICE = None
cfg.MAX_CALLER_NAME_LENGTH = 30; cfg.MAX_CACHED_CALLS = 5; cfg.RINGTONE_PATH = "x.wav"; cfg.RINGTONE_VOLUME = 0.2
cfg.WEATHER_CITY = "Madrid"; cfg.WEATHER_POSTCODE = "28051"; cfg.WEATHER_COUNTRY = "Espagne"
cfg.RADIO_STATIONS = []
sys.modules["config"] = cfg

evdev = types.ModuleType("evdev")
evdev.InputDevice = object
evdev.list_devices = lambda: []
evdev.ecodes = types.SimpleNamespace(EV_KEY=1, KEY={}, BTN_LEFT=272, REL_X=0, EV_REL=2)
sys.modules["evdev"] = evdev

tv = types.ModuleType("tv_control")
tv.tv_on_and_accept = lambda: None
tv.tv_return = lambda: None
sys.modules["tv_control"] = tv

import calendar_store as cs  # noqa: E402
import agent  # noqa: E402

passed = failed = 0


def check(label, condition, detail=""):
    global passed, failed
    passed, failed = passed + bool(condition), failed + (not condition)
    print(f"{'OK ' if condition else 'KO '} {label} {detail}")


# --- Notes checked ---
check("text cleaned: one line, no control characters nor < >, spaces joined",
      cs.clean_text("  Docteur\n<b>14:30</b>\t ok ") == "Docteur b 14:30 /b ok", repr(cs.clean_text("  Docteur\n<b>14:30</b>\t ok ")))
check("text cut at 80, empty -> None", len(cs.clean_text("x" * 200)) == 80 and cs.clean_text("   ") is None and cs.clean_text(3) is None)
check("dates: real days only", cs.valid_date("2028-02-29") and not cs.valid_date("2027-02-29")
      and not cs.valid_date("2026-13-01") and not cs.valid_date("18/10/2026") and not cs.valid_date(None))
check("note: known fields only, yearly only if true", cs.clean_note({"date": "2026-10-18", "text": "Paul", "yearly": "yes", "x": 1})
      == {"id": None, "date": "2026-10-18", "text": "Paul", "yearly": False})
check("note with a bad id: id dropped (a new one will be given)", cs.clean_note({"id": "../x", "date": "2026-10-18", "text": "a"})["id"] is None)

# --- Saved, changed, deleted ---
base = Path(tempfile.mkdtemp())
check("no file: no notes", cs.load(base) == [])
notes, error = cs.save_note(base, {"date": "2026-10-20", "text": "Docteur 14:30"})
first_id = notes[0]["id"]
check("added: a new id (12 hex), saved in calendar.json", error is None and len(notes) == 1 and cs.ID_PATTERN.match(first_id)
      and json.loads((base / "calendar.json").read_text(encoding="utf-8"))["notes"][0]["text"] == "Docteur 14:30")
notes, error = cs.save_note(base, {"date": "2026-10-18", "text": "Anniversaire de Paul", "yearly": True, "id": "abcdefabcdef"})
check("unknown id: added with a new id, sorted by date", error is None and [n["text"] for n in notes] == ["Anniversaire de Paul", "Docteur 14:30"]
      and notes[0]["id"] != "abcdefabcdef")
notes, error = cs.save_note(base, {"id": first_id, "date": "2026-10-21", "text": "Docteur 15:00"})
check("known id: changed (text and date), not added", error is None and len(notes) == 2
      and [n for n in notes if n["id"] == first_id][0] == {"id": first_id, "date": "2026-10-21", "text": "Docteur 15:00", "yearly": False})
notes, error = cs.save_note(base, {"date": "2026-10-21", "text": "  "})
check("bad note: refused (invalid), nothing changed", error == "invalid" and len(notes) == 2 and len(cs.load(base)) == 2)
notes, error = cs.delete_note(base, first_id)
check("deleted", error is None and [n["text"] for n in notes] == ["Anniversaire de Paul"] and len(cs.load(base)) == 1)
notes, error = cs.delete_note(base, "000000000000")
check("unknown id deleted: nothing changes, no error", error is None and len(notes) == 1)
full = Path(tempfile.mkdtemp())
cs.write(full, [{"id": f"{i:012x}", "date": "2026-10-18", "text": f"n{i}", "yearly": False} for i in range(cs.MAX_NOTES)])
notes, error = cs.save_note(full, {"date": "2026-10-19", "text": "one more"})
check("at most MAX_NOTES: refused (full)", error == "full" and len(cs.load(full)) == cs.MAX_NOTES)

# --- File broken or edited by hand ---
broken = Path(tempfile.mkdtemp())
(broken / "calendar.json").write_text("{not json", encoding="utf-8")
check("broken file: no notes, nothing breaks", cs.load(broken) == [])
(broken / "calendar.json").write_text(json.dumps({"notes": [
    {"id": "aaaaaaaaaaaa", "date": "2026-10-18", "text": "ok"}, {"id": "aaaaaaaaaaaa", "date": "2026-10-19", "text": "same id"},
    {"id": "bbbbbbbbbbbb", "date": "2026-02-30", "text": "bad date"}, {"date": "2026-10-18", "text": "no id"},
    {"id": "cccccccccccc", "date": "2026-10-17", "text": "<script>"}, "x"]}), encoding="utf-8")
check("edited by hand: bad notes left out, texts cleaned again",
      [n["text"] for n in cs.load(broken)] == ["script", "ok"], [n["text"] for n in cs.load(broken)])
(broken / "calendar.json").write_text(json.dumps([1, 2]), encoding="utf-8")
check("file of another shape: no notes", cs.load(broken) == [])


# --- Agent ---
async def agent_calendar():
    a = agent.TVControlAgent()
    sent = []

    async def capture(data):
        sent.append(data)

    async def nothing():
        return None

    a.send_message = capture
    a.ask_contacts = nothing
    a.send_radio_state = nothing
    cfg.BASE_DIR = Path(tempfile.mkdtemp())
    await a.handle_message({"type": "register_ack"})
    check("registered: notes sent to the TV page (the home screen shows the ones of the day)",
          sent == [{"type": "calendar", "notes": []}], sent)
    sent.clear()
    await a.handle_message({"type": "calendar_save", "note": {"date": "2026-10-18", "text": "Coiffeur", "yearly": False}})
    check("calendar_save: saved, all the notes sent back with the answer",
          len(sent) == 1 and sent[0]["done"] == "save" and sent[0]["ok"] is True and "error" not in sent[0]
          and [n["text"] for n in sent[0]["notes"]] == ["Coiffeur"] and len(cs.load(cfg.BASE_DIR)) == 1, sent)
    note_id = sent[0]["notes"][0]["id"]
    sent.clear()
    await a.handle_message({"type": "calendar_save", "note": {"date": "nope", "text": "x"}})
    check("bad note: answer not ok (invalid)", sent[0]["ok"] is False and sent[0]["error"] == "invalid" and len(sent[0]["notes"]) == 1, sent)
    sent.clear()
    await a.handle_message({"type": "calendar_request"})
    check("calendar_request: the notes", sent == [{"type": "calendar", "notes": cs.load(cfg.BASE_DIR)}])
    sent.clear()
    await a.handle_message({"type": "calendar_delete", "id": note_id})
    check("calendar_delete: deleted, answer ok", sent == [{"type": "calendar", "notes": [], "done": "delete", "ok": True}], sent)

asyncio.run(agent_calendar())

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
