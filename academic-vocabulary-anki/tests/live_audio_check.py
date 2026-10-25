#!/usr/bin/env python3
"""Explicitly request native answer-side TTS in the target deck, without grading a card."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from common import Anki, NAME, ROOT, check_profile, config


def run():
    cfg = config(ROOT)
    api = Anki(cfg)
    check_profile(api, cfg)
    if api.call("guiReviewActive"):
        current = api.call("guiCurrentCard")
        if current["deckName"] != NAME:
            raise RuntimeError("Review of another deck is active; leaving it untouched")
    assert api.call("guiDeckReview", name=NAME)
    card = api.call("guiCurrentCard")
    assert card["deckName"] == NAME
    before = api.call("cardsInfo", cards=[card["cardId"]])[0]
    assert api.call("guiShowAnswer")
    dispatched = api.call("guiPlayAudio")
    assert dispatched
    after = api.call("cardsInfo", cards=[card["cardId"]])[0]
    assert all(before[k] == after[k] for k in ("reps", "lapses", "interval", "due", "queue"))
    return {"status": "playback_requested", "card_id": card["cardId"],
            "term": card["fields"]["Term"]["value"], "template": card["template"],
            "review_not_graded": True,
            "limitation": "Anki accepted native replay; speaker audibility and pronunciation quality are not measured"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--play", required=True, action="store_true")
    parser.parse_args()
    print(json.dumps(run(), ensure_ascii=False, indent=2))
