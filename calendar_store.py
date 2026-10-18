# ============================================
# FILE: calendar_store.py
# ============================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Notes of the calendar of the TV (calendar page of the home screen, click
or OK on the time and date, ROADMAP 2.17): calendar.json in the
application folder, kept on the Raspberry only (the server only relays the
messages between the TV page and the agent, it never keeps the notes).

A note: {"id": "a1b2c3d4e5f6", "date": "2026-10-18", "text": "Anniversaire
de Paul", "yearly": true}; yearly = the note comes back every year on the
same day (birthdays, name days). Each note is checked when it is saved and
when the file is read (the file may have been edited by hand).
"""

import datetime
import json
import os
import re
import secrets
from pathlib import Path

FILE_NAME = "calendar.json"
TEXT_MAX_LENGTH = 80
MAX_NOTES = 300
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")
# Control characters and < > are removed from the texts
UNWANTED_CHARACTERS = re.compile(r"[\x00-\x1f\x7f<>]")


def clean_text(value):
    """Text of a note cleaned (one line, cut), or None if empty."""
    if not isinstance(value, str):
        return None
    text = " ".join(UNWANTED_CHARACTERS.sub(" ", value).split())[:TEXT_MAX_LENGTH].strip()
    return text or None


def valid_date(value):
    if not isinstance(value, str) or not DATE_PATTERN.match(value):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def clean_note(note):
    """A note checked ({id, date, text, yearly}), or None if not valid."""
    if not isinstance(note, dict) or not valid_date(note.get("date")):
        return None
    text = clean_text(note.get("text"))
    if text is None:
        return None
    note_id = note.get("id")
    return {
        "id": note_id if isinstance(note_id, str) and ID_PATTERN.match(note_id) else None,
        "date": note["date"],
        "text": text,
        "yearly": note.get("yearly") is True,
    }


def calendar_file(base_dir):
    return Path(base_dir) / FILE_NAME


def load(base_dir):
    """Valid notes of calendar.json (sorted by date), [] if none or broken."""
    try:
        with open(calendar_file(base_dir), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    notes, seen = [], set()
    for note in (data.get("notes") if isinstance(data, dict) else None) or []:
        clean = clean_note(note)
        if clean is None or clean["id"] is None or clean["id"] in seen:
            continue
        seen.add(clean["id"])
        notes.append(clean)
    return sorted(notes, key=lambda n: (n["date"], n["text"]))[:MAX_NOTES]


def write(base_dir, notes):
    """Writes the notes in one go; True if saved."""
    path = calendar_file(base_dir)
    temporary = path.with_suffix(".json.new")
    try:
        with open(temporary, "w", encoding="utf-8") as f:
            json.dump({"notes": notes}, f, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    except OSError as e:
        print(f"⚠️ Calendar not saved ({e})")
        return False
    return True


def save_note(base_dir, note):
    """
    Adds a note (no id or an unknown id) or changes it (known id).
    Returns (notes, error): error = None, "invalid", "full" or "save".
    """
    clean = clean_note(note)
    notes = load(base_dir)
    if clean is None:
        return notes, "invalid"
    index = next((i for i, n in enumerate(notes) if clean["id"] and n["id"] == clean["id"]), None)
    if index is None:
        if len(notes) >= MAX_NOTES:
            return notes, "full"
        clean["id"] = secrets.token_hex(6)
        notes.append(clean)
    else:
        notes[index] = clean
    notes.sort(key=lambda n: (n["date"], n["text"]))
    if not write(base_dir, notes):
        return load(base_dir), "save"
    return notes, None


def delete_note(base_dir, note_id):
    """Removes a note. Returns (notes, error): error = None or "save"."""
    notes = load(base_dir)
    kept = [n for n in notes if n["id"] != note_id]
    if len(kept) == len(notes):
        return notes, None
    if not write(base_dir, kept):
        return notes, "save"
    return kept, None
