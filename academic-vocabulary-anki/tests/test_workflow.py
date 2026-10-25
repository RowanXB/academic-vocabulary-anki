import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
from common import (Anki, Error, Unavailable, FIELDS, NAME, check_record, durable_replace,
                    encode_fields, locked, make_key, read_jsonl, templates, validate, write_jsonl)
from intake import enqueue
from lookup import lookup
from sync import synchronize

EXAMPLES = json.loads((SKILL / "evals/live-examples.json").read_text())


class FakeAnki:
    """Stateful API double: no socket, no real collection, no HTTP server."""
    def __init__(self):
        self.notes = {}
        self.models = []
        self.decks = ["Unrelated"]
        self.card_templates = {}
        self.fields = FIELDS[:]
        self.profile = "Test"
        self.offline = False
        self.lose_add_response = False
        self.lose_update_response = False
        self.actions = []
        self.foreign_deck = False

    def call(self, action, **params):
        self.actions.append((action, params))
        if self.offline:
            raise Unavailable("offline")
        if action == "version":
            return 6
        if action == "getActiveProfile":
            return self.profile
        if action == "modelNames":
            return self.models[:]
        if action == "deckNames":
            return self.decks[:]
        if action == "createDeck":
            self.decks.append(params["deck"])
            return 42
        if action == "createModel":
            self.models.append(params["modelName"])
            self.fields = params["inOrderFields"][:]
            self.card_templates = {t["Name"]: {"Front": t["Front"], "Back": t["Back"]} for t in params["cardTemplates"]}
            return {"id": 42}
        if action == "modelFieldNames":
            return self.fields[:]
        if action == "modelTemplates":
            return copy.deepcopy(self.card_templates)
        if action == "findNotes":
            return [nid for nid, note in self.notes.items() if "Key:" not in params["query"] or note["fields"]["Key"]["value"] in params["query"]]
        if action == "notesInfo":
            return [copy.deepcopy(self.notes.get(nid, {})) for nid in params["notes"]]
        if action == "cardsInfo":
            return [{"cardId": cid, "deckName": "Unrelated" if self.foreign_deck else NAME,
                     "ord": cid % 10, "reps": 7, "interval": 20} for cid in params["cards"]]
        if action == "addNote":
            note = params["note"]
            assert note["options"]["allowDuplicate"] is False
            assert note["deckName"] == NAME
            if any(n["fields"]["Key"]["value"] == note["fields"]["Key"] for n in self.notes.values()):
                raise Error("duplicate")
            nid = len(self.notes) + 1
            self.notes[nid] = {"noteId": nid, "modelName": NAME, "tags": note["tags"][:],
                               "fields": {k: {"value": v, "order": FIELDS.index(k)} for k, v in note["fields"].items()},
                               "cards": [nid * 10 + i for i, flag in enumerate(("Receptive", "Productive")) if note["fields"][flag]]}
            if self.lose_add_response:
                self.lose_add_response = False
                raise Unavailable("committed, response lost")
            return nid
        if action == "updateNoteFields":
            for k, value in params["note"]["fields"].items():
                self.notes[params["note"]["id"]]["fields"][k]["value"] = value
            if self.lose_update_response:
                self.lose_update_response = False
                raise Unavailable("update committed, response lost")
            return None
        if action == "addTags":
            for nid in params["notes"]:
                self.notes[nid]["tags"] = sorted(set(self.notes[nid]["tags"]) | set(params["tags"].split()))
            return None
        raise AssertionError(action)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "config.json").write_text(json.dumps({"expected_profile": "Test"}))
        self.api = FakeAnki()
        self.raw = copy.deepcopy(EXAMPLES[0])

    def tearDown(self):
        self.temp.cleanup()

    def pending(self):
        return read_jsonl(self.root / "data/pending.jsonl")

    def run_sync(self):
        return synchronize(self.root, self.api)

    def add(self):
        enqueue(self.root, [self.raw])
        result = self.run_sync()
        self.assertEqual(result["status"], "synced", result)

    def test_single_word_generated_fixture(self):
        raw = json.loads((SKILL / "evals/single-word.json").read_text())
        result = validate(raw)
        self.assertEqual(result["fields"]["Prompt"], "Additional statistical controls may _____ the observed association.")
        self.assertEqual(result["fields"]["Productive"], "1")
        self.assertEqual(result["fields"]["Receptive"], "")
        self.assertIn("context_generated", result["tags"])

    def test_preserves_user_context_and_inflection(self):
        record = validate(self.raw)
        self.assertEqual(record["fields"]["Context"], self.raw["original_context"])
        self.assertEqual(record["fields"]["Prompt"], "The effect was _____ after controlling for age.")
        self.assertEqual(record["fields"]["Answer"], "attenuated")
        self.assertEqual(list(record["fields"]), FIELDS)
        check_record(record)

    def test_exact_duplicates_enqueue_once(self):
        self.assertEqual(enqueue(self.root, [self.raw, self.raw])["enqueued"], 1)
        self.assertEqual(enqueue(self.root, [self.raw])["enqueued"], 0)
        self.assertEqual(len(self.pending()), 1)

    def test_offline_then_online(self):
        enqueue(self.root, [self.raw])
        before = (self.root / "data/pending.jsonl").read_bytes()
        self.api.offline = True
        self.assertEqual(self.run_sync()["status"], "pending")
        self.assertEqual((self.root / "data/pending.jsonl").read_bytes(), before)
        self.api.offline = False
        self.assertEqual(self.run_sync()["confirmed"], 1)
        self.assertEqual(self.pending(), [])

    def test_lost_add_response_then_retry(self):
        enqueue(self.root, [self.raw])
        self.api.lose_add_response = True
        self.assertEqual(self.run_sync()["status"], "pending")
        self.assertEqual(len(self.api.notes), 1)
        self.assertEqual(self.run_sync()["status"], "synced")
        self.assertEqual(len(self.api.notes), 1)
        self.assertEqual(sum(a == "addNote" for a, _ in self.api.actions), 1)

    def test_crash_after_receipt_before_queue_removal(self):
        enqueue(self.root, [self.raw])
        original = write_jsonl
        def crash(path, rows):
            if path.name == "pending.jsonl":
                raise OSError("simulated disk interruption")
            original(path, rows)
        with patch("sync.write_jsonl", side_effect=crash):
            self.assertEqual(self.run_sync()["status"], "pending")
        self.assertEqual(len(self.pending()), 1)
        self.assertEqual(self.run_sync()["status"], "synced")
        self.assertEqual(len(self.api.notes), 1)
        self.assertEqual(len(read_jsonl(self.root / "data/history.jsonl")), 1)

    def test_repeated_sync_and_reintake_idempotent(self):
        self.add()
        first = copy.deepcopy(self.api.notes)
        self.assertEqual(self.run_sync()["confirmed"], 0)
        enqueue(self.root, [self.raw])
        self.assertEqual(self.run_sync()["results"][0]["disposition"], "existing")
        self.assertEqual(first, self.api.notes)

    def test_same_sense_new_context_preserves_valid_content(self):
        self.add()
        first = copy.deepcopy(self.api.notes)
        newer = json.loads((SKILL / "evals/single-word.json").read_text())
        enqueue(self.root, [newer])
        result = self.run_sync()
        self.assertTrue(result["results"][0]["preserved_existing_context"])
        self.assertEqual(first, self.api.notes)
        self.assertEqual(len(read_jsonl(self.root / "data/history.jsonl")), 2)

    def test_manual_edits_and_flags_preserved(self):
        self.add()
        self.api.notes[1]["fields"]["Definition"]["value"] = "My carefully edited definition."
        self.api.notes[1]["fields"]["Collocation"]["value"] = "my own phrase"
        self.raw["fields"]["Receptive"] = "1"
        enqueue(self.root, [self.raw])
        self.assertEqual(self.run_sync()["status"], "synced")
        self.assertEqual(self.api.notes[1]["fields"]["Definition"]["value"], "My carefully edited definition.")
        self.assertEqual(self.api.notes[1]["fields"]["Receptive"]["value"], "")
        self.assertEqual(self.api.notes[1]["cards"], [11])

    def test_blank_enrichment_and_lost_update_response(self):
        self.add()
        self.api.notes[1]["fields"]["IPA"]["value"] = ""
        self.api.lose_update_response = True
        enqueue(self.root, [self.raw])
        self.assertEqual(self.run_sync()["status"], "pending")
        self.assertEqual(self.run_sync()["status"], "synced")
        self.assertEqual(self.api.notes[1]["fields"]["IPA"]["value"], self.raw["fields"]["IPA"])

    def test_context_fields_not_mixed(self):
        self.add()
        self.api.notes[1]["fields"]["Hint"]["value"] = ""
        newer = json.loads((SKILL / "evals/single-word.json").read_text())
        enqueue(self.root, [newer])
        self.assertEqual(self.run_sync()["status"], "synced")
        self.assertEqual(self.api.notes[1]["fields"]["Hint"]["value"], "")

    def test_new_sense_new_key(self):
        other = copy.deepcopy(self.raw)
        other["sense"] = "make-long-and-thin"
        other["fields"].update(Definition="To make something longer and thinner.", Context="The artist attenuated the limbs in the drawing.")
        other["original_context"] = other["fields"]["Context"]
        enqueue(self.root, [self.raw, other])
        self.assertEqual(self.run_sync()["confirmed"], 2)
        self.assertEqual(len(self.api.notes), 2)

    def test_profile_mismatch_no_writes(self):
        enqueue(self.root, [self.raw])
        self.api.profile = "Other"
        self.assertEqual(self.run_sync()["status"], "pending")
        self.assertFalse(any(a.startswith("create") or a.startswith("add") for a, _ in self.api.actions))

    def test_model_mismatch_does_not_overwrite(self):
        self.add()
        self.api.fields.reverse()
        enqueue(self.root, [self.raw])
        self.assertEqual(self.run_sync()["status"], "pending")
        self.assertEqual(self.api.fields, list(reversed(FIELDS)))

    def test_template_mismatch_does_not_overwrite(self):
        self.add()
        self.api.card_templates["Productive"]["Front"] = "Custom template"
        enqueue(self.root, [self.raw])
        self.assertEqual(self.run_sync()["status"], "pending")
        self.assertEqual(self.api.card_templates["Productive"]["Front"], "Custom template")

    def test_foreign_deck_untouched(self):
        self.add()
        self.api.foreign_deck = True
        previous = copy.deepcopy(self.api.notes)
        enqueue(self.root, [self.raw])
        self.assertEqual(self.run_sync()["status"], "pending")
        self.assertEqual(self.api.notes, previous)

    def test_whole_batch_validation_is_atomic(self):
        bad = copy.deepcopy(self.raw)
        bad["fields"]["Answer"] = "missing"
        with self.assertRaises(Error):
            enqueue(self.root, [self.raw, bad])
        self.assertFalse((self.root / "data/pending.jsonl").exists())

    def test_answer_leaks_rejected(self):
        for field in ("Definition", "Hint"):
            with self.subTest(field=field):
                bad = copy.deepcopy(self.raw)
                bad["fields"][field] = "Use attenuate here."
                with self.assertRaises(Error):
                    validate(bad)

    def test_changed_original_rejected(self):
        self.raw["fields"]["Context"] = "The effect was attenuated after controlling for sex."
        with self.assertRaises(Error):
            validate(self.raw)

    def test_wrong_prompt_and_flags_rejected(self):
        for field, value in (("Prompt", "Wrong prompt"), ("Productive", True), ("Receptive", "0")):
            with self.subTest(field=field):
                raw = copy.deepcopy(self.raw)
                raw["fields"][field] = value
                with self.assertRaises(Error):
                    validate(raw)

    def test_ipa_requires_source(self):
        self.raw.pop("ipa_source")
        with self.assertRaises(Error):
            validate(self.raw)

    def test_html_escaped_without_changing_cached_context(self):
        self.raw["fields"]["Context"] = "The effect was attenuated when p < 0.05 & n > 20."
        self.raw["original_context"] = self.raw["fields"]["Context"]
        self.add()
        self.assertIn("&lt;", self.api.notes[1]["fields"]["Context"]["value"])
        history = read_jsonl(self.root / "data/history.jsonl")
        self.assertEqual(history[0]["record"]["original_context"], self.raw["original_context"])

    def test_corrupted_queue_preserved(self):
        enqueue(self.root, [self.raw])
        path = self.root / "data/pending.jsonl"
        with path.open("a") as stream:
            stream.write('{"broken":')
        before = path.read_bytes()
        with self.assertRaises(Error):
            self.run_sync()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.api.actions, [])

    def test_tampered_record_rejected(self):
        enqueue(self.root, [self.raw])
        rows = self.pending()
        rows[0]["fields"]["Definition"] = "Changed outside intake"
        write_jsonl(self.root / "data/pending.jsonl", rows)
        with self.assertRaises(Error):
            self.run_sync()
        self.assertEqual(self.api.actions, [])

    def test_atomic_replace_failure_preserves_original(self):
        path = self.root / "atomic.jsonl"
        durable_replace(path, "original\n")
        with patch("common.os.replace", side_effect=OSError("simulated failure")):
            with self.assertRaises(OSError):
                durable_replace(path, "new\n")
        self.assertEqual(path.read_text(), "original\n")

    def test_lock_excludes_other_process(self):
        with locked(self.root):
            result = subprocess.run([sys.executable, str(SKILL / "scripts/intake.py"), str(SKILL / "evals/single-word.json"), "--root", str(self.root), "--no-sync"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Another intake/sync", result.stdout)

    def test_cli_jsonl_and_status(self):
        result = subprocess.run([sys.executable, str(SKILL / "scripts/intake.py"), "--root", str(self.root), "--no-sync"], input=json.dumps(self.raw) + "\n" + json.dumps(EXAMPLES[1]), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "saved_pending")
        self.assertEqual(len(self.pending()), 2)
        self.assertEqual((self.root / "data/pending.jsonl").stat().st_mode & 0o777, 0o600)

    def test_lookup_offline_retains_sense_and_context(self):
        self.add()
        result = lookup(self.root, " ATTENUATE ", offline=True)
        self.assertEqual(result["local_records"][0]["sense"], "reduce-strength")

    def test_all_card_modes_and_template_contract(self):
        enqueue(self.root, EXAMPLES)
        self.assertEqual(self.run_sync()["status"], "synced")
        self.assertEqual([len(n["cards"]) for n in self.api.notes.values()], [1, 1, 2])
        for t in templates():
            flag = t["Name"]
            self.assertTrue(t["Front"].strip().startswith("{{#" + flag + "}}"))
            self.assertTrue(t["Front"].strip().endswith("{{/" + flag + "}}"))
            self.assertNotIn("{{tts", t["Front"])
        productive = templates()[1]
        self.assertIn("{{hint:Hint}}", productive["Front"])
        self.assertNotIn("{{Term}}", productive["Front"])
        self.assertIn("{{tts en_US:Answer}}", productive["Back"])

    def test_http_response_uncertainty(self):
        api = Anki({"timeout_seconds": 1})
        with patch.object(api.opener, "open", side_effect=TimeoutError):
            with self.assertRaises(Unavailable):
                api.call("version")

    def test_partial_batch_failure_keeps_unconfirmed_only(self):
        enqueue(self.root, EXAMPLES)
        real_call = self.api.call
        def fail_second(action, **params):
            if action == "addNote" and len(self.api.notes) == 1:
                raise Unavailable("outage")
            return real_call(action, **params)
        with patch.object(self.api, "call", side_effect=fail_second):
            result = self.run_sync()
        self.assertEqual(result["confirmed"], 1)
        self.assertEqual(result["pending"], 2)
        self.assertEqual(self.run_sync()["confirmed"], 2)
        self.assertEqual(len(self.api.notes), 3)

    def test_anki_existing_tag_capitalization(self):
        self.add()
        self.api.notes[1]["tags"] = ["academic", "context_user", "Statistics"]
        previous = len(self.api.actions)
        enqueue(self.root, [self.raw])
        self.assertEqual(self.run_sync()["status"], "synced")
        self.assertFalse(any(a == "addTags" for a, _ in self.api.actions[previous:]))

    def test_missing_generated_card_retains_queue(self):
        self.add()
        self.api.notes[1]["cards"] = [10]
        enqueue(self.root, [self.raw])
        self.assertEqual(self.run_sync()["status"], "pending")
        self.assertEqual(len(self.pending()), 1)


if __name__ == "__main__":
    unittest.main()
