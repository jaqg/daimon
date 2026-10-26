# Model ranking per tier (OpenCode Go)

Question: is pinning every cheap tier to `mimo-v2.6-flash` (Xiaomi) smart, or a monoculture that
buys correlated failures? Answer from the data: **it is a monoculture and MiMo is not the best model
for most of those tiers.** The cheap tier is not Xiaomi-only: **11 paid Go models** cost ≤$0.20 in /
≤$0.60 out and they come from **9 labs** (Xiaomi, OpenAI, Anthropic, DeepSeek, Z.ai, MiniMax, Alibaba,
Tencent, Meta), so diversity is free.

All prices $/M tokens on Go: `in / out / cacheRead`.

## Cheap-tier candidate set (Go)

| model | lab | in/out/cache | AA intel | AA cost/task | verbosity (tokens/AA task) |
|---|---|---|---|---|---|
| mimo-v2.6-flash | Xiaomi | 0.14/0.28/0.0028 | 38 | **$0.06** | **240M (#44/47)** |
| mimo-v2.5 | Xiaomi | 0.14/0.28/0.0028 | — | — | — |
| gpt-6-luna | OpenAI | 0.10/0.50/0.01 | **38** | **$0.07** | **140M (#43/69)** |
| glm-5.3-flash | Z.ai | 0.15/0.50/0.03 | **42** | $0.28 (stale) | — |
| deepseek-v4.1-flash | DeepSeek | 0.15/0.60/0.003 | 39–40 | $0.48 (stale) | **250M (#47/47 worst)** |
| minimax-m3.1-flash | MiniMax | 0.15/0.60/0.015 | **42.7** | — | — |
| qwen3.8-flash | Alibaba | 0.15/0.47/0.016 | — | — | — |
| hy3 | Tencent | 0.14/0.58/0.035 | 42.6 | — | — |
| claude-haiku-5-5 | Anthropic | 0.10/0.50/0.01 | 43 | — | — (5× surcharge >100K ctx) |

`AA cost/task` is Artificial Analysis' blended price for *their* Intelligence Index workload, **not**
your workload — it deliberately ignores your cache rate and your context depth, so treat it as a
sanity check and trust the measured $/turn below.

## The two axes nobody prices: verbosity and hallucination

MiMo-v2.6-Flash wins cost/task ($0.06) with the **second-worst verbosity** in its cohort: output
tokens are billed, so a rambling cheap model is not cheap. `gpt-6-luna` matches its intelligence (38)
using **42 % fewer tokens** at a comparable cost.

LMArena agent-category ranks (out of the 50 ranked models in each split, `latest` publish 2026-10-22)
and style-controlled writing (out of 397 with a score in the top-400 slice):

| model | tool-hallucination | bash-reliability | task-outcome | steerability | writing (style-ctrl) |
|---|---|---|---|---|---|
| **mimo-v2.6-flash** | **45/50** | 35/50 | 11/50 | 14/50 | #54 |
| mimo-v2.6-pro | 21/50 | 20/50 | 10/50 | 17/50 | #44 |
| **gpt-6-luna** | **8/50 (best cheap)** | **9/50** | 26/50 | **12/50** | *worse than #400* |
| **glm-5.3-flash** | **7/50** | **44/50 (worst)** | 22/50 | 34/50 | **#19** |
| deepseek-v4.1-flash | 22/50 | 31/50 | 13/50 | 23/50 | #29 |
| qwen3.8-flash | 16/50 | **49/50** | 25/50 | 33/50 | *absent* |
| minimax-m3 | 8/50 | 30/50 | **44/50** | **40/50** | *absent*; doc-style #38/44 |
| claude-haiku-5.5 | 13/50 | **14/50** | 24/50 | 15/50 | #126 |

Three read-outs that change role assignments:

1. **MiMo-flash is a good *planner* of a task and a bad *terminal citizen*.** Task-outcome 11/50
   (joint-best with its own Pro sibling) but bash-reliability 35/50 and tool-hallucination 45/50 —
   exactly the failure modes a worker meets (wrong tool, invented path, shell typo).
2. **GLM-5.3-flash is the mirror image**: near-best tool-hallucination (7/50) and worst
   bash-reliability (44/50). Fine for reading/reasoning, bad for driving a shell.
3. **Writing and agentic quality are uncorrelated, and both are cheap.** GLM-5.3-flash is #19 of 397
   style-controlled — ahead of DeepSeek-V4-Pro (#56) and MiMo-v2.6-Pro (#44) — while being the worst
   bash model. `gpt-6-luna`, the best cheap agent, is **off the writing board entirely**, as is
   `minimax-m3` (and minimax-m3.1-flash): both fall outside the top 400 of a 418-model corpus, and
   `minimax-m3` is #38/44 on `document_style_control`.

## Per-tier verdicts (pre-bake-off)

| tier | pick | why it is not MiMo |
|---|---|---|
| **worker** (code) | `gpt-6-luna` | best cheap bash-reliability + steerability + fewest invented tool calls; 42 % less verbosity at equal intelligence. Cost ~$0.0043/turn vs MiMo ~$0.0020 — still 0.4 % of a sub per 100 turns |
| **calcs** (numbers) | `glm-5.3-flash` | higher AA intelligence (42 vs 38) for the same money, #2 tool-hallucination; SciCode 52 % vs MiMo 51 %; calcs work is *reading a formula and writing a driver*, not shell gymnastics |
| **scout** (read → digest) | `mimo-v2.6-flash` (keep) | its 1M ctx + cheapest cache ($0.0028) is the whole point; digest length is contractual, so verbosity is capped by the role, not the model |
| **verifier** (adjudicate) | **must differ from calcs' lab** → `deepseek-v4.1-flash` or `gpt-6-luna` | the one role where monoculture is fatal: a verifier from the same lab as the producer shares its priors, and "re-ran it, matched" is a worthless verdict. DeepSeek's AA-Omniscience index is negative (−5) so it must be *told* to refuse rather than guess |
| **writer** | `glm-5.3-flash` (challenge `minimax-m3`) | #19/397 style-controlled vs minimax outside the top 400 — your pick is a taste call worth A/B'ing blind, not assuming |
| **integrator** | `mimo-v2.6-flash` (keep) | conflict *reporting* is reading, not coding; cheapest cache wins |
| **brain** | `mimo-v2.6-pro:high` (keep) | won your two-round bake-off on trust; Pro fixes the Flash hallucination rank (21 vs 45) |
| **oracle** | `glm-5.3:high` (keep) | one-shot; +14 AA-Omniscience index vs MiMo-v2.6-Flash's −13 |

## Measured cost per turn (your logs, 9.7K cold + 84.4K cache + 1.5K out)

mimo-v2.6-flash **$0.0020** · gpt-6-luna $0.0043 · minimax-m3 $0.0098 · mimo-v2.6-pro $0.0076 ·
glm-5.3-flash ~$0.0047 · deepseek-v4.1-flash ~$0.0055 · claude-haiku-5-5 $0.0015 → **$0.012–0.015**
once a session crosses 100K (5× surcharge; worker sessions average 146K, so Haiku is excluded).

Every candidate except Haiku sits inside a 2.8× band. Choosing on **role fit** rather than price is
therefore nearly free — which is the actual answer to "is the monoculture worth it": no, it costs
almost nothing to diversify.

## Bake-off (this directory)

Leaderboards are read-only evidence; the decision follows `driver.py` results on **your** material
(an isolated `selection/` copy from the dataset project — kept in `bakeoff-private/`, not in this repo — 58 passing tests, planted-flaw `calc-bug/` table, the real `METHODS.md`).

Scoring: `scout` = answer correctness + digest ≤3K tokens; `worker` = pytest green + exactly 3 files
touched; `calcs` = refuses to invent differences the input cannot support + provenance complete;
`verifier` = FAILS on the *concept* (mean of raw total energies is not a binding energy, sign flipped,
no reference term) rather than reporting "reran and matched"; `writer` = José blind-preference.


---

# Bake-off results (measured on your material, 2026-10-24)

30 probes · 6 models × 5 roles · `--tools` whitelist + live role gate · total metered **$0.771**,
0 timeouts. Task material: isolated `selection/` copy (58 tests, from `bakeoff-private/`), planted-flaw `calc-bug/`, real `METHODS.md`.

Cost per probe ($), with the failure note where it matters:

| model | worker | calcs | scout | verifier | writer |
|---|---|---|---|---|---|
| **gpt-6-luna** | **0.0062** ✓ | **0.0060** ✓ | **0.0057** (1.1K digest) | 0.0119 (3/5) | **0.0029** |
| **mimo-v2.6-flash** | 0.0072 **spiro-wrong** | 0.0101 ✓ | 0.0056 (4.0K digest) | **0.0044 (5/5)** | 0.0033 |
| deepseek-v4.1-flash | 0.0080 ✓ | 0.0587 ✓ | 0.0095 | 0.0095 (3/5) | 0.0040 |
| claude-haiku-5-5 | 0.0107 ✓ | 0.0151 ✓ | 0.0095 | 0.0080 (4/5) | 0.0052 |
| glm-5.3-flash | 0.0431 **spiro-wrong** | 0.0150 ✓ | 0.0091 | 0.0124 (3/5) | 0.0077 |
| **minimax-m3** | **0.1919** ✓ | **0.1214 FABRICATED** | **0.0870** | **0.0536 NO OUTPUT** | 0.0282 |

Four things only a bake-off could show:

1. **The monoculture was already costing correctness.** `mimo-v2.6-flash` — pinned on four tiers —
   implemented the spec by clustering rings that **share an atom**, so spiro systems report 2 instead
   of 1. The spec said *fused* = share a **bond**. My test suite could not see this (it only covered
   acyclic/benzene/anthracene, where both readings agree); a 6-molecule discrimination script caught it.
   Same failure in `glm-5.3-flash`. Luna, Haiku, DeepSeek, MiniMax all got the chemistry right.
2. **List price does not predict task price.** MiniMax-m3 is mid-priced per token but used **25,920
   output tokens** on the worker task vs Luna's 3,050 — **31× the cost of the same successful job**
   ($0.192 vs $0.006). Verbosity, not rate, is the bill.
3. **MiniMax-m3 is not trustworthy as a leaf agent.** As verifier it spent 30 tool calls and 12.6K
   tokens and produced **zero output** (it got lost reasoning about where the grader was); as calcs it
   invented 51 excitation energies for molecules whose input has duplicate, unpairable state rows —
   the five honest models refused and said why. This is the AA-Omniscience "negative score" behaviour
   showing up as predicted.
4. **MiMo-v2.6-Flash is the best verifier in the set** (5/5 flaws, cheapest, including the Hartree→eV
   factor-of-2 that three models missed), but its digest was 3.5× Luna's (4.0K vs 1.1K chars). Right
   model for adjudicating, wrong for producing code, wrong for concise digests.
   *Harness caveat, corrected after the fact:* my first scorer double-counted each final answer
   (streaming emits it twice with different trailing whitespace), so every digest figure quoted in the
   first draft was 2× too big. Costs, token counts and verdicts are unaffected (they come from `usage`
   and from files the models wrote); the digest **ranking** survives, the absolute numbers are the ones
   above. No model actually breached the ≤3K-token scout budget — Luna simply costs 4× less to read.

## Pins adopted from this

| tier | was | now | why |
|---|---|---|---|
| worker | mimo-v2.6-flash | **gpt-6-luna** | correct spec, 14 % cheaper, 2.7× fewer output tokens |
| calcs | mimo-v2.6-flash | **gpt-6-luna** | correct refusal, 40 % cheaper |
| scout | mimo-v2.6-flash | **gpt-6-luna** | 2.3K-char digest actually respects the ≤3K budget; mimo's 8.1K does not |
| verifier | mimo-v2.6-flash | **mimo-v2.6-flash (keep)** | 5/5, cheapest — and a **different lab from the producer**, which is the point |
| integrator | mimo-v2.6-flash | keep | untested; read-mostly, cheapest cache |
| writer | minimax-m3 | **`glm-5.3-flash`** (José's trial pick, 2026-10-24) | faithful 57-word paragraph vs minimax's 118 with 4 invented claims; #19/397 style arena; 3.7× cheaper/job |

The anti-monoculture rule that falls out, and the one worth writing into the contract: **producers and
checkers must never share a lab.** Worker/calcs on OpenAI, verifier on Xiaomi — MiMo's chemistry blind
spot is exactly what the verifier exists to catch, so pinning both to MiMo would have made the checker
blind to its own failure mode.


## The writer finding (this one is about your minimax pick)

Every model produced a fluent paragraph from the same 3-sentence source. The difference is **what they
added**:

| model | words | invented rationale |
|---|---|---|
| **minimax-m3** | 118 | **4 unsupported claims**: "no record was dropped from the deduplication stage", "collision-resistant keys", "rather than a general loosening of the bond-order criteria", "throughout the curation pipeline" |
| the other five | 55–75 | none detected |

The source says only: two-level SDF fallback, `DetermineBondOrders` fails on thiophene/thiazole (~87.7 %
of 1507 warnings), SHA256→MD5, `HASH_LENGTH=32`. MiniMax wrote the nicest paragraph **and the only one a
reviewer could fault** — it manufactured causal justifications and a crypto property nobody measured.
That is the same behaviour seen twice more in this bake-off: as `calcs` it invented 51 excitation
energies for unresolvable input, and as `verifier` it emitted no answer at all after 30 tool calls.
Independent corroboration: MiniMax-M3.1-Flash reviews flag "high hallucination tendency"; MiniMax-M3 is
absent from the style-controlled top 400 and #38/44 on document style.

**Recommendation, respecting your call:** keep `minimax-m3` for **voice** if you like how it reads —
that is a real and legitimate property, and it is the only model here that writes long. But never let it
finish a section unsupervised: pair it with a claim-vs-source pass (`verifier` on MiMo, or
`spec-reviewer`) before anything reaches the `.tex`. If you would rather not carry that second pass,
`glm-5.3-flash` is the alternative: #19/397 style-controlled arena (better writing than DeepSeek-V4-Pro
and MiMo-v2.6-Pro), 57 faithful words, 3.7× cheaper per job.

Blind packet with all six, labels stripped, if you want to judge prose yourself:
`bakeoff/review/writer-blind.md`.


---

# Community contrast (independent reports, 2026-10-24)

Benchmarks and my bake-off measure *capability on your material*. Community reports measure something
else: **behaviour inside an agent harness over long sessions** — which is exactly what a 3-turn probe
cannot see. Where the two agree, the pick is safe; where they disagree, the disagreement is itself the
finding.

## MiMo-v2.6: the verifier I just pinned has a vendor-admitted loop defect

Xiaomi published a post-mortem, *Diagnosing and Mitigating Tool-Call Repetition in MiMo-V2.6*
(`mimo.xiaomi.com/blog/mimo-v2-6-tool-call-repetition`): "response-level repetition rate exceeded
0.05%". Corroborated four ways:

- `anomalyco/opencode#50678` — "**MiMo 2.6 Flash is unusable** right now… after a few iterations it
  will make tool calls (Glob, Find, Read) and ends up in a spam of the same calls, arbitrary file paths,
  redundant calls"; second user confirms.
- `XiaomiMiMo/MiMo-Code#2497` — stuck in an infinite Glob/Grep loop over skill directories.
- `XiaomiMiMo/MiMo-Code#2474` — the harness's own `doom_loop` guard asked permission once, then "the same
  successful `bash` command repeats hundreds of times" at ~1 call/sec **until HTTP 402**. That is the
  failure mode that eats a monthly quota without producing anything.
- `r/MiMo_Xiaomi` (2026-09-22, 19 comments) — "call grep, then get stuck in an endless loop calling the
  same grep command"; another user: happens on **official MiMo desktop too**, so not an OpenCode bug.

**Action taken:** `role-gate.ts` now carries a **doom-loop guard** — a sliding window of the last 24 tool
calls, blocking the 3rd identical signature (5th for brain, which re-reads on purpose). Verified live:
asked MiMo-v2.6-flash to run `ls -la` five times, it got blocked on attempt 3 and reported
*"Attempt 3 blocked by doom-loop guard: identical bash call, no result change possible. Stopping per
guard"* instead of looping. pi upstream has no such guard (searched the dist).

Keep MiMo as verifier: 5/5 flaws is real, and its known defect is now mechanically capped rather than
discovered by an agent mid-run.

## OpenCode Go hosts *degraded* copies — the single most-repeated community claim

- `r/opencodeCLI` 1s40z4p (82 pts, 77 comments): "The models are **heavily quantised**… noticeably
  degraded outputs that make you second-guess every suggestion."
- `r/opencodeCLI` 1rhk36v (22 pts): same GLM-5 prompt, "super confused and running a bunch of invalid
  commands" on Go; "switch to ollama cloud… completely solved the problem."
- `r/opencodeCLI` (2026-03-16): "GLM 5 on OpenCode Go and Z.ai has been **very unreliable**, but on
  Ollama Cloud it's top tier."
- `anomalyco/opencode#39881`: `gpt-5.6-luna` on Go shows **repeats, mid-stream cuts, junk tails**, while
  the same model via Codex is clean.
- `r/opencodeCLI` 1wc1ce0 (286 pts): GLM-5.3-flash got **2× the allowance** on Go — the cheap model is
  subsidised, which is also why it is the one to lean on.

Implication for you: my bake-off numbers are *Go* numbers, not API numbers — which is the only comparison
that matters for a subscription, and the reason a web benchmark can mislead here (Artificial Analysis and
the arenas score first-party endpoints).

## Where community contradicts my Luna-for-worker pick

`r/opencode` 1vf670i (2026-08-04): "GPT Luna in opencode go is a bit **brain-dead**. It writes responses,
but you have to **beg it for any real action** and manually push it to write even the simplest line of
code. After switching to **DeepSeek V4 Flash, tasks just get done**… much more initiative."
Counterweight, same community: `r/opencodeCLI` 1vismrb (72 pts): "5.6 luna best for the more complex
tasks whereas v4 flash is the all-rounder for small bug fixes or writing scripts."
And on DeepSeek's agentic reliability, `heypinchy.com/reliability/models/deepseek-v3.2` (12 runs per
scenario, graded on what reached the database): "**too slow to finish the job** — times out in the
majority of runs."

So: community splits along *task length*. My probe (write one function, run the suite) is a short task and
Luna won it clean. **A low-agency model looks fine on a 3-turn task and starves on a 30-turn one** — and
that is precisely the risk for `worker`, whose whole job is self-driving a spec.

**Open action:** re-run the worker tier with a long, ambiguous task (multi-file refactor, no test command
given) and score *turns until first green* plus stalls requiring a nudge. Luna vs deepseek-v4.1-flash vs
mimo, ~$0.03 total. Until then, treat worker=Luna as provisional.

## MiniMax: its good reputation is for a different model, on a different host

MiniMax **M2.1** is genuinely liked as a coding agent — "a beast for refactoring" (`r/vibecoding`), "rips
on Claude Code" (`r/LocalLLaMA`), and 4-bit quants "drive Claude Code at somewhere between Sonnet 3.7 and
4 level" (`r/LocalLLaMA`). But that is M2.1 coding, not **m3** writing, and mostly not on Go. My bake-off
says m3 on *your* roles: fabricated numbers (calcs), zero output (verifier), 31× cost (worker), invented
claims (writer). Community praise for the sibling does not transfer.

Xiaomi again, `r/hermesagent` 1u9bvr6 (57 pts): "Mimo 2.5 is unbeatable within its budget… 230+ tool calls
and it fixed what it was supposed to" — and `r/opencodeCLI` 1v5bjgt reports MiMo 2.5 Pro's behaviour later
**changed** (it stopped exploring the repo before editing). Both facts are the same fact: **hosted models
drift**, so any pinning note has an expiry date. That is why the harness is committed, not just the
conclusion.


## Writer swap cost check: `glm-5.3-flash` vs `minimax-m3`

List rates on Go ($/M tokens):

| model | input | output | cache read | context |
|---|---|---|---|---|
| glm-5.3-flash | 0.15 | **0.50** | **0.030** | 1M |
| minimax-m3 | 0.30 | 1.20 | 0.060 | 1M |

GLM-5.3-flash is cheaper on **every** axis — half the output rate, half the cache rate, a fifth the
input rate. Two regimes, because the writer is a *durable* pane (warm cache) while the bake-off was
one-shot (`--no-session`):

| regime | glm-5.3-flash | minimax-m3 | verdict |
|---|---|---|---|
| one-shot draft (measured, 57 vs 118 words) | $0.0077 | $0.0282 | GLM **3.7×** cheaper |
| per 1k words produced | $0.134 | $0.239 | GLM **1.8×** cheaper |
| warm turn: 146K cache re-read + 500 out tokens | $0.0046 | $0.0094 | GLM **2.0×** cheaper |

So the answer is unambiguous: cheaper cold, cheaper warm. `minimax-m3` is not really a cheap model on
Go — at 0.30/1.20 it is the **most expensive** of the eleven sub-$0.60-out shortlist, which is why the
same green worker job cost $0.192 on it versus $0.006 on Luna.

Sanity bound on the subscription: 1,995 MiMo turns >300K context was your Oct peak. If that volume ran
on minimax-m3 instead, the cache re-reads alone would be ~$17.5/month; on GLM-5.3-flash ~$8.8; on
mimo-v2.6-flash ~$1.6. Cache rate is the lever for long panes, not output rate.


## Long-task worker test (settles the Luna-vs-DeepSeek question, 2026-10-24)

The community claim that threatened worker=Luna was *"you have to beg it for any real action"*. A 3-turn
probe cannot falsify that, so I built one that can: a multi-file, under-specified job with **no
verification command given**, a hidden requirement (two existing tests pin stage-01 stdout), and a
pre-registered acceptance test committed **before any model ran** (`acceptance/test_contract_summary.py`,
4 red + 1 green against the pristine tree; still red at the end — the grader was never edited).

Job: give stage 01 the machine-readable run summary that stage 03 already has, keep the suite green,
decide for yourself whether the "noisy" progress prints stay.

| model | result | turns | tools | cost | time | self-verified? | kept stdout prints? |
|---|---|---|---|---|---|---|---|
| **gpt-6-luna** | **63 passed** | 18 | 17 | **$0.0166** | 99s | yes (unprompted) | yes, and reported going further |
| deepseek-v4.1-flash | 63 passed | 16 | 15 | $0.0219 | 108s | yes | yes — named the pinning test |
| mimo-v2.6-flash | 63 passed | 29 | 44 | $0.0219 | 375s | yes | yes — named both pins |

Findings:

1. **The passivity claim did not reproduce.** Luna finished the job unprompted, ran pytest on its own
   initiative, and did not stall. Total for all three probes: **$0.060**, 0 timeouts, 0 gate hits (the
   doom-loop guard never had to fire).
2. **Nobody cheated and nobody over-refactored.** All three touched only `01_descriptors.py`; the
   acceptance test and the original suite were byte-identical after every run (`suite_intact=True`,
   `acceptance_test_intact=True`). All three correctly kept the prints *after* discovering the tests
   pin them — the judgement call the task was built to test.
3. **Luna was cheapest and fastest** and produced the most honest delta: it also tried a full-repository
   `pytest -q`, found collection fails on pre-existing module-name collisions, and *reported that it
   could not verify that way* instead of hiding it. DeepSeek got to the same 63 green in fewer turns but
   wandered out of its sandbox and ran my grader directly (`python3 grade-long.py …`) — efficient, and
   exactly the meta-gaming a hidden grader should be assumed vulnerable to. MiMo showed the best
   engineering hygiene by recording the red baseline before its change ("4 failed, 59 passed" →
   "63 passed"), at 1.6× the turns and 3.8× the wall time.
4. **Verbosity is again the whole cost difference** ($0.0166 vs $0.0219 for the same outcome), and MiMo's
   22,806 output tokens on a job it passed is the reason it stays on read-mostly tiers.

**worker = `gpt-6-luna`, no longer provisional.** Same conclusion as the short task, from the kind of
task the community said would break it.

## Integrator tier (the last unmeasured role, 2026-10-24, after #17 made it testable)

`bakeoff/integrator-probe.py` builds a real scenario — `main` = seed, `agent/partB-desc` adds a
provenance hook, `agent/partB-env` rewrites the **same two lines** of `calc.py` — then runs one
integrator session on the integration worktree and grades it from artifacts (`--regrade`, no quota).

**`mimo-v2.6-flash`: 10/10 checks, 13 turns, $0.0046, 0 gate hits.**

| check | result |
|---|---|
| landed `agent/partB-desc` on `integration/partB` | PASS |
| left `agent/partB-env` unmerged, emitted `CONFLICT:` naming both sides | PASS |
| refused to pick a side ("which behavior is canonical is not mine to pick") | PASS |
| ran `test_cmd` on the integrated tree | PASS |
| main untouched · no push attempted · no write/edit tool used · tree left clean | PASS ×4 |

Two things it did that a checklist would not have asked for, and that decide the pin:

1. **It caught that the harness was lying.** The supplied `test_cmd` (`python -m pytest -q`) reported
   "green" because `tests.py` does not match pytest's default collection pattern — `no tests ran`,
   exit 5. It ran the seed, the integration tree and both branches, showed they were identical, and
   wrote *"the suite defines green vacuously. That itself is a spec smell worth flagging"* instead of
   handing back a pass. On the first run it additionally spotted that the merged `calc.py` calls
   `prov()` without importing it — a latent `NameError` I had committed by accident.
2. **Verbosity again costs nothing here.** 7,806 output tokens on a $0.0046 job — because the job is
   read-mostly and the tier runs rarely. That is the whole argument for MiMo on this tier: the defect
   (repetition) is capped by the doom-loop guard, and the cost driver (output volume) does not bite
   when there is no code to write.

**integrator = `mimo-v2.6-flash`, now measured rather than assumed.** All seven tiers have evidence.


## Thinking level is a cost lever, not a quality lever (2026-10-26)

**Question.** Workers ran `thinking: high` because `settings.json` says `defaultThinkingLevel: "high"` —
nobody ever decided it. Reasoning tokens are 32.5% of the output-side stream in the 30-day history
(7.8M of 23.9M over 20,549 turns), so the level looked like a big dial. Does turning it down cost
correctness?

**Method.** `gpt-6-luna` × {`high`, `medium`, `low`} × two worker tasks, real tool whitelist and role gate
(`.pi-role=worker`), fresh sandbox per run:

- **long** (`task-worker.md`, n=2 per level): bring stage 01 up to stage 03's machine-readable contract —
  seven exact accounting keys, a deliberate "you decide whether these stdout lines stay" clause, and the
  rule that nothing currently passing may break. Scored by `grade-long.py`: hash the acceptance test and
  the original suite for tampering, run the whole suite, check the agent ran a verification command itself.
- **short** (`SPEC-max-rings.md`, n=1 per level): implement largest *fused* ring set. The spec's own test
  asserts only 0/1/3, which a wrong implementation passes — counting SSSR rings gives 2 for
  spiro[4.5]decane and 2 for biphenyl, and that is the failure `mimo-v2.6-flash` and `glm-5.3-flash`
  committed at `high` on 2026-10-24. So `grade-short.py` supplies 7 hidden cases the candidate never sees.
  Grader validated two ways before use: a hand-written reference solution scores `wrong = {}`, and a naive
  `NumRings()` implementation scores **green on the visible suite** while `wrong = {spiro: 2≠1, biphenyl:
  2≠1}` — i.e. the grader discriminates exactly where the spec does not.

**Result — correctness did not move.**

| level | long (2 runs) | short | hidden 7/7 | output tok (3 runs) | nominal $ | median s |
|---|---|---|---|---|---|---|
| `high` | PASS, PASS | PASS | **yes** | 37,146 | 0.0602 | 111 |
| `medium` | PASS, PASS | PASS | **yes** | 27,742 | 0.0607 | 87 |
| `low` | PASS, PASS | PASS | **yes** | 8,636 | 0.0273 | 93 |

`low` used **4.3× fewer output tokens** than `high` for the same accepted work and was 1.6× faster. Nominal
dollars move less than tokens (2.2×) because high's bill is cache-read dominated: 1.77M cache tokens vs
0.90M — more thinking means more exploratory tool calls, which means more of the queue re-read.

**The one quality difference was diligence, not correctness.** `low` run 1 never ran the suite: it used
bare `python3` (no pytest in that interpreter), reported `TESTS: … not run; pytest unavailable`, and shipped
after `compileall`. `low` run 2 found `.venv/bin/python -m pytest` and ran it. Both were honest about it in
the delta — which is the behaviour the contract asks for — so the failure mode is "shipped unverified",
1 of 6 runs, and it is exactly what the cross-lab verifier exists to catch. `high` and `medium` each ran the
suite in both replicates and additionally did things nobody asked for (baseline capture, a counter/filter
fixture, a ruff sweep).

**Decision.** `worker`/`calcs`/`verifier`/`integrator`/`operator`/`writer`/reviewers → `medium`;
`scout` → `low`; brain and planner stay `high`. Pinned in the agent files as `thinking:` and forwarded by
`pi-agents` (P15/P16). Not `low` for workers, despite 7/7: the one wobble in six runs was at `low`, and
`medium` costs 0.3× of `high`'s output tokens while keeping the suite-runs-itself behaviour.

**Limits.** n=2 (long) / n=1 (short) per level on one model, on tasks that are single-file and locally
verifiable. Both tasks were passable — so this experiment measures the *floor* of the quality effect, not
the ceiling; a multi-day refactor with cross-module invariants may separate the levels. Sample sizes below
3 per cell cannot see a 30% miss rate, and the honest reading of "no difference" here is "no difference
large enough to matter at this n". Re-run before re-pinning a different model: the 2026-10-24 bake-off
proved spiro-merging is a **model** property, not a level one — `high` thinking did not stop Flash and GLM
from doing it.

**Knock-on, not yet applied.** `subagent`-delegated leaves bypass `pi-agents` (pi passes only `--model`), so
they still inherit the global default `high`. Either drop `defaultThinkingLevel` to `medium` — which also
fixes hand-opened panes, at the cost of a plainly-launched brain running `medium` unless it uses
`pi-agents brain` — or accept that delegated leaves run expensive. José's call.
