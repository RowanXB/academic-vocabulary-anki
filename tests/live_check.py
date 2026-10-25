#!/usr/bin/env python3
"""Explicit live integration check; writes three useful examples only to the target deck."""
import argparse
import json
from pathlib import Path
import sys

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
from common import Anki, NAME, ROOT, FIELDS, config, plain
from intake import enqueue
from sync import initialize, synchronize


def run(root):
    cfg = config(root)
    api = Anki(cfg)
    ready = initialize(root)
    examples = json.loads((SKILL / "evals/live-examples.json").read_text())
    enqueue(root, examples)
    first = synchronize(root)
    assert first["status"] == "synced", first
    ids = [r["note_id"] for r in first["results"]]
    notes = api.call("notesInfo", notes=ids)
    cards = api.call("cardsInfo", cards=[cid for n in notes for cid in n["cards"]])
    by_note = {n["noteId"]: [c for c in cards if c["note"] == n["noteId"]] for n in notes}
    counts = [len(by_note[nid]) for nid in ids]
    assert counts == [1, 1, 2], counts
    assert [{c["ord"] for c in by_note[nid]} for nid in ids] == [{1}, {0}, {0, 1}]
    assert api.call("modelFieldNames", modelName=NAME) == FIELDS
    assert notes[0]["fields"]["Context"]["value"] == examples[0]["original_context"]
    assert notes[0]["fields"]["Answer"]["value"] == "attenuated"
    for c in cards:
        question = c["question"].split("</style>")[-1]
        assert c["deckName"] == NAME
        assert "[anki:tts" not in question
        if c["ord"] == 1:
            assert "_____" in question
            assert "hint" in question
            assert c["fields"]["Answer"]["value"].casefold() not in plain(question).casefold()
        assert c["fields"]["IPA"]["value"] in c["answer"]
        # AnkiConnect returns either native TTS markers or rendered playback controls.
        assert any(marker in c["answer"] for marker in ("[anki:tts", "replay-button", "playsound")), c["answer"]
    before_reviews = [{k: c[k] for k in ("cardId", "reps", "lapses", "interval", "due", "queue")} for c in cards]
    enqueue(root, examples)
    repeated = synchronize(root)
    assert repeated["status"] == "synced", repeated
    assert all(r["disposition"] == "existing" for r in repeated["results"])
    again = api.call("cardsInfo", cards=[c["cardId"] for c in cards])
    assert before_reviews == [{k: c[k] for k in before_reviews[0]} for c in again]
    assert synchronize(root)["confirmed"] == 0
    for record in first["results"]:
        assert api.call("findNotes", query=f'"note:{NAME}" "Key:{record["key"]}"') == [record["note_id"]]
    return {"status": "passed", "ready": ready, "notes": ids, "cards": [c["cardId"] for c in cards],
            "card_counts": counts,
            "review_state_unchanged_on_retry": True, "repeat_sync": repeated,
            "tts": "native markup/playback controls rendered; audibility requires UI/device check"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write-examples", action="store_true", required=True,
                        help="Required: explicitly write the three example notes")
    args = parser.parse_args()
    print(json.dumps(run(args.root), ensure_ascii=False, indent=2))
