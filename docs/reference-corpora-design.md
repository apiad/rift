# Reference corpora: measuring prose against a baseline

> **Status:** design, 2026-09-13. Not yet planned.

Every rift rule today is self-contained. It computes a number from one document
and compares it to a literal in `.rift.yaml`. That covers "is this file shaped
like its siblings" and it cannot express the question this design is about:
**does this text diverge from a reference body of writing?**

That question is what mechanical slop detection needs, because slop is not an
absolute property of a string. It is a frequency relative to how people
actually write.

## The governing constraint

**rift ships data and mechanism. It never ships rules.**

A frequency list, a spelling dictionary, a tokenizer, an arithmetic routine:
these are facts and machinery, the same for every project, and shipping them is
the difference between a usable tool and a homework assignment. A banned word,
a threshold, a target rate: these are policy, they differ per language, per
genre, per author, and they belong in `.rift.yaml` where a human argued for
them and a diff records the argument.

The line matters because the temptation here is strong. Everyone has a list of
AI words. Any list rift shipped would be wrong within a year and wrong for most
projects on the day it shipped.

Measured evidence that a shipped threshold would be wrong, from the workspace
that motivated this design:

- A widely-copied list of sixteen "AI vocabulary" words scored **zero
  occurrences** in 12,221 words of uninstructed model prose, while the human
  author it was meant to protect uses nine of them, one at 340 per million.
- Em dash rate in the same author's own published writing: **4.02 per 1000
  words in English, 28.19 in Spanish.** A shipped em-dash threshold is wrong by
  a factor of seven the moment it crosses a language boundary, because Spanish
  uses the raya for dialogue as ordinary typography.

So: the per-language *data* is a gold standard worth shipping. The per-language
*policy* is not.

## What gets added

### 1. A `corpora:` section

Named reference corpora, resolved like any other path in the config:

```yaml
corpora:
  author-en:
    paths: [corpus/published/**/*.md]
    lang: en
  author-es:
    paths: [corpus/capitulos/**/*.md]
    lang: es
```

A `rift profile` command compiles a corpus into a profile artifact: token
count, n-gram counts above a floor, the function-word frequency vector, and the
metric values rift already computes. Profiles are committed, so a check does not
re-read the corpus on every run and a profile change shows up in a diff.

Everything about which texts constitute the baseline is the project's decision.
rift supplies the counting.

### 2. Metrics that take a corpus

Three new metrics, each taking a `corpus:` argument. None carries a default
threshold.

**`overuse`** — the rate of a phrase in the file divided by its rate in the
reference corpus.

```yaml
- measure: overuse
  corpus: author-en
  pattern: "it isn't"
  max: 3.0
```

This is the one that finds tells nobody wrote down. In the motivating
measurement it ranked a contracted construction at **51x** the author's rate
while a hand-written rule list had aimed at the uncontracted form, which the
author used *more* than the model did.

A `rift overuse <corpus>` reporting command lists the top-ranked phrases so a
human can promote the ones they agree with into rules. The tool proposes;
`.rift.yaml` decides.

**`delta`** — Burrows's Delta against the corpus's function-word profile. Take
the N most frequent function words in the reference, z-normalise their
frequencies, average the absolute differences. Pure arithmetic, no model, and
the established instrument for authorship attribution since the 1990s.

```yaml
- measure: delta
  corpus: author-en
  words: 150
  max: 1.2
```

This answers "does this sound like the reference author" with one number, which
no combination of banned-word rules can do.

**`rarity`** — the fraction of tokens falling outside rank N of a frequency
list.

```yaml
- measure: rarity
  list: en          # a shipped language pack, or a corpus name
  above-rank: 10000
  max: 5.0          # percent
```

Measured on topic-matched corpora: the human author 4.37% outside the top
10,000, the model 6.35% on the same topics. The model reaches for rarer
vocabulary while being structurally more predictable, which is the "utilize"
problem at scale.

Note the direction is a project decision, not a universal. A children's
encyclopedia wants rarity *low*; a literary essay may want it high. rift
reports the number and `min`/`max` belong to the config.

### 3. `misspelled`

```yaml
- measure: misspelled
  dict: en
  allow: [tokenizer, logits, slopcheck]
  max: 0
```

Dictionary lookup plus affix rules over a hunspell/aspell dictionary. No model,
no statistics. The project wordlist is config, which is the same shape `permit`
already has, and technical prose needs it: an unconfigurable spell check over a
software repo is noise.

### 4. Rates, not only counts, for pattern measures

`pattern:` currently yields exact counts. Slop thresholds need rates, because
eight em dashes in a thousand words and eight in three thousand are different
texts. Add a `per:` normaliser:

```yaml
- measure: pattern
  pattern: "—"
  per: 1000-words
  max: 5.0
```

This is not cosmetic. In the measurement that motivated it, a rate-normalised
comparison credited an intervention with a 60% improvement that vanished in raw
counts, because the intervention made documents 35% longer. Both views need to
be available, and a config that picks one should have to say which.

## Language packs

rift may ship, per language: a frequency list with ranks, a hunspell/aspell
dictionary, a function-word list for `delta`, and a sentence/token segmenter
appropriate to the script.

```
rift lang install en es
```

These are the aspell-class artifacts: maintained, standard, identical for every
project, and useless to reimplement. Shipping them is what makes the metrics
above usable on day one rather than a research project per repo.

They carry **no thresholds and no word bans.** A language pack answers "how
frequent is this word in this language" and "is this a word". It never answers
"should you have written it".

A project may override any pack with its own corpus, which is the path for a
language rift does not ship and for a domain whose vocabulary the general list
misrepresents.

## What stays out

**Grammar checking.** LanguageTool is genuinely rule-based, so it passes the
no-model test, and it still should not go in. It needs a Java runtime or a
server, and its false-positive rate on technical prose is high enough to train
readers to skim past red, which is the one failure mode that makes a linter
worse than nothing. The parts that matter for slop are reachable more cheaply:
passive voice approximates well with a participle list and a regex.

**Anything that needs a reader.** A chapter that awards its central argument to
the wrong character has every sentence correct and the whole wrong. No rule
shape detects that, and a rule that pretends to is worse than none, because it
licenses skipping the read.

**Any built-in list of banned words.** Stated again because it is the thing
that will be proposed every time someone new arrives.

## Why this belongs in rift rather than a separate tool

The counting is the easy half. The hard half is the part rift already solved:
config resolution, zone scoping, severity promotion, `rift list` so every
finding is read before it becomes an error, and the discipline that a rule
starts as a warning and gets promoted only when its output is empty for reasons
someone agrees with. A standalone slop counter would have to rebuild all of it,
and would be run once and forgotten, which is exactly what happened to the
hand-written rule lists this design replaces.

## Open questions

- Profile format and whether it is committed or built. Committed is proposed
  above, for diffability; it costs repo size proportional to the n-gram floor.
- Whether `overuse` should require the phrase to be overrepresented against
  *two* references (the author and a general-language corpus). The motivating
  measurement needed both: against one baseline alone, the top-ranked results
  were topics rather than habits.
- Segmenter quality for languages whose sentence boundaries the current
  regex handles badly.
- Whether `delta` should report the contributing words, which is what makes a
  failure actionable rather than a bare number.
