# Installation, usage and troubleshooting

## Requirements

macOS, Python 3.9+, a local Anki installation and AnkiConnect. The scripts depend only on the Python standard library. macOS does not always ship with Python; check with `python3 --version`.

## Choose where to install

Install the skill by cloning the repository into the skills directory of the runtime you use. Common locations:

| Runtime | Skill directory |
|---|---|
| Codex and other runtimes that read the Agent Skills user directory | `~/.agents/skills/academic-vocabulary-anki/` |
| Claude Code | `~/.claude/skills/academic-vocabulary-anki/` |

You decide the location; any directory your runtime loads skills from works. The scripts find their configuration and data from their own location, so `config.json` and `data/` live inside the directory you choose. Back up that whole directory when moving to another computer, especially pending, history and config.

Each clone keeps its own configuration and vocabulary history. If you use several runtimes and want them to share one history, install once and make the other runtimes read that same directory yourself.

The rest of this guide writes the chosen directory as `<skill-dir>`.

New conversations load new skills; if the skill does not appear, restart that runtime or give it the path to SKILL.md explicitly. A local installation does not mean a cloud session has the skill or can reach this computer.

## Install

### Let your agent install it

Open a local agent session that can run shell commands (for example Claude Code or Codex) and paste this request:

```text
Install the agent skill from https://github.com/RowanXB/academic-vocabulary-anki on this Mac:
1. Check that python3 is version 3.9 or later, and that Anki (/Applications/Anki.app) and the AnkiConnect add-on (folder 2055492159 in Anki's addons21 directory) are installed. If anything is missing, tell me what and how you would install it, and install it yourself only after I confirm. For Anki, download the macOS dmg for this Mac's chip (Apple Silicon or Intel; check with `uname -m`) from https://apps.ankiweb.net, mount it, copy Anki.app to /Applications, then unmount it. If I already manage apps with Homebrew, `brew install --cask anki` is fine instead. For AnkiConnect, quit Anki, download the official add-on from https://ankiweb.net/shared/download/2055492159?v=2.1&p=<point> (p is the installed Anki version as digits, e.g. 25.07.5 → 250705; it serves AnkiConnect.ankiaddon, a zip file), extract it into ~/Library/Application Support/Anki2/addons21/2055492159, then start Anki again.
2. Ask me which directory to install the skill in, and suggest this runtime's own skills directory as the default. Do not choose for me.
3. Clone the repository into the directory I choose. If that path already exists, stop and show me what is there.
4. Open Anki, then run scripts/sync.py --status from the clone and show me the result; "available" means AnkiConnect is responding.
5. Only after I confirm the active Anki profile is the one I want, run scripts/sync.py --init.
Report the install path and what you ran at the end.
```

Then start a new conversation so the runtime loads the skill.

### Install manually

Pick a directory from the table above and clone into it. For example, for the Agent Skills user directory:

```sh
git clone https://github.com/RowanXB/academic-vocabulary-anki.git ~/.agents/skills/academic-vocabulary-anki
```

If the target already exists, inspect it manually and do not overwrite it.

## Set up AnkiConnect

If AnkiConnect is not installed, enter the official code `2055492159` in Anki → Tools → Add-ons → Get Add-ons, then restart Anki. Alternatively, download `AnkiConnect.ankiaddon` from `https://ankiweb.net/shared/download/2055492159?v=2.1&p=<point>` (for Anki 25.07.5, `p=250705`) and open it with Anki to install. Keep the bind address `127.0.0.1` and port `8765`; no CORS wildcard and no relaxed security settings are needed. If the add-on has an API key enabled, pass it to the scripts through the `ANKICONNECT_API_KEY` environment variable; never put the key in notes, the skill or a chat.

## First-time initialization

Run once, with Anki open on the profile you want to use:

```sh
python3 <skill-dir>/scripts/sync.py --init
```

Initialization binds the current Anki profile, creates the missing target deck and note type, and checks fields and templates. If an incompatible structure with the same name already exists, it stops and never overwrites it.

## Start collecting

In a chat dedicated to vocabulary, send this first: `Use academic-vocabulary-anki and treat this chat as a vocabulary collection chat. Save every word I send from now on to Anki automatically.` (In Codex you can write `$academic-vocabulary-anki`; in Claude Code you can use `/academic-vocabulary-anki`.) After that, just send words or screenshots.

Automatic skill discovery is model behavior and cannot be guaranteed every time; enabling it explicitly once in a dedicated chat is the most reliable. The project has no resident background process, and opening Anki does not trigger a catch-up sync; pending records are retried on the next collected word or sync run.

## Switching or clearing Anki profiles

Switching profiles requires the user to review and edit `expected_profile` in the project config deliberately; do not mix profiles in one queue.

If you clear the current profile yourself: keep the local project first; after clearing, run `sync.py --init` to rebuild the target structure. History is not re-imported automatically; only pending records are processed on the next sync. When creating a profile with a different name, first confirm that the queued records belong to the new profile, then set `expected_profile` in config.json to that profile's exact name and initialize. Do not change the binding automatically just because the API reports a different profile. Clearing Anki and clearing the local vocabulary history are two separate operations.

## Common commands

```sh
python3 <skill-dir>/scripts/sync.py --status
python3 <skill-dir>/scripts/sync.py
python3 <skill-dir>/scripts/lookup.py attenuate
python3 <skill-dir>/scripts/intake.py records.json
python3 -m unittest discover -s <skill-dir>/tests -v
```

The model generates the structured data; the scripts contain no AI API and do not accept a bare word to generate definitions themselves. The skill handles that layer in everyday use. The default data directory is derived from the scripts' actual location. `--root PATH` isolates test data or points to another data directory explicitly; it does not change the Anki target names or the localhost address.

## Troubleshooting

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

## Data and durability

data/pending.jsonl is created on the first collected word; data/history.jsonl records the receipt and full vocabulary data only after a successful read-back confirmation. Writes use a temporary file in the same directory, fsync, macOS F_FULLFSYNC, atomic replacement and a process lock. If the process stops after a successful write to Anki, the next run finds the original note by Key instead of creating it again. A pending entry is removed only after the history record has been written. The directory is private and data files have 0600 permissions; there are no per-day files, no database, and Anki's internal database is never read.

## Tests

Tests use temporary directories and a mock API by default; they run no HTTP server and never touch the real Anki. Real-world verification is done separately with valid study examples in the target deck; it never writes to other decks or resets reviews.
