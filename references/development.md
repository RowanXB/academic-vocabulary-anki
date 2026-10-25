# Development

This guide covers how data is stored and how to test the skill.

Paths and commands follow [setup.md](setup.md#requirements): `<skill-dir>` is the directory the skill was installed in, and on Windows `py -3` replaces `python3`.

## How data is stored

data/pending.jsonl is created on the first collected word; data/history.jsonl records the receipt and full vocabulary data only after a successful read-back confirmation. Writes use a temporary file in the same directory, fsync (plus F_FULLFSYNC on macOS), atomic replacement and a process lock (`flock` on macOS and Linux, `msvcrt.locking` on Windows). The containing directory is also fsynced on macOS and Linux; Windows cannot open a directory for that, and relies on the atomic replacement. If the process stops after a successful write to Anki, the next run finds the original note by Key instead of creating it again. A pending entry is removed only after the history record has been written. On macOS the directory is private and data files have 0600 permissions; on Windows they inherit the user profile's access rules; there are no per-day files, no database, and Anki's internal database is never read.

## Tests

Tests use temporary directories and a mock API by default; they run no HTTP server and never touch the real Anki. Real-world verification is done separately with valid study examples in the target deck; it never writes to other decks or resets reviews.

For automated or unattended tests against a real Anki, install Anki's official PyPI package in a virtual environment and give it its own data directory, so the test never touches your normal Anki app or collection:

```sh
python3 -m venv <test-dir>/venv
<test-dir>/venv/bin/python -m pip install "aqt[qt6]"
<test-dir>/venv/bin/anki -b <test-dir>/anki-base
```

On Windows the executables are in `venv\Scripts\` instead of `venv/bin/`. Install AnkiConnect into `<test-dir>/anki-base/addons21/2055492159` as in [setup step 3](setup.md#step-3-install-ankiconnect), and pass `--root <test-dir>/skill-data` to the scripts so the test queue, history and profile binding stay separate as well. The first launch of a new data directory shows a language dialog that needs one click. Use this only for testing; install Anki for daily use as in [setup step 2](setup.md#step-2-install-anki).
