# Operations

This guide covers daily use, maintenance and troubleshooting after [installation](setup.md).

Paths and commands follow [setup.md](setup.md#requirements): `<skill-dir>` is the directory the skill was installed in, and on Windows `py -3` replaces `python3`.

## Daily use

### Start collecting

To put a chat in collection mode, so that every word you send is saved, send this once: `Use academic-vocabulary-anki and treat this chat as a vocabulary collection chat. Save every word I send from now on to Anki automatically.` (In Codex you can write `$academic-vocabulary-anki`; in Claude Code you can use `/academic-vocabulary-anki`.) Saying the same thing in your own words, in any language, also works. After that, just send words or screenshots, and say that you want to stop when you are done. In a screenshot or pasted text of a sentence or passage, name the words to save in your message, or highlight, underline or circle just those words; otherwise the agent asks which ones you mean. If you name words, only those are saved unless you also point to your marks.

You can also save particular words without collection mode or the skill name, in any wording or language, for example “把 attenuate 记下来” or `save this word: attenuate`. SKILL.md, under "Conversation behavior", defines exactly what each request saves, including how meaning questions are handled.

Automatic skill discovery is model behavior and cannot be guaranteed every time; naming the skill, as above, is the most reliable. The project has no resident background process, and opening Anki does not trigger a catch-up sync; pending records are retried on the next collected word or sync run.

### Script commands

The skill runs these for you; they are listed for checks and manual recovery.

```sh
python3 <skill-dir>/scripts/sync.py --status
python3 <skill-dir>/scripts/sync.py
python3 <skill-dir>/scripts/lookup.py attenuate
python3 <skill-dir>/scripts/intake.py records.json
python3 -m unittest discover -s <skill-dir>/tests -v
```

The model generates the structured data; the scripts contain no AI API and do not accept a bare word to generate definitions themselves. `--root PATH` isolates test data or points to another data directory explicitly; it does not change the Anki target names or the localhost address.

## Maintenance

### Back up or move to another computer

Back up the whole `<skill-dir>`, especially `config.json`, `data/pending.jsonl` and `data/history.jsonl`. These files are ignored by Git, so a fresh clone does not contain them.

### Switch or clear Anki profiles

Switching profiles requires you to review and edit `expected_profile` in `config.json` deliberately; do not mix profiles in one queue.

If you clear the current profile yourself: keep the local project first; after clearing, run `sync.py --init` to rebuild the target structure. History is not re-imported automatically; only pending records are processed on the next sync. When creating a profile with a different name, first confirm that the queued records belong to the new profile, then set `expected_profile` in config.json to that profile's exact name and initialize. Do not change the binding automatically just because the API reports a different profile. Clearing Anki and clearing the local vocabulary history are two separate operations.

## Troubleshooting

- `pending` with `"retry": "after_fix"`: the queue is blocked at the first failing record, and later records wait behind it. Fix the cause named in `reason` (see the entries below), then run `sync.py` again.
- `pending`: the content is still in data/pending.jsonl. Open or wake Anki, finish any open dialog, then sync again. macOS can also put background apps to sleep and cause a temporary timeout; wake Anki and retry, without changing system settings automatically.
- Windows: IPA or other non-ASCII text arrives replaced or approximated (for example `ə` → `?`, `ˈ` → `'`): Windows PowerShell 5.1 encodes text piped into another program as ASCII, and `Set-Content` without `-Encoding UTF8` writes the system code page. Pass records to `intake.py` as a file written in UTF-8 (with or without a BOM) or UTF-16 with a BOM, such as `Out-File`'s default; other encodings fail without saving anything. Intake also rejects the whole batch when an IPA contains `?`, since IPA never uses it; other fields can legitimately contain `?` and are not checked.
- Script output shows `\u0259` instead of `ə`: this is intended. The scripts print ASCII-only JSON so that no console code page can corrupt it; any JSON parser restores the original characters.
- Windows "file in use" or permission errors while saving: another program, such as antivirus or an editor, has a file in `data/` open. Close it and retry; records already saved stay pending until the next sync.
- `failed`: read the JSON error. If `saved_pending` was printed earlier, the cache is still saved; otherwise do not assume anything was saved. A corrupted JSONL file stops processing and the original file is kept; bad lines are never dropped automatically.
- Duplicate sense: run lookup first and reuse the sense. The scripts only guarantee idempotency for a stable Key; comparing meanings is the AI's job. Renaming a sense must not be used to bypass deduplication.
- Existing content: only completely empty compatible fields are filled; manual text, review history, card flags and existing CSS are never overwritten. Replacing an old context or enabling another card direction is a separate, explicit edit. Do not edit the same note or switch profiles in Anki while syncing; AnkiConnect has no atomic conditional update across requests.
- A card with the same Key was moved to another deck: sync stops and waits for manual review; it never moves the card back or modifies other decks.
- "Card templates are from an earlier version of this skill": run `sync.py --init` once to upgrade them; nothing else changes.
- Field or template mismatch: sync stops for manual review; user templates are never overwritten automatically. CSS can be adjusted freely and does not affect the script checks.
- The `context_user`/`context_generated` tags describe the context currently stored in Anki; a new original sentence from a repeated input is kept in history instead of pretending Anki's context was replaced.
- Anki's native tags are case-insensitive and may reuse an existing spelling such as `Statistics`; the scripts compare tags by the same rule and never rename tags across the collection.
- Anki quits unexpectedly on macOS (crash report: `EXC_BAD_ACCESS` on `CrBrowserMain` inside `libqcocoa` accessibility calls): a known Qt defect (QTBUG-149612; see the [Anki forum report](https://forums.ankiweb.net/t/macos-accessibility-scan-can-crash-browse-when-a-row-is-selected/70882)) crashes Anki when the Browse window has a selected row while an accessibility client, such as an agent's computer-use service or screen monitoring, reads the window. It is not caused by this skill and does not damage the collection; the skill never opens Browse itself. Until a fixed Anki release is available, close Browse (or leave no row selected) when you are not using it, especially while computer-use tools are running.
- Distorted or novelty-sounding pronunciation on macOS: Anki picked a novelty voice such as Albert. The templates prefer Samantha (macOS) and Zira or David (Windows); if the note type predates this, run `sync.py --init` to upgrade it.
- An empty IPA is a deliberate "not verified" state. TTS uses the device's built-in en_US voice: on desktop, install an American English voice in the macOS or Windows speech settings and restart Anki. The templates list preferred voices (Samantha, Zira, David); on a device without them, such as a phone, Anki falls back to its first en_US voice.
- iOS/Android: sync the deck through your existing AnkiWeb sync and configure an en_US TTS engine or voice on the device. The scripts import into the local collection only and never run a full AnkiWeb sync. Actual mobile display and playback still need to be checked on each device.
