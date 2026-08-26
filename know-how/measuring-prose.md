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

## Do not ship thresholds you have not measured

Write the rule with no `expect:` first, or use `rift stats`, and look at the real
distribution before choosing a bound. rift ships no defaults precisely because a
plausible-sounding threshold picked in advance is how a linter starts crying wolf.

`vs-siblings` needs no number at all and survives the set growing, so prefer it
unless you have a reason the absolute value matters. Remember it needs at least 4
files — below that rift reports the number, warns, and does not judge.

## Related

- **[writing-rules](writing-rules.md)** — the bar a rule has to clear before it
  earns `severity: error`, and how to use `rift list` to tune one.
- `docs/prose-linting-design.md` — why each metric was chosen, and which were
  deliberately excluded (readability scores, chiefly).
