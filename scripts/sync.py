#!/usr/bin/env python3
"""Synchronize the durable queue. No daemon, database access or destructive API calls."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from common import (Anki, Error, Unavailable, ROOT, NAME, FIELDS, check_profile, check_record,
                    config, contains, durable_replace, encode_fields, ensure_model, find_key, locked,
                    normalized, note_fields, plain, read_jsonl, write_jsonl)


def sync_note(api, record):
    key = record["fields"]["Key"]
    incoming = encode_fields(record["fields"])
    note = find_key(api, key)
    disposition = "existing"
    updates = {}
    if note is None:
        # Key is the first field: Anki's own global/model duplicate check is the
        # second guard when an add succeeded but its response was lost.
        nid = api.call("addNote", note={"deckName": NAME, "modelName": NAME,
                       "fields": incoming, "tags": record["tags"],
                       "options": {"allowDuplicate": False, "duplicateScope": "collection"}})
        if not isinstance(nid, int) or isinstance(nid, bool) or nid <= 0:
            raise Unavailable("addNote returned no valid note ID; keep pending")
        note = find_key(api, key)
        if not note or note["noteId"] != nid or note_fields(note) != incoming:
            raise Unavailable("Created note could not be verified; keep pending")
        disposition = "created"
        wanted_tags = record["tags"]
    else:
        current = note_fields(note)
        if normalized(plain(current["Term"])) != normalized(record["fields"]["Term"]):
            raise Error("Key belongs to a different Term; no fields changed")
        cards = api.call("cardsInfo", cards=note["cards"])
        if len(cards) != len(note["cards"]) or not cards or any(c.get("deckName") != NAME for c in cards):
            raise Error("Matching note has cards outside the target deck; retained for review")
        # Treat context/prompt/answer/hint as one unit. Never insert a new answer
        # into a manually edited sentence, or an unrelated hint into an old cue.
        coupled = ("Context", "Prompt", "Answer", "Hint")
        context_compatible = all(not current[k].strip() or current[k] == incoming[k] for k in coupled)
        # Flags are never supplemented, so the existing Productive flag decides whether
        # a blank would be shown on the recall side. A leaking blank is not compatible.
        leaking = set()
        if current["Productive"]:
            leaking = {k for k in ("Definition", "Prompt", "Hint") if current[k] == ""
                       and any(contains(record["fields"][k], form) for form in record["target_forms"])}
        candidates = ["Definition", "Collocation", "Contrast", "IPA"]
        if context_compatible and "Prompt" not in leaking:
            candidates += list(coupled)
        for field in candidates:
            if field not in leaking and current[field] == "" and incoming[field]:
                updates[field] = incoming[field]
        # Empty flags can be deliberate user choices. Do not re-enable cards.
        if updates:
            fresh = api.call("notesInfo", notes=[note["noteId"]])
            if len(fresh) != 1 or not fresh[0] or note_fields(fresh[0]) != current:
                raise Error("Note changed during sync; keep pending and retry when editing is finished")
            api.call("updateNoteFields", note={"id": note["noteId"], "fields": updates})
            disposition = "supplemented"
        domain_tags = [t for t in record["tags"] if not t.startswith("context_")]
        # Context provenance describes the actual saved Context, not every later encounter.
        # Checking the saved value also covers a retry after a lost update response.
        saved_context = updates.get("Context", current["Context"])
        if saved_context == incoming["Context"] and not any(t.casefold().startswith("context_") for t in note["tags"]):
            domain_tags.append("context_" + record["context_origin"])
        wanted_tags = domain_tags
        missing = sorted(t for t in set(domain_tags) if t.casefold() not in {x.casefold() for x in note["tags"]})
        if missing:
            api.call("addTags", notes=[note["noteId"]], tags=" ".join(missing))
    verified = find_key(api, key)
    if not verified or verified["noteId"] != note["noteId"]:
        raise Unavailable("Note verification failed; keep pending")
    actual = note_fields(verified)
    if any(actual[k] != value for k, value in updates.items()):
        raise Unavailable("Field update could not be verified; keep pending")
    if any(not actual[k].strip() for k in ("Term", "Definition", "Context")) or not (actual["Receptive"] or actual["Productive"]):
        raise Error("Existing note is incomplete; retained for manual review")
    if actual["Productive"] and any(not actual[k].strip() for k in ("Prompt", "Answer")):
        raise Error("Existing productive card is incomplete; retained for review")
    if not verified["cards"]:
        raise Error("Note has no generated cards; retained for review")
    cards = api.call("cardsInfo", cards=verified["cards"])
    enabled = {i for i, flag in enumerate(("Receptive", "Productive")) if actual[flag] == "1"}
    if (len(cards) != len(verified["cards"]) or any(c.get("deckName") != NAME for c in cards)
            or not enabled.issubset({c.get("ord") for c in cards})):
        raise Error("Generated card types or target deck could not be verified; keep pending")
    if not {t.casefold() for t in wanted_tags}.issubset({t.casefold() for t in verified["tags"]}):
        raise Unavailable("Tag update could not be verified; keep pending")
    return {"note_id": verified["noteId"], "disposition": disposition,
            "preserved_existing_context": actual["Context"] != incoming["Context"]}


def synchronize(root, api=None):
    with locked(root) as data:
        queue = read_jsonl(data / "pending.jsonl")
        for record in queue:
            check_record(record)
        if not queue:
            return {"status": "synced", "confirmed": 0, "pending": 0, "results": []}
        cfg = config(root)
        api = api or Anki(cfg)
        results = []
        try:
            api.call("version")
            check_profile(api, cfg)
            ensure_model(api)
            history = read_jsonl(data / "history.jsonl")
            # Stop on the first failure; there are no immediate write retries.
            while queue:
                check_profile(api, cfg)
                record = queue[0]
                result = sync_note(api, record)
                receipt = {"record": record, "profile": cfg["expected_profile"], **result,
                           "confirmed_at": datetime.now(timezone.utc).isoformat()}
                if not any(h["record"]["id"] == record["id"] and h["profile"] == receipt["profile"]
                           and h["note_id"] == receipt["note_id"] for h in history):
                    history.append(receipt)
                    write_jsonl(data / "history.jsonl", history)
                # A crash before this replacement leaves a replayable queue item.
                write_jsonl(data / "pending.jsonl", queue[1:])
                queue.pop(0)
                results.append({"key": record["fields"]["Key"], **result})
        except (Error, OSError, ValueError, KeyError, TypeError) as exc:
            return {"status": "pending", "confirmed": len(results), "pending": len(queue),
                    "reason": str(exc), "results": results}
        return {"status": "synced", "confirmed": len(results), "pending": 0, "results": results}


def initialize(root):
    with locked(root):
        cfg = config(root)
        api = Anki(cfg)
        version = api.call("version")
        profile = api.call("getActiveProfile")
        if cfg.get("expected_profile") and cfg["expected_profile"] != profile:
            raise Error("Profile differs from configured profile; no writes performed")
        if not cfg.get("expected_profile"):
            cfg.update({"endpoint": "http://127.0.0.1:8765", "expected_profile": profile,
                        "timeout_seconds": 8, "api_key_env": "ANKICONNECT_API_KEY"})
            durable_replace(Path(root) / "config.json", json.dumps(cfg, indent=2) + "\n")
        ensure_model(api)
        return {"status": "ready", "api_version": version, "profile": profile,
                "deck": NAME, "note_type": NAME, "fields": FIELDS}


def status(root):
    with locked(root) as data:
        queue = read_jsonl(data / "pending.jsonl")
        cfg = config(root)
        api = Anki(cfg)
        result = {"pending": len(queue), "configured_profile": cfg.get("expected_profile")}
        try:
            result.update({"api_version": api.call("version"), "active_profile": api.call("getActiveProfile"),
                           "target_deck_exists": NAME in api.call("deckNames"),
                           "target_model_exists": NAME in api.call("modelNames"), "status": "available"})
        except Error as exc:
            result.update({"status": "unavailable", "reason": str(exc)})
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--init", action="store_true", help="Bind current profile and create missing deck/model")
    group.add_argument("--status", action="store_true", help="Read-only API check")
    args = parser.parse_args()
    try:
        result = initialize(args.root) if args.init else status(args.root) if args.status else synchronize(args.root)
        print(json.dumps(result, ensure_ascii=False))
        return 2 if result["status"] in ("pending", "unavailable") else 0
    except (Error, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
