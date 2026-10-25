# Installation, usage and troubleshooting

Requirements: macOS, Python 3.9+, a local Anki installation and AnkiConnect. The scripts depend only on the Python standard library. macOS does not always ship with Python; check with `python3 --version`.

Default repository and skill location: `~/.agents/skills/academic-vocabulary-anki/`. `SKILL.md`, scripts, references and the rest sit directly in the repository root, together with the full Git history. `config.json` and runtime data live in the project root; when moving to another computer, back up the whole project directory, especially pending, history and config.

Each runtime reads the same repository through a symbolic link, so there is only one copy of the code:

| Runtime | Location it reads | How to install |
|---|---|---|
| Runtimes that follow the Agent Skills standard directory | `~/.agents/skills/academic-vocabulary-anki/` | The repository itself |
| Claude Code | `~/.claude/skills/academic-vocabulary-anki/` | Link to the repository root, or link the whole `~/.claude/skills` to `~/.agents/skills` |
| Codex | `~/.codex/skills/academic-vocabulary-anki/` | Link to the repository root |

New conversations load new skills; if the skill does not appear, restart that runtime or give it the path to SKILL.md explicitly. A local installation does not mean a cloud session has the skill or can reach this computer.

Clone the repository to the default location first, then add links only for the runtimes you actually use (if a target already exists, inspect it manually and do not overwrite it):

```sh
git clone https://github.com/RowanXB/academic-vocabulary-anki.git ~/.agents/skills/academic-vocabulary-anki
mkdir -p ~/.codex/skills
ln -s ~/.agents/skills/academic-vocabulary-anki ~/.codex/skills/academic-vocabulary-anki
mkdir -p ~/.claude/skills
ln -s ~/.agents/skills/academic-vocabulary-anki ~/.claude/skills/academic-vocabulary-anki
```

If `~/.claude/skills` is already a link to `~/.agents/skills`, skip the last two lines; otherwise `ln -s` creates a self-referencing link inside the repository.

In a chat dedicated to vocabulary, send this first: `Use academic-vocabulary-anki and treat this chat as a vocabulary collection chat. Save every word I send from now on to Anki automatically.` (In Codex you can write `$academic-vocabulary-anki`; in Claude Code you can use `/academic-vocabulary-anki`.) After that, just send words or screenshots. Automatic skill discovery is model behavior and cannot be guaranteed every time; enabling it explicitly once in a dedicated chat is the most reliable. The project has no resident background process, and opening Anki does not trigger a catch-up sync; pending records are retried on the next collected word or sync run.

First-time initialization (run once):

```sh
python3 ~/.agents/skills/academic-vocabulary-anki/scripts/sync.py --init
```

Initialization binds the current Anki profile, creates the missing target deck and note type, and checks fields and templates. If an incompatible structure with the same name already exists, it stops and never overwrites it. Switching profiles requires the user to review and edit `expected_profile` in the project config deliberately; do not mix profiles in one queue.

If you clear the current profile yourself: keep the local project first; after clearing, run `sync.py --init` to rebuild the target structure. History is not re-imported automatically; only pending records are processed on the next sync. When creating a profile with a different name, first confirm that the queued records belong to the new profile, then set `expected_profile` in config.json to that profile's exact name and initialize. Do not change the binding automatically just because the API reports a different profile. Clearing Anki and clearing the local vocabulary history are two separate operations.

Common commands:

```sh
python3 ~/.agents/skills/academic-vocabulary-anki/scripts/sync.py --status
python3 ~/.agents/skills/academic-vocabulary-anki/scripts/sync.py
python3 ~/.agents/skills/academic-vocabulary-anki/scripts/lookup.py attenuate
python3 ~/.agents/skills/academic-vocabulary-anki/scripts/intake.py records.json
python3 -m unittest discover -s ~/.agents/skills/academic-vocabulary-anki/tests -v
```

The model generates the structured data; the scripts contain no AI API and do not accept a bare word to generate definitions themselves. The skill handles that layer in everyday use. The default data directory is derived from the scripts' actual location. `--root PATH` isolates test data or points to another data directory explicitly; it does not change the Anki target names or the localhost address.

If AnkiConnect is not installed, enter the official code `2055492159` in Anki → Tools → Add-ons → Get Add-ons, then restart Anki. Keep the bind address `127.0.0.1` and port `8765`; no CORS wildcard and no relaxed security settings are needed. If the add-on has an API key enabled, pass it to the scripts through the `ANKICONNECT_API_KEY` environment variable; never put the key in notes, the skill or a chat.

Troubleshooting:

- `pending`: the content is still in data/pending.jsonl. Open or wake Anki, finish any open dialog, then sync again. macOS can also put background apps to sleep and cause a temporary timeout; wake Anki and retry, without changing system settings automatically.
- `failed`: read the JSON error. If `saved_pending` was printed earlier, the cache is still saved; otherwise do not assume anything was saved. A corrupted JSONL file stops processing and the original file is kept; bad lines are never dropped automatically.
- Duplicate sense: run lookup first and reuse the sense. The scripts only guarantee idempotency for a stable Key; comparing meanings is the AI's job. Renaming a sense must not be used to bypass deduplication.
- Existing content: only completely empty compatible fields are filled; manual text, review history, card flags and existing CSS are never overwritten. Replacing an old context or enabling another card direction is a separate, explicit edit. Do not edit the same note or switch profiles in Anki while syncing; AnkiConnect has no atomic conditional update across requests.
- A card with the same Key was moved to another deck: sync stops and waits for manual review; it never moves the card back or modifies other decks.
- Field or template mismatch: sync stops for manual review; user templates are never overwritten automatically. CSS can be adjusted freely and does not affect the script checks.
- The `context_user`/`context_generated` tags describe the context currently stored in Anki; a new original sentence from a repeated input is kept in history instead of pretending Anki's context was replaced.
- Anki's native tags are case-insensitive and may reuse an existing spelling such as `Statistics`; the scripts compare tags by the same rule and never rename tags across the collection.
- An empty IPA is a deliberate "not verified" state. TTS uses the device's built-in en_US voice: on desktop, install an American voice in the system speech settings and restart Anki. The templates do not pin a specific Apple voice, so they also work on mobile.
- iOS/Android: sync the deck through your existing AnkiWeb sync and configure an en_US TTS engine or voice on the device. The scripts import into the local collection only and never run a full AnkiWeb sync. Actual mobile display and playback still need to be checked on each device.

data/pending.jsonl is created on the first collected word; data/history.jsonl records the receipt and full vocabulary data only after a successful read-back confirmation. Writes use a temporary file in the same directory, fsync, macOS F_FULLFSYNC, atomic replacement and a process lock. If the process stops after a successful write to Anki, the next run finds the original note by Key instead of creating it again. A pending entry is removed only after the history record has been written. The directory is private and data files have 0600 permissions; there are no per-day files, no database, and Anki's internal database is never read.

Tests use temporary directories and a mock API by default; they run no HTTP server and never touch the real Anki. Real-world verification is done separately with valid study examples in the target deck; it never writes to other decks or resets reviews.
