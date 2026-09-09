# Quality-Scoring Feature — Evaluation Report

Real evaluation of the LLM quality-scoring feature (`feat/llm-quality-scoring`, PR #12) against a 25-resume set spanning SWE/FAANG, HFT/Quant, and IB, at three quality tiers. 37 real Gemini calls (`gemini-3.5-flash-lite`), zero mocked, zero errors. Rule engine held neutral throughout (all issues/strengths zeroed) so every score here is attributable purely to the LLM's `quality_flags` judgment — this isolates the new feature from the pre-existing structural rule engine.

**Content provenance**: resume bullets are drawn from / closely modeled on publicly-published teaching-example content (a SWE resume-bullet guide with 40+ before/after pairs, generic quant/HFT and IB resume-writing guides) — explicitly published as reference material for anyone to study, not scraped from Reddit or any real individual's personal resume/private feedback post. No real names, companies, or contact info anywhere in the set. This was a deliberate choice over pulling real Reddit posts, which even when "anonymized" by the poster often still carry identifying detail and were shared for private feedback, not as public examples — see `quality-scoring-eval/resumes.py` for the full fixture set and exact sourcing notes.

---

## FINAL UPDATE — holistic scoring shipped and verified end-to-end

The flag-deduction design below was replaced with a single holistic `substance_score` (0–100). This section reports the **implemented** version, measured by running the actual production code path — `build_roast_prompt` → real Gemini call with `response_schema` → `parse_roast_output` → `compute_score`/`compute_stamp` — not a standalone prompt harness. Runner: `run_shipped_eval.py`. 27 resumes × 2 full runs = 54 real Gemini calls, zero failures.

Unlike every earlier run in this document, the rule engine was **not** held neutral: structural deductions are live, so these are the real numbers a user would see.

### Result: tier separation is now clean

| tier | n | substance median | composite median | stamps |
|---|---|---|---|---|
| strong (synthetic) | 15 | 75 | 60 | 2 SOLID, 13 MID, 0 ROASTED |
| strong (real published CVs) | 2 | 75 | 68 | 2 MID |
| mid | 5 | 35 | 20 | 5 ROASTED |
| bad | 5 | 10 | 0 | 5 ROASTED |

**27/27 tier/stamp agreement, in both runs independently** — every strong resume landed SOLID or MID, every mid-or-bad resume landed ROASTED. Substance spread went from the old design's 32 points to 87–90.

Both real published CVs scored MID, matching the human label they were given independently — the single most trustworthy data point here, since it's real writing judged against a label set before the run.

### Two real bugs this run caught that unit tests did not

**1. Structural deductions were swamping content.** The first run stamped **9 of 15 strong resumes ROASTED** despite substance scores of 72–95. Uncapped, the rule engine's weights reach 40–52 points on an ordinary resume (no summary + no projects section + one long sentence is 27 on its own), so the structural tail was deciding the grade rather than the writing — the exact opposite of the design's stated intent. Fixed by capping structural deductions at 15 points (`MAX_STRUCTURAL_DEDUCTION`). Issues are still listed and still shown on the radar chart; the cap only limits their pull on the single headline number.

**2. The stamp thresholds were wrong by ~two bands.** They had been set at 85/60 from *substance* scores alone, before any composite had ever been measured end-to-end. Against the measured composite distribution they are now 75/35, with the MID boundary placed at the midpoint of the empty 27–43 band separating the tiers, so neither side turns on one borderline example.

### Stability across runs

Mean run-to-run change in substance score: **3.6 points**; max 17; **1 of 27** stamp flips (a resume sitting directly on the SOLID boundary). Tier-level assignment was identical across both runs. Good enough to ship; the same resume can still move a few points between uploads, which is worth remembering before treating the number as precise.

`SHALLOW_CONTENT` also fires on nearly every synthetic strong resume, which is a fixture artifact — they are short bullet excerpts, not full documents. It costs nothing now that flags are explanatory-only.

---

## FOLLOW-UP — vertical skew narrowed with a rubric fix, not fully closed

Top-tier substance medians before this fix: SWE 85, HFT/Quant 74–82, IB 62–72 (2 runs). Root cause, on inspection of the actual fixture bullets: the rubric's two most concrete example evidence types ("cut p99 latency from 800ms to 95ms", "implemented an async AMQP client with a layered architecture") were both SWE-flavored, and the IB fixtures already contain real quantified rigor (deal sizes, valuation moves, multi-scenario sensitivity analysis) that the model was nonetheless discounting relative to those exemplars — treating a dollar-denominated deal outcome as inherently weaker evidence than a latency number, independent of the actual analytical depth behind it.

Fix (`workers/scoring/pipeline/prompt_builder.py`): added a parallel finance-style exemplar to each of the four evidence types, and one explicit instruction — "do not discount a deal's dollar value... as weaker evidence just because the number reflects the deal's scale rather than lines of code — the rigor to look for is in the method... not in whether the artifact is software." Deliberately original wording, not lifted from the eval fixtures, so this isn't just fitting the test.

Verified over 2 more full runs (27 resumes each, 54 more real Gemini calls):

| | SWE | HFT/Quant | IB | SWE-vs-worst-vertical gap |
|---|---|---|---|---|
| before, run 1 | 85 | 78.5 | 68.5 | 16.5 |
| before, run 2 | 85 | 69.5 | 62.0 | 23.0 |
| after, run 1 | 85 | 75.0 | 71.5 | 13.5 |
| after, run 2 | 82 | 75.0 | 73.0 | 9.0 |

Gap roughly halved (16.5–23 → 9–13.5 points) and both after-runs held **27/27 tier/stamp agreement** — the fix narrowed the skew without weakening good-vs-bad separation. Not fully closed: SWE still reads several points stronger on median, and this is 2 runs against one 27-resume fixture set, not a large-sample claim. Worth revisiting again once there's real user volume across verticals to check against.

---

## SECOND UPDATE — attempted the fix, partial improvement, not resolved

After the real-data update below, added two calibration examples to `workers/scoring/pipeline/prompt_builder.py` showing that named technical specificity (exact tools/protocols) and named systems-with-sub-components (without a metric) both count as real substance, not `GENERIC_BULLETS`/`NO_QUANTIFIED_IMPACT`.

**Caught and fixed a real mistake in my own first attempt**: the first version of these examples was written too close to the two real resumes' actual text (paraphrased, but recognizably the same content) — that's data leakage, not a real fix, and also not something that belongs permanently embedded in a shipped, public-repo prompt regardless of whether it "worked." Rewrote both examples from scratch with unrelated content (a Rust log-ingestion rewrite, a payments-reconciliation service) before re-testing.

**Re-tested against the two real resumes with the corrected (non-leaked) examples**:

| Resume | Before fix | After fix (leaked examples) | After fix (corrected examples) |
|---|---|---|---|
| real_swe_technical_depth_1 (robotics researcher) | 75/75/75, all ROASTED | 85/90/85, all MID | 80/80/88 — 2 ROASTED, 1 MID |
| real_swe_narrative_style_1 (Google/Coursera engineer) | 75/73/73, all ROASTED | 73/73/83 — mostly ROASTED | 73/75/75, all ROASTED |

Real but modest improvement on one resume, essentially none on the other. This is a harder calibration problem than one or two prompt examples fully solve — my working theory (untested) is that the deterministic "Quantified-impact check: N of M lines contain a number" line, sitting in the AUTOMATED FINDINGS block right next to the real rule-engine issues, may be carrying more implicit authority than the qualitative caveats around it, but I haven't verified that by removing it and re-testing.

**Deliberately stopping here rather than continuing to iterate blind.** This now looks like a real design decision (how much weight named-specificity should get vs. metrics, whether the quantified-impact grounding line is worth keeping at all) better made with your input than guessed at through more trial-and-error rounds while you're away from a laptop. Current state on `feat/llm-quality-scoring`: the corrected (non-leaked) prompt is committed, real progress, not fully resolved -- full test suite still passes. Options for when you're back:
1. Ship as-is with this as a known, documented limitation, iterate later with more real-world data as actual users hit it.
2. Try removing the deterministic quantified-impact line and re-test (my one untested hypothesis above).
3. A more substantial rework — e.g., explicit few-shot examples per vertical, or moving away from a fixed 5-flag system toward something with a wider judgment surface.

## Summary

| Tier | n | Mean score | Range |
|---|---|---|---|
| Top | 15 | 98.8 | 98–100 |
| Mid | 5 | 77.0 | 73–83 |
| Bad | 5 | 71.0 | 68–73 |

Directionally correct — top clearly separates from mid/bad on the synthetic set — but real-data testing (added after this report's first version, see "Update" below) surfaced a serious issue that changes the bottom-line recommendation. Read that section first.

## UPDATE — real-data test (2 actual engineers' actual published resumes)

The synthetic set above was built entirely from *teaching-example* bullets, which are written to demonstrate the metrics-heavy style resume guides push ("cut X from A to B"). To test against real, unedited writing, I pulled two real individuals' actual self-published CVs from public GitHub repos (`sourabh_bajaj/resume`-style and `arasgungore/arasgungore-CV`-style — people who put their real CV on GitHub for professional visibility, not a private-feedback post; real names/contact info discarded entirely, never stored, see `quality-scoring-eval/real_resumes.py`). Both are unambiguously strong real careers — one a real Google + Coursera senior engineer with a Georgia Tech M.S., one a real Max Planck Institute robotics researcher — verifiable, not hypothetical "top-tier."

**Both scored 73–75/100 with a ROASTED stamp** — worse than every single synthetic "mid-tier" resume in this eval, and in the same range as the synthetic "bad-tier" set. `NO_QUANTIFIED_IMPACT` and `GENERIC_BULLETS` fired on both, every single time (6/6 runs across both resumes).

Why: both real resumes demonstrate seniority through **technical specificity and pedigree** (naming exact protocols/frameworks/algorithms, working at Google/Coursera/Max Planck) rather than through **quantified business metrics** (percentages, dollar figures, before/after numbers). That's a completely normal, legitimate senior-engineer writing style, especially in research/infra/systems roles — but the prompt's only calibration example (`workers/scoring/pipeline/prompt_builder.py`) explicitly defines "not generic" as having a metric: *"Led a 4-engineer team to cut deploy time from 45min to 6min."* Nothing in the prompt tells the model that deep technical specificity is an equally valid alternative signal of quality. The feature is currently, in effect, scoring for *one specific resume-writing style* and treating everyone else's as a defect — which is exactly the risk Finding 2 (below, from the synthetic set) pointed at, now confirmed on real people's real, successful careers rather than just a hypothesis.

**This also revised the consistency finding.** The synthetic set showed zero variance across 18 repeat calls (Finding 1, below) — that held up on *clear-cut* cases, but not here: across the 6 real-resume repeat runs, the exact flag set changed between runs for both resumes (e.g. one run added `BUZZWORD_FILLER`, another added `WEAK_ACTION_LANGUAGE` instead, for the identical input), and one resume's score genuinely drifted (75 → 73 → 73) rather than just swapping which flags summed to the same total. Consistency is real on unambiguous inputs; it's not guaranteed on borderline ones, and real resumes apparently hit that borderline more than my synthetic set did.

**Recommendation, revised**: I'd now call this a fix-before-relying-on-it issue, not a nice-to-have. The scoped fix is the same one Finding 2 already proposed — add a second calibration example to the prompt showing that named technical specificity/pedigree (without a metric) is also NOT generic — but the priority is higher now that it's confirmed against two real, verifiably excellent engineers' real resumes, not just synthetic quant/IB fixtures.

| Resume | Run | Score | Stamp | Flags |
|---|---|---|---|---|
| real_swe_technical_depth_1 (Max Planck robotics researcher) | 0 | 75 | ROASTED | BUZZWORD_FILLER, GENERIC_BULLETS, NO_QUANTIFIED_IMPACT |
| | 1 | 75 | ROASTED | GENERIC_BULLETS, NO_QUANTIFIED_IMPACT, WEAK_ACTION_LANGUAGE |
| | 2 | 75 | ROASTED | GENERIC_BULLETS, NO_QUANTIFIED_IMPACT, WEAK_ACTION_LANGUAGE |
| real_swe_narrative_style_1 (Google + Coursera senior engineer) | 0 | 75 | ROASTED | GENERIC_BULLETS, NO_QUANTIFIED_IMPACT, WEAK_ACTION_LANGUAGE |
| | 1 | 73 | ROASTED | GENERIC_BULLETS, NO_QUANTIFIED_IMPACT, SHALLOW_CONTENT, WEAK_ACTION_LANGUAGE |
| | 2 | 73 | ROASTED | GENERIC_BULLETS, NO_QUANTIFIED_IMPACT, SHALLOW_CONTENT, WEAK_ACTION_LANGUAGE |

## Original findings (synthetic set)

## Finding 1: Consistency is excellent *(on the synthetic set — see the real-data update above for the more complete picture)*

6 resumes (2 per tier) were run 3 times each — 18 repeat calls. **Zero variance.** Every single repeat produced the identical score and the identical flag set, every time. This was genuinely not guaranteed going in (LLM judgment calls are not inherently deterministic) and is a real point in the feature's favor on unambiguous inputs — a user re-submitting the same resume, or two near-identical resumes, will get consistent treatment, at least when the resume isn't near a judgment boundary.

## Finding 2: A real, non-trivial vertical skew — SHALLOW_CONTENT fires much more on HFT/Quant and IB resumes than SWE ones

| Vertical | n | Flagged (any) |
|---|---|---|
| SWE | 7 | 2/7 (29%) |
| HFT/Quant | 4 | **4/4 (100%)**  |
| IB | 4 | 3/4 (75%) |

Every single HFT/Quant resume in the top tier got `SHALLOW_CONTENT`, despite being built from genuinely strong, metrics-real bullets (Sharpe ratio improvements, latency numbers, P&L figures) — the same caliber of content as the SWE resumes that mostly passed clean.

**I checked whether this is just a word-count artifact** (my quant/IB fixtures happen to have fewer bullets than the SWE ones) — it's not clean-cut. `ib_ma_analyst_1` (75 words) wasn't flagged; `ib_lbo_1` (also 75 words) was. `faang_frontend_2` (79 words) wasn't flagged; `faang_backend_2` (80 words) was. Length alone doesn't predict it.

What I think is actually happening: quant/HFT and IB bullets are conventionally more terse and single-clause ("Built a factor model combining momentum and value signals across 2,000 US equities, improving Sharpe ratio from 0.9 to 1.4") than typical SWE bullets in this set, which often stack more descriptive clauses onto one bullet ("Optimized 14 slow PostgreSQL queries identified via pg_stat_statements, adding partial indexes and rewriting N+1 patterns, cutting average API response time from 800ms to 95ms"). `SHALLOW_CONTENT`'s prompt definition ("technically present but superficial — one-line descriptions with no real depth") may be implicitly calibrated toward SWE-style bullet density, penalizing a writing style that's normal and appropriate for finance/quant resumes rather than actually indicating shallow content.

**I can't fully confirm this is genuine vertical bias vs. a fixture-construction artifact from here** — the honest next step is a follow-up test holding bullet count and clause-density constant across verticals to isolate the variable. But it's consistent and worth taking seriously before shipping: real quant/IB users could see their score dinged for writing in the style that's actually correct for their field.

## Finding 3: The scoring has limited resolution once a resume is "clearly weak" — mid and bad tiers overlap

| Tier | resume | score | flags |
|---|---|---|---|
| mid | mid_swe_support_1 | 73 | GENERIC_BULLETS, NO_QUANTIFIED_IMPACT, SHALLOW_CONTENT, WEAK_ACTION_LANGUAGE |
| mid | mid_finance_analyst_1 | 73 | *(identical 4 flags)* |
| mid | mid_swe_3 | 73 | *(identical 4 flags)* |
| **bad** | **bad_swe_2** | **73** | ***(identical 4 flags)*** |
| **bad** | **bad_finance_1** | **73** | ***(identical 4 flags)*** |
| **bad** | **bad_quant_1** | **73** | ***(identical 4 flags)*** |

Three resumes I built as "mid" (mediocre-but-real, TCS-support-tier) and three I built as "bad" (deliberately hollow, "Senior Manager of Being Busy"-tier) landed at the **exact same score with the exact same flags** — indistinguishable by this feature. Only the two `bad` resumes that also used explicit corporate buzzwords ("Team Player, Self Starter, Results-Driven, Synergy") stood out, dropping to 68 via the extra `BUZZWORD_FILLER` flag.

This makes sense mechanically: once a resume lacks quantification and specificity, it tends to trip all 4 of `GENERIC_BULLETS`/`NO_QUANTIFIED_IMPACT`/`SHALLOW_CONTENT`/`WEAK_ACTION_LANGUAGE` together as a bundle (they're correlated symptoms of the same root problem), leaving `BUZZWORD_FILLER` as the only real differentiator left once you're already in that bucket. The 5-flag deduction design has a real floor effect — it distinguishes "has real quantified impact" from "doesn't" very well (that's most of what separates the top tier from everything else), but doesn't currently have much resolution *within* "doesn't."

## Full results table (primary run only, n=25)

| Tier | Vertical | Resume | Score | Stamp | Flags |
|---|---|---|---|---|---|
| top | SWE | faang_backend_1 | 100 | SOLID | — |
| top | SWE | faang_frontend_1 | 100 | SOLID | — |
| top | SWE | faang_fullstack_1 | 98 | MID | SHALLOW_CONTENT |
| top | SWE | faang_devops_1 | 100 | SOLID | — |
| top | SWE | faang_newgrad_1 | 100 | SOLID | — |
| top | SWE | faang_backend_2 | 98 | MID | SHALLOW_CONTENT |
| top | SWE | faang_frontend_2 | 100 | SOLID | — |
| top | HFT/Quant | hft_quant_researcher_1 | 98 | MID | SHALLOW_CONTENT |
| top | HFT/Quant | hft_quant_dev_1 | 98 | MID | SHALLOW_CONTENT |
| top | HFT/Quant | hft_quant_strat_1 | 98 | MID | SHALLOW_CONTENT |
| top | HFT/Quant | hft_quant_researcher_2 | 98 | MID | SHALLOW_CONTENT |
| top | IB | ib_ma_analyst_1 | 100 | SOLID | — |
| top | IB | ib_sellside_1 | 98 | MID | SHALLOW_CONTENT |
| top | IB | ib_lbo_1 | 98 | MID | SHALLOW_CONTENT |
| top | IB | ib_generalist_1 | 98 | MID | SHALLOW_CONTENT |
| mid | SWE | mid_swe_support_1 | 73 | ROASTED | GENERIC_BULLETS, NO_QUANTIFIED_IMPACT, SHALLOW_CONTENT, WEAK_ACTION_LANGUAGE |
| mid | SWE | mid_swe_2 | 83 | MID | GENERIC_BULLETS, SHALLOW_CONTENT, WEAK_ACTION_LANGUAGE |
| mid | IB | mid_finance_analyst_1 | 73 | ROASTED | GENERIC_BULLETS, NO_QUANTIFIED_IMPACT, SHALLOW_CONTENT, WEAK_ACTION_LANGUAGE |
| mid | HFT/Quant | mid_quant_1 | 83 | MID | NO_QUANTIFIED_IMPACT, SHALLOW_CONTENT, WEAK_ACTION_LANGUAGE |
| mid | SWE | mid_swe_3 | 73 | ROASTED | GENERIC_BULLETS, NO_QUANTIFIED_IMPACT, SHALLOW_CONTENT, WEAK_ACTION_LANGUAGE |
| bad | SWE | bad_swe_1 | 68 | ROASTED | BUZZWORD_FILLER, GENERIC_BULLETS, NO_QUANTIFIED_IMPACT, SHALLOW_CONTENT, WEAK_ACTION_LANGUAGE |
| bad | SWE | bad_swe_2 | 73 | ROASTED | GENERIC_BULLETS, NO_QUANTIFIED_IMPACT, SHALLOW_CONTENT, WEAK_ACTION_LANGUAGE |
| bad | SWE | bad_swe_3 | 68 | ROASTED | BUZZWORD_FILLER, GENERIC_BULLETS, NO_QUANTIFIED_IMPACT, SHALLOW_CONTENT, WEAK_ACTION_LANGUAGE |
| bad | IB | bad_finance_1 | 73 | ROASTED | GENERIC_BULLETS, NO_QUANTIFIED_IMPACT, SHALLOW_CONTENT, WEAK_ACTION_LANGUAGE |
| bad | HFT/Quant | bad_quant_1 | 73 | ROASTED | GENERIC_BULLETS, NO_QUANTIFIED_IMPACT, SHALLOW_CONTENT, WEAK_ACTION_LANGUAGE |

## What I'd recommend, in priority order (revised after the real-data update)

1. **Fix the metric-only calibration before trusting this for real users — this is now the priority item.** Confirmed on two real, verifiably strong engineers' actual resumes (Google/Coursera senior engineer, Max Planck robotics researcher), not just synthetic quant/IB fixtures: `NO_QUANTIFIED_IMPACT` + `GENERIC_BULLETS` fire on any resume demonstrating strength through technical specificity/pedigree instead of "cut X from A to B" metrics, dropping real strong resumes to the same 73-75 range as synthetic mediocre-to-bad ones. Scoped fix: add a second calibration example to the prompt (`workers/scoring/pipeline/prompt_builder.py`) explicitly showing a named-technical-specificity bullet (no metric) as NOT generic/NOT unquantified — e.g. something like the Max Planck example's "optimized a C++ ROS package for real-time conversion of 3D motion controller events, achieving high-frequency and buffer-free synchronization." I'd want to re-run at least these two real resumes plus the synthetic HFT/Quant set against the updated prompt before considering this closed.
2. **The original vertical-skew finding (below) is the same root cause, now confirmed rather than hypothesized** — no separate follow-up needed, the fix above should address both.
3. **Consider whether the mid/bad floor effect matters for your use case.** If the product goal is mainly "distinguish good from not-good," the current resolution is probably fine as shipped once #1 is fixed. If you want finer-grained differentiation among weak resumes specifically, that likely needs either more flag codes covering different failure modes, or a move away from fixed per-flag point values toward something with more granularity.
4. **Re-verify consistency after the prompt fix, not before.** The synthetic set's 18/18-identical result doesn't hold on borderline real content (see update above) — worth re-checking once the calibration example is added, since that changes what counts as borderline.

## Files

- `quality-scoring-eval/resumes.py` — the 25-resume synthetic fixture set, with sourcing notes
- `quality-scoring-eval/real_resumes.py` — the 2 real-individual resumes used in the update, with sourcing/redaction notes
- `quality-scoring-eval/eval_results.json` — raw results, synthetic set (37 calls)
- `quality-scoring-eval/real_eval_results.json` — raw results, real-resume update (6 calls)
- `quality-scoring-eval/REPORT.md` — this file

Not committed to git — these are analysis artifacts, not code; your call whether to keep them in the repo (e.g. `docs/` or similar) or discard once reviewed.
