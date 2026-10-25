# Rationale and verification sources

Design decisions, not claims of a uniquely optimal vocabulary method:

- Receptive recall tests meaning from a term in context; Productive recall tests the expression needed to express a meaning. Separate retrieval directions reflect partly distinct learning outcomes. [Yanagisawa (2016), original experiment](https://www.jstage.jst.go.jp/article/katejournal/30/0/30_11/_article) found stronger productive outcomes from productive retrieval than the comparison conditions. Its small sample and pseudowords limit direct generalization.
- Use Anki's normal spaced review scheduling rather than a custom timetable. [Kim & Webb (2022), meta-analysis](https://doi.org/10.1111/lang.12479) found a spacing benefit across second-language experiments, with variation by task and retention interval. This does not establish one best schedule for this learner; no scheduler settings are changed automatically.
- Preserve context to select a particular meaning and practice its inflected use. [Kim & Webb (2023), experiment](https://doi.org/10.1111/modl.12879) compared fill-in-the-blank practice and flashcards with spacing. The evidence supports both as useful activities; it does not show that this exact template is optimal.
- One collocation provides a usable phrase without turning each card into a multi-part test. Verified IPA and answer-side US TTS support sound-form knowledge, but listening alone does not test pronunciation production. Say the answer aloud before revealing it when practicing speech.
- Avoid redundant Both cards: choose direction by learning need and use minimal hints to make retrieval feasible. Context may sometimes make a Receptive card too easy; select a useful authentic sentence where possible, while remaining faithful to input.

Implementation references:

- [Anki conditional card generation](https://docs.ankiweb.net/templates/generation.html): the entire front is inside the relevant flag condition.
- [Anki TTS and native hints](https://docs.ankiweb.net/templates/fields.html): `{{tts en_US:Term}}`, `{{tts en_US:Answer}}`, `{{hint:Hint}}`.
- [AnkiConnect upstream](https://git.sr.ht/~foosoft/anki-connect): v6 actions verified against the locally installed add-on's source during setup. No modifications made to the add-on.

Example content sources checked on 2026-10-25:

- [Cambridge: attenuate](https://dictionary.cambridge.org/us/dictionary/english/attenuate) — reduction sense, US IPA, and effect usage.
- [NCBI MedGen: anterograde amnesia](https://www.ncbi.nlm.nih.gov/medgen/115938) — difficulty establishing new long-term memories.
- [Kessler et al. (1997)](https://pubmed.ncbi.nlm.nih.gov/9342692/) — attested “severe anterograde amnesia” usage.
- [APA: working memory](https://dictionary.apa.org/working-memory) — temporary maintenance and manipulation for cognitive tasks.
- [Oberauer et al. (2016)](https://pubmed.ncbi.nlm.nih.gov/26950009/) — attested “working memory capacity” usage.

Specialist IPA is left empty in the examples because a verified full US transcription was not obtained. Do not fill it from memory.
