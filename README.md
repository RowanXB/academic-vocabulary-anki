# Academic Vocabulary

A local Agent Skill plus Python standard-library scripts. It works in local runtimes that support skills, such as Codex and Claude Code. The main entry point is `SKILL.md`.

Installation, usage and troubleshooting notes are in [references/setup.md](references/setup.md).

Main files:

- `scripts/intake.py`: validates, persists and automatically attempts a sync.
- `scripts/sync.py`: initializes, checks status and retries pending syncs.
- `scripts/lookup.py`: looks up known senses.
- `scripts/common.py`: fixed data structures, persistence and API communication.
- `assets/`: two Front/Back card templates and CSS.
- `tests/`: non-destructive automated tests.
- `evals/`: language-generation examples and evaluation cases.
- `config.json`: local endpoint and Anki profile binding; contains no secrets.
- `data/pending.jsonl`: records awaiting sync; created on the first collected word.
- `data/history.jsonl`: confirmed import receipts and context history.

There is no background agent and no long-running service. Pending records are retried the next time a word is collected; opening Anki alone does not process the queue.

License: [MIT](LICENSE).
