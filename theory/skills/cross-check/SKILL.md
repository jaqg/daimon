---
name: cross-check
disable-model-invocation: true
description: "Multi-model mathematical verification. Runs the same math query through 2+ models independently, diffs outputs at the equation level, and flags discrepancies. Use after sympy-verify for extra confidence, or when you have a candidate answer and want independent confirmation. Trigger: \"cross-check this\", \"verify with another model\", \"second opinion\", \"independent verification\", \"does another model agree?\"."
compatibility: "Requires pi CLI with multiple model access. Uses pi --print for non-interactive invocation. Models must be configured in ~/.pi/agent/models.json or via built-in providers (opencode-go)."
---

# Cross-Check

Two (or three) models, one query. If they agree, confidence goes up. If they disagree, you see exactly where and how.

## Flags

Parse these from the user message or `/skill:cross-check` args:

| Flag | Default | Description |
|---|---|---|
| `--primary MODEL` | qwen3.7-max | Primary model for the query |
| `--alt MODEL` | deepseek-v4-pro | Alternate model for independent verification |
| `--three-way` | off | Add kimi-k2.6 as third model (majority vote) |
| `--third MODEL` | kimi-k2.6 | Override third model (requires --three-way) |
| `--save PATH` | (none) | Save full diff report to PATH |

## Workflow

### Step 1: Receive query + optional candidate answer

Two invocation modes:

**Mode A — Query only** (user provides math problem):
```
/skill:cross-check "integrate x^2 sin(x) from 0 to pi"
```

**Mode B — Query + answer to verify** (user has candidate result):
```
/skill:cross-check --three-way "integrate x^2 sin(x) from 0 to pi, I got pi^2 - 4"
```

In Mode B, the candidate answer is included in the prompt so each model can evaluate it.

### Step 2: Build the prompt

Construct a prompt that forces structured output from each model. The prompt must:
1. State the math problem clearly
2. If Mode B, include the candidate answer to evaluate
3. Require the final answer wrapped in `%%ANSWER%%` ... `%%ENDANSWER%%` markers
4. Ask for reasoning before the marker block

Prompt template:

```
Solve this math problem. Show your step-by-step reasoning, then wrap ONLY your final answer between %%ANSWER%% and %%ENDANSWER%% markers. The answer should be a complete mathematical expression in LaTeX, a numeric value, or a clear statement — nothing else between the markers.

Problem: {query}

{If mode B: The user believes the answer is: {candidate}. Verify whether this is correct.}
```

**Critical rule:** Never reveal to any model what another model answered. Each runs independently.

### Step 3: Invoke each model

Use `pi --print` (non-interactive mode) for each model. Pipe output to temp files for diffing.

```bash
# Primary model
pi -p --model opencode-go/qwen3.7-max "Solve this math problem. Show your step-by-step reasoning..." > /tmp/crosscheck-primary.txt

# Alternate model
pi -p --model opencode-go/deepseek-v4-pro "Solve this math problem. Show your step-by-step reasoning..." > /tmp/crosscheck-alt.txt

# Third model (if --three-way)
pi -p --model opencode-go/kimi-k2.6 "Solve this math problem. Show your step-by-step reasoning..." > /tmp/crosscheck-third.txt
```

Use the exact model ID strings as configured in your provider. Common opencode-go models:
- `opencode-go/qwen3.7-max` — best for math
- `opencode-go/deepseek-v4-pro` — strong reasoning
- `opencode-go/kimi-k2.6` — third opinion
- `opencode-go/glm-5.1` — alternative
- `opencode-go/minimax-m3` — lightweight

Wait for all invocations to complete before proceeding.

### Step 4: Extract answers

Parse each output file to extract the content between `%%ANSWER%%` and `%%ENDANSWER%%`. Use this Python snippet:

```python
import re, sys

def extract_answer(text):
    match = re.search(r'%%ANSWER%%\s*(.*?)\s*%%ENDANSWER%%', text, re.DOTALL)
    return match.group(1).strip() if match else None

for path in sys.argv[1:]:
    with open(path) as f:
        text = f.read()
    answer = extract_answer(text)
    if answer:
        print(f"=== {path} ===")
        print(answer)
    else:
        print(f"=== {path} === (NO ANSWER EXTRACTED)")
        # Fall through — the full output is still available for diff
```

### Step 5: Diff the answers

Run two diffs:

#### Diff 1 — Equation-level comparison

