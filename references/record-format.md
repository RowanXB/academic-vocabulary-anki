# Structured intake

Input is a JSON object, array of objects, or JSONL. All text is plain text: HTML is escaped by the script. `Key` and `Prompt` are generated; if supplied, they must match the generated values. No external content is executed. Data is not sent beyond local AnkiConnect by these scripts.

```json
{
  "sense": "reduce-strength",
  "fields": {
    "Term": "attenuate",
    "Definition": "To reduce the strength or magnitude of something.",
    "Context": "The effect was attenuated after controlling for age.",
    "Answer": "attenuated",
    "Hint": "verb; starts with a; past participle",
    "Collocation": "attenuate an effect",
    "Contrast": "",
    "Receptive": "",
    "Productive": "1",
    "IPA": "/əˈten.ju.eɪt/"
  },
  "tags": ["academic", "statistics"],
  "context_origin": "user",
  "original_context": "The effect was attenuated after controlling for age.",
  "target_forms": ["attenuate", "attenuates", "attenuating", "attenuated", "attenuation"],
  "ipa_source": "https://dictionary.cambridge.org/us/dictionary/english/attenuate",
  "sources": ["https://dictionary.cambridge.org/us/dictionary/english/attenuate"]
}
```

For generated contexts, use `context_origin: "generated"` and omit `original_context` (or use an empty string). Sources and IPA-source URLs are local metadata, not Anki fields. A nonempty IPA requires an HTTPS source; this structural check does not prove the source supports the IPA. The generating agent must actually verify it. Use `sources: []` when no source was consulted. `target_forms` must include relevant inflections/derivations to catch leaks; the script always adds Term and Answer.

Required fields: Term, Definition, Context, plus at least one card flag set to the string `"1"`. Supply Answer or the model-selected `answer_spans` described below. Other fields default to `""`. Supply a domain tag such as academic, neuroscience, psychology or statistics. The matching context_user/context_generated tag is added automatically. Context must be a full example, normally one sentence. The script checks a basic minimum length, not grammatical or scientific correctness.

## Model-selected blanks

The model chooses the target occurrences and forms in context. Prefer `answer_spans` for new records; it is local metadata, not an Anki field. Each entry contains the exact case-sensitive text and its 1-based occurrence among whole-word matches of that text in the original Context. Offsets need not be counted by the model.

```json
{
  "answer_spans": [
    {"text": "attenuate", "occurrence": 1},
    {"text": "attenuated", "occurrence": 1}
  ]
}
```

For Context `The intervention may attenuate the response, as it attenuated earlier responses.`, the script derives:

- Prompt: `The intervention may _____ (1) the response, as it _____ (2) earlier responses.`
- Answer: `1. attenuate\n2. attenuated` (two actual lines).

Omit the input Prompt and Answer to let the script derive them. If supplied and nonempty, they must match the derived values. Selections are ordered by position in Context; missing, duplicate or overlapping selections are rejected. If all selected occurrences have identical text, every blank is `_____` and Answer contains that text once. Choose occurrences for one learning target and sense; do not combine unrelated terms or meanings. Productive cards still reject visible target forms in Definition, Prompt or Hint. Receptive cards preserve the full original Context.

Existing inputs without `answer_spans` remain supported: Answer must have at least one exact whole-word match, and all exact matches become blanks. The optional zero-based `answer_start` checks the first selected match; it does not select or suppress occurrences. Existing single-match records retain their keys, checksums and format.

Anki field order: Key, Term, Definition, Context, Prompt, Answer, Hint, Collocation, Contrast, Receptive, Productive, IPA.

Key algorithm: `av1-` + full SHA-256 of NFKC/casefold/whitespace-normalized Term, newline, stable sense slug. Slugs use lowercase letters/digits separated by hyphens, at most 80 characters. They identify a meaning, not an example or date. Look up and reuse them before every intake. Different senses may share Term but not Key. A record ID additionally hashes the complete validated payload so distinct encounters survive in history.

Exit codes: 0 = requested operation complete (with `--no-sync`, this means cached only); 2 = cache retained/API unavailable; 1 = validation/configuration/storage failure. Read JSON output rather than guessing from exit code. One intake prints a cache result followed by a sync result.

Blank-only enrichment preserves existing card flags and review history. When the same sense is encountered in a new sentence, Anki keeps its existing sentence; the new source sentence is recorded in history after confirmation. No provenance tag is added for a sentence that was not placed in the Anki Context field.
