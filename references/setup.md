# Setup and operations

This guide covers installation, daily use, maintenance and troubleshooting. Installation is a single procedure that you can run yourself or hand to a local agent.

## Requirements

- macOS or Windows
- Python 3.9 or later (the scripts use only the standard library)
- Anki with the AnkiConnect add-on

Commands in this guide use `python3` and `~`. On Windows, use `py -3` (or `python`) for `python3`, and `%USERPROFILE%` for `~`.

## Installation

### Install with an agent

Open a local agent session that can run shell commands, such as Claude Code or Codex, and send:

```text
Install the agent skill from https://github.com/RowanXB/academic-vocabulary-anki on this computer.
```

The agent follows the steps below. When an agent runs them, it must:

- ask you which install directory to use instead of choosing one itself;
- tell you what is missing and how it would install it, and wait for your confirmation before installing software or running `--init`;
- stop and show you what is there if a target path already exists, never overwriting it;
- finish by reporting the install path and the commands it ran.

To install manually, run the same steps yourself.

### Step 1: Check Python

```sh
python3 --version
```

On Windows, run `py -3 --version`.

macOS and Windows do not always ship with Python. If it is missing or older than 3.9, install Python 3 from https://www.python.org/downloads/ (or with Homebrew on macOS if you already use it).

### Step 2: Install Anki

Skip this step if Anki is already installed (on macOS, `/Applications/Anki.app` exists).

- macOS: download the dmg for this Mac's chip from https://apps.ankiweb.net (`uname -m` prints `arm64` for Apple Silicon and `x86_64` for Intel), mount it, copy `Anki.app` to `/Applications`, then unmount it. If you already manage apps with Homebrew, `brew install --cask anki` works instead.
- Windows: download the Windows installer from https://apps.ankiweb.net and run it.

### Step 3: Install AnkiConnect

Skip this step if the add-on folder already exists:

| System | AnkiConnect folder |
|---|---|
| macOS | `~/Library/Application Support/Anki2/addons21/2055492159` |
| Windows | `%APPDATA%\Anki2\addons21\2055492159` |

Quit Anki, download the official add-on from AnkiWeb and extract it into that folder, then start Anki again:

```text
https://ankiweb.net/shared/download/2055492159?v=2.1&p=<point>
```

`<point>` is the installed Anki version written as digits, for example `250705` for Anki 25.07.5. The link serves `AnkiConnect.ankiaddon`, which is a zip file. Alternatively, open the downloaded file with Anki, or enter code `2055492159` in Anki → Tools → Add-ons → Get Add-ons and restart Anki.

Keep AnkiConnect's bind address `127.0.0.1` and port `8765`; no CORS wildcard and no relaxed security settings are needed. If the add-on has an API key enabled, pass it to the scripts through the `ANKICONNECT_API_KEY` environment variable; never put the key in notes, the skill or a chat.

### Step 4: Clone the skill

Clone the repository into a directory your runtime loads skills from. Common locations:

| Runtime | Skill directory (on Windows, `~` is `%USERPROFILE%`) |
|---|---|
| Codex and other runtimes that read the Agent Skills user directory | `~/.agents/skills/academic-vocabulary-anki/` |
| Claude Code | `~/.claude/skills/academic-vocabulary-anki/` |

```sh
git clone https://github.com/RowanXB/academic-vocabulary-anki.git ~/.agents/skills/academic-vocabulary-anki
```

The rest of this guide writes the chosen directory as `<skill-dir>`. The scripts locate their configuration and data from their own path, so `config.json` and `data/` live inside `<skill-dir>`. Each clone keeps its own configuration and vocabulary history; if you use several runtimes and want them to share one history, install once and make the other runtimes read that same directory yourself.

### Step 5: Check the connection

Open Anki on the profile you want to use, then run:

```sh
python3 <skill-dir>/scripts/sync.py --status
```

`"status": "available"` means AnkiConnect is responding. The output also shows the active profile and whether the target deck and note type already exist. This check is read-only.

### Step 6: Initialize

Confirm that the active profile shown in step 5 is the one you want, then run once:

```sh
python3 <skill-dir>/scripts/sync.py --init
```

