#!/usr/bin/env python3
"""Validate JSON/JSONL vocabulary records, durably enqueue, then optionally sync."""
import argparse
import json
from pathlib import Path
import sys
from common import Error, ROOT, check_record, locked, read_jsonl, validate, write_jsonl


def enqueue(root, raw_records):
    # Validate the whole batch before touching storage.
    records = [validate(raw) for raw in raw_records]
    if not records:
        raise Error("No vocabulary records supplied")
    with locked(root) as data:
        queue = read_jsonl(data / "pending.jsonl")
        for record in queue:
            check_record(record)
        known = {r["id"] for r in queue}
        added = 0
        for record in records:
            if record["id"] not in known:
                queue.append(record)
                known.add(record["id"])
                added += 1
        write_jsonl(data / "pending.jsonl", queue)
    return {"status": "saved_pending", "received": len(records), "enqueued": added,
            "pending": len(queue), "keys": [r["fields"]["Key"] for r in records]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", default="-", help="JSON object/array or JSONL; '-' reads stdin")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--no-sync", action="store_true")
    args = parser.parse_args()
    try:
        source = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
        try:
            raw = json.loads(source)
            records = raw if isinstance(raw, list) else [raw]
        except json.JSONDecodeError:
            records = [json.loads(line) for line in source.splitlines() if line.strip()]
        result = enqueue(args.root, records)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if not args.no_sync:
            from sync import synchronize
            synced = synchronize(args.root)
            print(json.dumps(synced, ensure_ascii=False))
            return 0 if synced["status"] == "synced" else 2
        return 0
    except (Error, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
