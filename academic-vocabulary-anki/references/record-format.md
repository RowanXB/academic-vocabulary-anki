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

Required fields: Term, Definition, Context, Answer, plus at least one card flag set to the string `"1"`. Other fields default to `""`. Supply a domain tag such as academic, neuroscience, psychology or statistics. The matching context_user/context_generated tag is added automatically. Exactly one exact Answer occurrence is required; optional zero-based `answer_start` verifies the span. Context must be a full example, normally one sentence. The script checks a basic minimum length, not grammatical or scientific correctness.

Anki field order: Key, Term, Definition, Context, Prompt, Answer, Hint, Collocation, Contrast, Receptive, Productive, IPA.

Key algorithm: `av1-` + full SHA-256 of NFKC/casefold/whitespace-normalized Term, newline, stable sense slug. Slugs use lowercase letters/digits separated by hyphens, at most 80 characters. They identify a meaning, not an example or date. Look up and reuse them before every intake. Different senses may share Term but not Key. A record ID additionally hashes the complete validated payload so distinct encounters survive in history.

Exit codes: 0 = requested operation complete (with `--no-sync`, this means cached only); 2 = cache retained/API unavailable; 1 = validation/configuration/storage failure. Read JSON output rather than guessing from exit code. One intake prints a cache result followed by a sync result.

Blank-only enrichment preserves existing card flags and review history. When the same sense is encountered in a new sentence, Anki keeps its existing sentence; the new source sentence is recorded in history after confirmation. No provenance tag is added for a sentence that was not placed in the Anki Context field.