```python
import difflib, re, sys, textwrap

def extract_equations(text):
    """Extract LaTeX math blocks ($...$ and $$...$$) from text."""
    display = re.findall(r'\$\$(.+?)\$\$', text, re.DOTALL)
    inline = re.findall(r'\$(.+?)\$', text)
    return display + inline

def normalize_math(eq):
    """Normalize math for comparison: strip spaces, normalize braces."""
    eq = re.sub(r'\s+', ' ', eq).strip()
    return eq

def diff_answers(text_a, text_b, label_a="Model A", label_b="Model B"):
    # Equation-level
    eq_a = extract_equations(text_a)
    eq_b = extract_equations(text_b)
    
    max_eq = max(len(eq_a), len(eq_b))
    eq_diffs = []
    for i in range(max_eq):
        a = normalize_math(eq_a[i]) if i < len(eq_a) else "(missing)"
        b = normalize_math(eq_b[i]) if i < len(eq_b) else "(missing)"
        if a != b:
            eq_diffs.append(f"[Equation {i+1}]")
            eq_diffs.append(f"  {label_a}: {a}")
            eq_diffs.append(f"  {label_b}: {b}")
            eq_diffs.append("")
    
    # Full text-level
    full_diff = difflib.unified_diff(
        text_a.splitlines(keepends=True),
        text_b.splitlines(keepends=True),
        fromfile=label_a,
        tofile=label_b,
    )
    
    return "\n".join(eq_diffs), "".join(full_diff)

if __name__ == "__main__":
    with open(sys.argv[1]) as f: text_a = f.read()
    with open(sys.argv[2]) as f: text_b = f.read()
    eq_diff, full_diff = diff_answers(text_a, text_b)
    print("=== EQUATION-LEVEL DIFF ===")
    print(eq_diff or "(No equation-level differences)")
    print("\n=== FULL RESPONSE DIFF ===")
    print(full_diff or "(No differences)")
```

Save this script to `/tmp/crosscheck-diff.py` and run:

```bash
python3 /tmp/crosscheck-diff.py /tmp/crosscheck-primary.txt /tmp/crosscheck-alt.txt
```

### Step 6: Three-way vote (if enabled)

When `--three-way` is set:

1. Extract answers from all three models
2. Compare pairwise: (primary vs alt), (primary vs third), (alt vs third)
3. **Agreement rule:** Two models agree if their extracted answers normalize to the same expression
4. Present results:

```
VOTE RESULTS:
  qwen3.7-max:     pi^2 - 4           ✓ (agrees with kimi-k2.6)
  deepseek-v4-pro: pi^2 - 4 + 0       ✓ (agrees with kimi-k2.6)  
  kimi-k2.6:       pi^2 - 4           ✓ (agrees with qwen3.7-max)

  CONSENSUS: pi^2 - 4  (3/3 agree)

  --- or ---

  qwen3.7-max:     pi^2 - 4           ✗ (disagrees with deepseek-v4-pro)
  deepseek-v4-pro: pi^3/3 - 4*pi      ✗ (disagrees with qwen3.7-max)
  kimi-k2.6:       pi^2 - 4           ✓ (agrees with qwen3.7-max)

  MAJORITY: pi^2 - 4  (2/3 agree)
  DISAGREEMENT: deepseek-v4-pro says pi^3/3 - 4*pi
```

To check agreement, compare normalized math expressions. Same normalization as equation diff above.

### Step 7: Report

Present to user:
1. **Quick summary**: AGREEMENT / DISAGREEMENT (and vote count if three-way)
2. **Equation-level diff**: where they diverge mathematically
3. **Full response diff**: complete side-by-side for debugging
4. **Confidence note**: "Verified by N independent models" or "Discrepancy found — manual review needed"

If `--save PATH`, write the full report to PATH.

## Cleanup

After reporting, clean temp files unless `--save` was used:

```bash
rm -f /tmp/crosscheck-primary.txt /tmp/crosscheck-alt.txt /tmp/crosscheck-third.txt /tmp/crosscheck-diff.py
```

## Notes

- Model invocations are independent — each runs via separate `pi -p` process
- `pi -p` returns the full agent response including reasoning. The answer markers isolate just the result
- If a model fails to produce answer markers, include its full response in the diff and flag it
- The skill uses `timeout` implicitly via pi's own timeout — no explicit timeout flag needed
- For long queries, consider adding `--thinking xhigh` to each pi invocation for better results
- Model IDs must match exactly what your provider expects. Check with `pi --list-models`

## Example Session

```
User: /skill:cross-check "evaluate ∫₀^π x sin(x) dx"

Agent:
  Running primary model (qwen3.7-max)... done.
  Running alternate model (deepseek-v4-pro)... done.

  AGREEMENT — both models agree.

  EQUATION-LEVEL: No differences.

  Result: ∫₀^π x sin(x) dx = π
  Verified by: qwen3.7-max ✓, deepseek-v4-pro ✓
```

```
User: /skill:cross-check --three-way --alt glm-5.1 "sum of 1/n^2 from n=1 to infinity"

Agent:
  Running qwen3.7-max... done.
  Running glm-5.1... done.
  Running kimi-k2.6... done.

  DISAGREEMENT (2/3 agree)

  EQUATION-LEVEL DIFF:
  [Equation 1]
    qwen3.7-max: \frac{\pi^2}{6}
    glm-5.1: \frac{\pi}{2}

  VOTE: π²/6 wins (qwen3.7-max + kimi-k2.6)
  DISAGREE: glm-5.1 says π/2
```
