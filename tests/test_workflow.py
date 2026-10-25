import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
import common
from common import (Anki, Error, Unavailable, FIELDS, NAME, check_record, durable_replace,
                    encode_fields, locked, make_key, read_jsonl, templates, validate, write_jsonl)
from intake import enqueue
from lookup import lookup
from sync import synchronize

EXAMPLES = json.loads((SKILL / "evals/live-examples.json").read_text(encoding="utf-8"))


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
        raw = json.loads((SKILL / "evals/single-word.json").read_text(encoding="utf-8"))
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

    def test_repeated_answer_blanks_all_occurrences_in_every_card_mode(self):
        context = "The effect was attenuated, but it was not attenuated equally across groups."
        self.raw["fields"]["Context"] = self.raw["original_context"] = context
        self.raw["answer_start"] = context.index("attenuated")
        for receptive, productive in (("", "1"), ("1", ""), ("1", "1")):
            with self.subTest(receptive=receptive, productive=productive):
                self.raw["fields"].update(Receptive=receptive, Productive=productive)
                record = validate(self.raw)
                self.assertEqual(record["fields"]["Context"], context)
                self.assertEqual(record["fields"]["Answer"], "attenuated")
                self.assertEqual(record["fields"]["Prompt"],
                                 "The effect was _____, but it was not _____ equally across groups.")
                check_record(record)

    def test_repeated_answer_offline_recovery_and_lost_response_remain_idempotent(self):
        context = "The effect was attenuated, but it was not attenuated equally across groups."
        self.raw["fields"]["Context"] = self.raw["original_context"] = context
        enqueue(self.root, [self.raw])
        self.api.offline = True
        self.assertEqual(self.run_sync()["pending"], 1)
        self.api.offline = False
        self.api.lose_add_response = True
        self.assertEqual(self.run_sync()["pending"], 1)
        self.assertEqual(self.run_sync()["confirmed"], 1)
        enqueue(self.root, [self.raw])
        self.assertEqual(self.run_sync()["results"][0]["disposition"], "existing")
        self.assertEqual(len(self.api.notes), 1)
        self.assertEqual(len(self.api.notes[1]["cards"]), 1)
        self.assertEqual(self.api.notes[1]["fields"]["Prompt"]["value"].count("_____"), 2)
        self.assertEqual(self.pending(), [])

    def test_repeated_answer_rejects_partially_blank_prompt(self):
        context = "The effect was attenuated, but it was not attenuated equally across groups."
        self.raw["fields"]["Context"] = self.raw["original_context"] = context
        self.raw["fields"]["Prompt"] = "The effect was _____, but it was not attenuated equally across groups."
        with self.assertRaisesRegex(Error, "selected answer spans"):
            validate(self.raw)

    def test_repeated_phrase_preserves_word_boundaries(self):
        raw = copy.deepcopy(EXAMPLES[1])
        raw["fields"]["Context"] = "We studied anterograde amnesia and anterograde amnesia, not anterograde amnesias."
        record = validate(raw)
        self.assertEqual(record["fields"]["Prompt"],
                         "We studied _____ and _____, not anterograde amnesias.")

    def test_other_target_forms_still_cannot_leak_from_productive_prompt(self):
        context = "The effect was attenuated, and this may attenuate later responses."
        self.raw["fields"]["Context"] = self.raw["original_context"] = context
        with self.assertRaisesRegex(Error, "Prompt leaks a target form"):
            validate(self.raw)
        self.raw["fields"].update(Receptive="1", Productive="")
        self.assertEqual(validate(self.raw)["fields"]["Context"], context)

    def test_model_selects_different_forms_and_script_numbers_them_in_context_order(self):
        context = "The intervention may attenuate the response, as it attenuated earlier responses."
        self.raw["fields"]["Context"] = self.raw["original_context"] = context
        self.raw["fields"].pop("Answer")
        self.raw["fields"]["Hint"] = "verb; starts with a; use the form required by each clause"
        self.raw["answer_spans"] = [{"text": "attenuated", "occurrence": 1},
                                    {"text": "attenuate", "occurrence": 1}]
        record = validate(self.raw)
        self.assertEqual(record["fields"]["Prompt"],
                         "The intervention may _____ (1) the response, as it _____ (2) earlier responses.")
        self.assertEqual(record["fields"]["Answer"], "1. attenuate\n2. attenuated")
        self.assertEqual(record["fields"]["Context"], context)
        self.assertEqual(record["answer_spans"][0]["text"], "attenuate")
        check_record(record)
        enqueue(self.root, [self.raw])
        self.api.lose_add_response = True
        self.assertEqual(self.run_sync()["pending"], 1)
        self.assertEqual(self.run_sync()["confirmed"], 1)
        enqueue(self.root, [self.raw])
        self.assertEqual(self.run_sync()["results"][0]["disposition"], "existing")
        self.assertEqual(len(self.api.notes), 1)
        self.assertEqual(len(self.api.notes[1]["cards"]), 1)
        self.assertEqual(self.api.notes[1]["fields"]["Answer"]["value"], "1. attenuate<br>2. attenuated")

    def test_model_selected_repeated_form_uses_one_shared_answer(self):
        context = "The effect was attenuated, but it was not attenuated equally across groups."
        self.raw["fields"]["Context"] = self.raw["original_context"] = context
        self.raw["answer_spans"] = [{"text": "attenuated", "occurrence": 1},
                                    {"text": "attenuated", "occurrence": 2}]
        record = validate(self.raw)
        self.assertEqual(record["fields"]["Answer"], "attenuated")
        self.assertEqual(record["fields"]["Prompt"].count("_____"), 2)
        check_record(record)

    def test_invalid_model_selections_rejected_without_caching(self):
        invalid = [None, [], [{"text": "attenuated", "occurrence": True}],
                   [{"text": "attenuated", "occurrence": 0}],
                   [{"text": "attenuated", "occurrence": 2}],
                   [{"text": "Attenuated", "occurrence": 1}],
                   [{"text": "attenuated", "occurrence": 1, "extra": 1}],
                   [{"text": "attenuated", "occurrence": 1}] * 2,
                   [{"text": "was attenuated", "occurrence": 1},
                    {"text": "attenuated", "occurrence": 1}]]
        for spans in invalid:
            with self.subTest(spans=spans):
                self.raw["answer_spans"] = spans
                with self.assertRaises(Error):
                    enqueue(self.root, [self.raw])
                self.assertEqual(self.pending(), [])

    def test_model_cannot_leave_a_visible_copy_of_a_productive_answer(self):
        context = "The effect was attenuated, but it was not attenuated equally across groups."
        self.raw["fields"]["Context"] = self.raw["original_context"] = context
        self.raw["answer_spans"] = [{"text": "attenuated", "occurrence": 2}]
        with self.assertRaisesRegex(Error, "Prompt leaks a target form"):
            validate(self.raw)

    def test_model_supplied_answer_must_agree_with_selected_text(self):
        self.raw["answer_spans"] = [{"text": "attenuated", "occurrence": 1}]
        self.raw["fields"]["Answer"] = "attenuate"
        with self.assertRaisesRegex(Error, "Answer must match"):
            validate(self.raw)

    def test_oversized_derived_prompt_is_rejected_before_storage(self):
        raw = {"sense": "letter-symbol", "fields": {
            "Term": "a", "Definition": "The first selected symbol.",
            "Context": " ".join(["a", "b"] * 500), "Receptive": "1"},
            "context_origin": "generated", "tags": ["academic"],
            "answer_spans": [{"text": text, "occurrence": i}
                             for text in ("a", "b") for i in range(1, 501)]}
        with self.assertRaisesRegex(Error, "Derived Prompt or Answer exceeds"):
            enqueue(self.root, [raw])
        self.assertFalse((self.root / "data/pending.jsonl").exists())

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
        newer = json.loads((SKILL / "evals/single-word.json").read_text(encoding="utf-8"))
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
        newer = json.loads((SKILL / "evals/single-word.json").read_text(encoding="utf-8"))
        enqueue(self.root, [newer])
        self.assertEqual(self.run_sync()["status"], "synced")
        self.assertEqual(self.api.notes[1]["fields"]["Hint"]["value"], "")

    def test_receptive_supplement_cannot_leak_into_existing_productive_card(self):
        self.add()
        self.api.notes[1]["fields"]["Hint"]["value"] = ""
        self.raw["fields"].update(Receptive="1", Productive="", Hint="past participle: attenuated")
        enqueue(self.root, [self.raw])
        self.assertEqual(self.run_sync()["status"], "synced")
        self.assertEqual(self.api.notes[1]["fields"]["Productive"]["value"], "1")
        self.assertEqual(self.api.notes[1]["fields"]["Hint"]["value"], "")

    def test_context_provenance_restored_after_lost_update_response(self):
        self.add()
        self.api.notes[1]["fields"]["Context"]["value"] = ""
        self.api.notes[1]["tags"] = [t for t in self.api.notes[1]["tags"] if not t.startswith("context_")]
        self.api.lose_update_response = True
        enqueue(self.root, [self.raw])
        self.assertEqual(self.run_sync()["status"], "pending")
        self.assertEqual(self.run_sync()["status"], "synced")
        self.assertEqual(self.api.notes[1]["fields"]["Context"]["value"], self.raw["fields"]["Context"])
        self.assertIn("context_user", self.api.notes[1]["tags"])

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
        if os.name != "nt":  # Windows has no POSIX mode bits; the user profile ACL applies.
            self.assertEqual((self.root / "data/pending.jsonl").stat().st_mode & 0o777, 0o600)

    def test_windows_lock_excludes_second_holder(self):
        held = set()

        class FakeMsvcrt:
            LK_NBLCK, LK_UNLCK = 2, 0

            def locking(self, fd, mode, nbytes):
                identity = os.fstat(fd).st_ino
                if mode == self.LK_UNLCK:
                    held.discard(identity)
                elif identity in held:
                    raise PermissionError(13, "locked")
                else:
                    held.add(identity)

        with patch.object(common, "WINDOWS", True), patch.object(common, "msvcrt", FakeMsvcrt()):
            with locked(self.root):
                with self.assertRaisesRegex(Error, "Another intake/sync"):
                    with locked(self.root):
                        pass
            with locked(self.root):
                pass

    def test_windows_write_skips_directory_fsync(self):
        real_open = os.open

        def no_directory_open(path, flags, *args):
            if os.path.isdir(path):
                raise PermissionError(13, "directories cannot be opened on Windows")
            return real_open(path, flags, *args)

        path = self.root / "data/pending.jsonl"
        with patch.object(common.os, "open", no_directory_open):
            with patch.object(common, "WINDOWS", False), self.assertRaises(PermissionError):
                write_jsonl(path, [{"n": 1}])
            with patch.object(common, "WINDOWS", True):
                write_jsonl(path, [{"n": 2}])
        self.assertEqual(read_jsonl(path), [{"n": 2}])

    def test_cli_output_is_utf8_under_legacy_console_encoding(self):
        self.add()
        env = dict(os.environ, PYTHONIOENCODING="cp1252")
        result = subprocess.run([sys.executable, str(SKILL / "scripts/lookup.py"), "attenuate", "--root", str(self.root), "--offline"], capture_output=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        output = json.loads(result.stdout.decode("utf-8"))
        self.assertIn("ə", output["local_records"][0]["fields"]["IPA"])

    def test_intake_accepts_utf8_bom_from_windows_editors(self):
        source = self.root / "input.json"
        source.write_bytes(b"\xef\xbb\xbf" + json.dumps(self.raw, ensure_ascii=False).encode("utf-8"))
        result = subprocess.run([sys.executable, str(SKILL / "scripts/intake.py"), str(source), "--root", str(self.root), "--no-sync"], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout.decode("utf-8", "replace"))
        self.assertEqual(self.pending()[0]["fields"]["IPA"], self.raw["fields"]["IPA"])

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
