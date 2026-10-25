# Setup

This guide covers installation and initialization. Installation is a single procedure that you can run yourself or hand to a local agent.

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

Python 3.9 or later is required, and neither system always ships with it.

- macOS: run `python3 --version`. If Python is missing or older than 3.9, install it from https://www.python.org/downloads/, or with `brew install python` if you already use Homebrew.
- Windows: run `py -3 --version`. If Python is missing or older than 3.9, install it from https://www.python.org/downloads/.

### Step 2: Install Anki

- macOS: skip this step if `/Applications/Anki.app` exists. Otherwise download the dmg for this Mac's chip from https://apps.ankiweb.net (`uname -m` prints `arm64` for Apple Silicon and `x86_64` for Intel), mount it, copy `Anki.app` to `/Applications`, then unmount it. If you already manage apps with Homebrew, `brew install --cask anki` works instead.
- Windows: skip this step if `%LOCALAPPDATA%\Programs\Anki\anki.exe` exists. Otherwise download the Windows `.msi` installer from https://apps.ankiweb.net (`anki-<version>-win-x64.msi`, or `-win-arm64.msi` for ARM) and run it. It installs for the current user; `msiexec /i <file>.msi /qn` installs it without any dialog.

### Step 3: Install AnkiConnect

AnkiConnect lives in Anki's add-on folder:

- macOS: `~/Library/Application Support/Anki2/addons21/2055492159`
- Windows: `%APPDATA%\Anki2\addons21\2055492159`

Skip this step if that folder exists. Otherwise quit Anki, download the official add-on from AnkiWeb and extract it into that folder, then start Anki again:

```text
https://ankiweb.net/shared/download/2055492159?v=2.1&p=<point>
```

`<point>` is the installed Anki version written as digits, for example `250705` for Anki 25.07.5. The link serves `AnkiConnect.ankiaddon`, which is a zip file. Alternatively, open the downloaded file with Anki, or enter code `2055492159` in Anki → Tools → Add-ons → Get Add-ons and restart Anki.

Keep AnkiConnect's bind address `127.0.0.1` and port `8765`; no CORS wildcard and no relaxed security settings are needed. If the add-on has an API key enabled, pass it to the scripts through the `ANKICONNECT_API_KEY` environment variable; never put the key in notes, the skill or a chat.

### Step 4: Clone the skill

Clone the repository into a directory your runtime loads skills from. Common locations:

| Runtime | Skill directory |
|---|---|
| Codex and other runtimes that read the Agent Skills user directory | `~/.agents/skills/academic-vocabulary-anki/` |
| Claude Code | `~/.claude/skills/academic-vocabulary-anki/` |

```sh
git clone https://github.com/RowanXB/academic-vocabulary-anki.git ~/.agents/skills/academic-vocabulary-anki
```

This guide and the other guides in `references/` write the chosen directory as `<skill-dir>`. The scripts locate their configuration and data from their own path, so `config.json` and `data/` live inside `<skill-dir>`. Each clone keeps its own configuration and vocabulary history; if you use several runtimes and want them to share one history, install once and make the other runtimes read that same directory yourself.

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

Initialization binds that profile in `config.json`, creates the missing "Academic Vocabulary" deck and note type, and checks fields and templates. If an incompatible structure with the same name already exists, it stops and never overwrites it. Running it again is safe; after updating the skill, run it once more to upgrade card templates from an earlier version of this skill (templates you edited are left alone).

### Step 7: Load the skill

Start a new conversation so the runtime loads the skill. If it does not appear, restart the runtime or give it the path to `<skill-dir>/SKILL.md`. A local installation does not mean a cloud session has the skill or can reach this computer.

Installation is complete; no further setup is needed. Continue with [operations.md](operations.md) to start collecting.
