# Measuring prose with rift

**When to reach for it:** you are pointing `measure` / `expect` or `rift stats` at
a body of writing — a book, a docs set, a chapter directory — and want numbers you
can act on rather than numbers that look meaningful.

Everything here was learned running the metrics over a real 26-chapter book
(`repos/books-tsoc`, 2026-08-26). The traps below are not hypothetical; each one
produced a wrong answer first.

## Strip the renderer's markup, or you are measuring apparatus

**This is the one that will bite you, and it is silent.**

Marker syntax is not prose. Left in, `[Tony Hoare]{~hoare-tony}` tokenises as
*"tony hoare hoare tony"* — four tokens where the reader sees two — and a marker
that carries a caption (`[in 1969]{>1969: Hoare publishes an axiomatic basis…}`)
leaks the entire caption into the sentence stream with no terminal punctuation to
break it. One such marker produced a 144-token "sentence".

The damage is not a rounding error, and it is worst exactly where you will look
first: **a chapter that carries more markers than its neighbours measures as
having different prose**, so it surfaces as your top outlier. In the book, the
"burstiest chapter" scored 0.871 with markers and 0.701 without, against a book
mean of 0.696. It was not an outlier at all. It just had more glossary entries.

```yaml
    measure:
      files: "chapters/*.md"
      metric: sentence-length-cv
      strip: ['\{[~>][^}]*\}', '\[>[^\]]*\]']
```

`rift stats` takes the same patterns via repeatable `-s`. **Put them in a makefile
target** so nobody runs the un-stripped version by accident — the numbers look
perfectly plausible either way, which is what makes it dangerous.

The general rule: anything the renderer consumes and the reader never sees must be
stripped before measuring. rift cannot know what that is for your renderer; that
is why `strip:` exists and why it ships empty.

## What Burrows's Delta can and cannot tell you

Delta answers **"is one document in this set written by a different hand than the
others?"** It self-calibrates against the set's own centroid, which is why
`vs-siblings` is the predicate to pair it with.

It does **not** answer "does this sound like me". If an entire book drifted
uniformly away from your voice, every chapter would drift together, the centroid
would move with them, and Delta would report a perfectly tight set. In the book,
the spread was 0.627–0.937 with a largest sibling z of 1.99 — clean by every
internal measure, and completely silent on the question the author actually cared
about.

**To ask "is this my voice", put your own writing in the comparison set.** Glob
your essays alongside the chapters and see whether the chapters cluster away from
them. Same metric, different file set, and it is the only version of the question
Delta can answer.

Delta is also noisy at chapter length — it is designed for whole novels. Rank the
results; do not read meaning into the third decimal.

## Your reference chapter will fail your own rule