Initialization binds that profile in `config.json`, creates the missing "Academic Vocabulary" deck and note type, and checks fields and templates. If an incompatible structure with the same name already exists, it stops and never overwrites it. Running it again is safe.

### Step 7: Load the skill

Start a new conversation so the runtime loads the skill. If it does not appear, restart the runtime or give it the path to `<skill-dir>/SKILL.md`. A local installation does not mean a cloud session has the skill or can reach this computer.

Installation is complete; no further setup is needed.

## Daily use

### Start collecting

In a chat dedicated to vocabulary, send this first: `Use academic-vocabulary-anki and treat this chat as a vocabulary collection chat. Save every word I send from now on to Anki automatically.` (In Codex you can write `$academic-vocabulary-anki`; in Claude Code you can use `/academic-vocabulary-anki`.) After that, just send words or screenshots.

Automatic skill discovery is model behavior and cannot be guaranteed every time; enabling it explicitly once in a dedicated chat is the most reliable. The project has no resident background process, and opening Anki does not trigger a catch-up sync; pending records are retried on the next collected word or sync run.

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

- `pending`: the content is still in data/pending.jsonl. Open or wake Anki, finish any open dialog, then sync again. macOS can also put background apps to sleep and cause a temporary timeout; wake Anki and retry, without changing system settings automatically.
- Windows "file in use" or permission errors while saving: another program, such as antivirus or an editor, has a file in `data/` open. Close it and retry; records already saved stay pending until the next sync.
- `failed`: read the JSON error. If `saved_pending` was printed earlier, the cache is still saved; otherwise do not assume anything was saved. A corrupted JSONL file stops processing and the original file is kept; bad lines are never dropped automatically.
- Duplicate sense: run lookup first and reuse the sense. The scripts only guarantee idempotency for a stable Key; comparing meanings is the AI's job. Renaming a sense must not be used to bypass deduplication.
- Existing content: only completely empty compatible fields are filled; manual text, review history, card flags and existing CSS are never overwritten. Replacing an old context or enabling another card direction is a separate, explicit edit. Do not edit the same note or switch profiles in Anki while syncing; AnkiConnect has no atomic conditional update across requests.
- A card with the same Key was moved to another deck: sync stops and waits for manual review; it never moves the card back or modifies other decks.
- Field or template mismatch: sync stops for manual review; user templates are never overwritten automatically. CSS can be adjusted freely and does not affect the script checks.
- The `context_user`/`context_generated` tags describe the context currently stored in Anki; a new original sentence from a repeated input is kept in history instead of pretending Anki's context was replaced.
- Anki's native tags are case-insensitive and may reuse an existing spelling such as `Statistics`; the scripts compare tags by the same rule and never rename tags across the collection.
- An empty IPA is a deliberate "not verified" state. TTS uses the device's built-in en_US voice: on desktop, install an American English voice in the macOS or Windows speech settings and restart Anki. The templates do not pin a specific Apple voice, so they also work on mobile.
- iOS/Android: sync the deck through your existing AnkiWeb sync and configure an en_US TTS engine or voice on the device. The scripts import into the local collection only and never run a full AnkiWeb sync. Actual mobile display and playback still need to be checked on each device.

## How data is stored

data/pending.jsonl is created on the first collected word; data/history.jsonl records the receipt and full vocabulary data only after a successful read-back confirmation. Writes use a temporary file in the same directory, fsync (plus F_FULLFSYNC on macOS), atomic replacement and a process lock (`flock` on macOS and Linux, `msvcrt.locking` on Windows). The containing directory is also fsynced on macOS and Linux; Windows cannot open a directory for that, and relies on the atomic replacement. If the process stops after a successful write to Anki, the next run finds the original note by Key instead of creating it again. A pending entry is removed only after the history record has been written. On macOS the directory is private and data files have 0600 permissions; on Windows they inherit the user profile's access rules; there are no per-day files, no database, and Anki's internal database is never read.

## Tests

Tests use temporary directories and a mock API by default; they run no HTTP server and never touch the real Anki. Real-world verification is done separately with valid study examples in the target deck; it never writes to other decks or resets reviews.
