#!/usr/bin/env python3
"""Show known senses locally and in the configured Anki profile before generation."""
import argparse
import json
from pathlib import Path
import sys
from common import Anki, Error, NAME, ROOT, check_profile, config, locked, normalized, plain, read_jsonl


def lookup(root, term, offline=False):
    match = normalized(term)
    with locked(root) as data:
        records = read_jsonl(data / "pending.jsonl")
        records += [h["record"] for h in read_jsonl(data / "history.jsonl")]
    local = {r["id"]: r for r in records if normalized(r["fields"]["Term"]) == match}
    result = {"term": term, "local_records": list(local.values()), "anki_notes": [], "anki_status": "not_checked"}
    if not offline:
        try:
            cfg = config(root)
            api = Anki(cfg)
            check_profile(api, cfg)
            if NAME in api.call("modelNames"):
                ids = api.call("findNotes", query=f'"note:{NAME}"')
                for start in range(0, len(ids), 100):
                    for n in api.call("notesInfo", notes=ids[start:start + 100]):
                        if n and "Term" in n["fields"] and normalized(plain(n["fields"]["Term"]["value"])) == match:
                            result["anki_notes"].append(n)
            result["anki_status"] = "checked"
        except Error as exc:
            result.update({"anki_status": "unavailable", "reason": str(exc)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("term")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(lookup(args.root, args.term, args.offline)))
        return 0
    except (Error, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