If a project has a declared gold-standard document ("when in doubt, reread this
one"), expect it to be a `vs-siblings` outlier. The book's stated voice reference
sat more than 2 sd from its siblings on four metrics — lowest short-sentence
ratio, lowest vocabulary diversity, shortest headings.

That is not a contradiction; it is the point. The gold standard is distinctive,
and `vs-siblings` measures distinctiveness. But it means **"write like chapter N"
and "stay near your siblings" are different instructions**, and a rule enforcing
the second will flag the document embodying the first. Decide which you want
before writing the threshold, and consider excluding the reference document from
the comparison glob.

## Read the parts before the chapters

Per-file outliers are noisy and mostly uninteresting: with 26 files and 13 metrics
you will get twenty-odd `|z| > 2` hits by construction, and chasing them
individually tells you very little.

The signal that mattered was an aggregate one — one Part of the book was flatter
than every other Part on burstiness (0.604 against 0.67–0.71) and was the only
Part with negative sentence-length autocorrelation, across *all* of its chapters.
No single chapter was a dramatic outlier; the group was. Average by directory
before you go file by file.

Note also which metrics *disagree*: that same Part had the book's **highest**
vocabulary diversity. "Flat" was true of its cadence and false of its words, and
only reading two families together gives you that.

## An average hides the one paragraph a reader will actually notice

The mirror of the section above: aggregates conceal single offenders, and for
paragraph length the single offender is the whole complaint. A reader does not
experience a mean — they hit one wall of text and stop.

Measured on a real prologue, before and after its three longest paragraphs were
split (the text is otherwise identical — splitting cost zero words):

| | before | after |
|---|---|---|
| `mean-paragraph-length` | 83.1 | 80.2 |
| `paragraph-length-cv` | 0.665 | 0.561 |
| `max-paragraph-length` | **403** | **198** |

The mean moves three tokens across a 400-token defect — one wall among 160
paragraphs cannot shift it, and no threshold on it could have caught this.

The CV is the more interesting failure. It did move here, so it is not blind —
but it cannot tell *one wall of text* from *healthy variation*, because both
raise it. Bound it and you flag the document that deliberately drops a
one-sentence paragraph for emphasis, which is the effect you were hoping to
protect. **Bound the top end; never bound the variation.**

**A rift token is not a word, and the gap is where your threshold goes wrong.**
Tokenising is `\w+`, so `25.9` counts as two and `six-point` as two. The
after-column above reads 198 by rift and 184 by `len(p.split())` — a 7% spread,
concentrated entirely in whichever paragraph carries the statistics. A `max: 200`
rule is therefore meaningfully *tighter* than "200 words", and tightest on
exactly the data-heavy paragraphs. Measure with `rift stats` and set the bound
against that number, not against a count from another tool.

**Then leave margin.** That book holds a corpus max of 198 against a written
standard of "200 words", and shipped its rule at **220** rather than 200. At 200
the bound clears by two tokens — adding one decimal to the statistics paragraph
turns the gate red without the prose getting worse, and a gate that fires on
noise is one people learn to skip. The standard stays 200 for the writer; the
linter catches them around 205.

## Do not ship thresholds you have not measured

Write the rule with no `expect:` first, or use `rift stats`, and look at the real
distribution before choosing a bound. rift ships no defaults precisely because a
plausible-sounding threshold picked in advance is how a linter starts crying wolf.

`vs-siblings` needs no number at all and survives the set growing, so prefer it
unless you have a reason the absolute value matters. Remember it needs at least 4
files — below that rift reports the number, warns, and does not judge.

## Fixing a `vs-siblings` outlier can promote the next one

Observed on `books-tsoc`, 2026-08-27: the longest chapter was trimmed under the
line, and the next-longest immediately took its place as the outlier.

This is arithmetic, not bad luck. `vs-siblings` compares each file against the
**other** files — `s = pstdev(others)` — so pulling the extreme value toward the
middle shrinks the sibling spread for every remaining file, and a smaller `s`
makes `k * s` a tighter band. Every other file's z-score goes **up** when you fix
the worst one. A set with one dramatic outlier and a cluster behind it can chase
you through the whole cluster, one commit at a time.

**So do not edit toward the line — edit toward a value.** Before touching
anything, run `rift stats` over the set, decide what the number should actually
be for the file in question, and change it to that. If several files are close
to the band, expect to move several: compute where the set lands once they are
all where you want them, rather than iterating into a fixed point you never
chose.

This is not an argument against `vs-siblings` — it is still the predicate to
reach for, precisely because it has no invented number in it. It is an argument
against treating "the rule went green" as the goal. The rule going green is
evidence about the set, and the set moved while you were looking at it.

## Encoding a style guide: what converts and what does not

Taking a real book's prose rules (`repos/books-tsoc`, CALIBRATION.md plus six
know-how docs) rule by rule, the split was sharp.

**Converts cleanly** — anything that is a *phrase*, a *density*, or a
*cross-reference*. Banned register ("basically", "it turns out"), forward and
backward chapter heralds, academic royal plural, em-dash budget, intensifier
budget, author/reader presence, every marker resolving to a real glossary key,
every glossary key actually being marked, a term marked only once per chapter, a
footnote label defined only once.

**Does not convert, and should not be forced** — the 2:2:1 historical/didactic/
philosophical weave, "characters have minds", "concrete before abstract", "the
coda must be unrepeatable in another chapter", "section titles are slogans not
topic labels", "open with urgency not definition". Each needs a reader. Encoding
a proxy is how a linter starts lying: `mean-heading-length` is not a slogan
detector.

**Two rules of thumb that emerged:**

*A rule that is mostly red is noise, not a check.* The book declares a 2,000–3,000
word target; 22 of its 26 chapters are outside it. Encoding that target produces
22 warnings every run and trains everyone to skim past red. `vs-siblings` on
`word-count` instead flags exactly one chapter, and that one is worth looking at.
When your declared target and your actual corpus disagree, the linter's job is to
surface the disagreement once — in a task — not to shout it every run.

*A rule that is green on arrival is still worth writing.* Six of the rules here
found nothing, because a holistic revision pass had already fixed them. They are
regression guards for expensive manual work, which is the cheapest kind of rule
to own.

**Watch for permissive matching quietly weakening a rule.** "Every glossary entry
is used" with `as: mention` reported 26 unused; the true number was 34, because
the entry `abstraction` was being satisfied by the ordinary word *abstraction*.
`wrap:` fixes it by matching the marker instead of the bare string. Any rule whose
entities are *keys* rather than *prose* probably wants `wrap:`.

## Related

- **[writing-rules](writing-rules.md)** — the bar a rule has to clear before it
  earns `severity: error`, and how to use `rift list` to tune one.
- `docs/prose-linting-design.md` — why each metric was chosen, and which were
  deliberately excluded (readability scores, chiefly).
