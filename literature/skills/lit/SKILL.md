---
name: lit
description: >
  Literature pipeline orchestrator. Parses natural language intent and routes to the
  right lit-* skills in the correct order. Use for any literature request:
  "/lit", "find papers on X", "lit review on X", "import papers to vault",
  "full pipeline for X", "watch for new papers on X", "annotate this paper",
  "chase citations of X", "bib file for X", "extract literature for X".
  Eliminates needing to choose or manually sequence lit-* skills.
  Also triggers for: "literature for my project", "set up lit monitoring",
  "I finished reading [paper]", "generate bibliography for X", "what cites [paper]".
tools: Bash, Read, Write
---

# lit

Natural-language entry point for the daimon literature pipeline. Parses user intent,
asks only the questions needed to fill in important missing parameters, shows an
execution plan, gets approval, then invokes sub-skills in order.

## Intent taxonomy

| Intent | Trigger phrases | Sub-skills invoked |
|--------|----------------|--------------------|
| `search` | "find papers", "search for papers", "papers on X", "discover papers" | `lit-search` |
| `chase` | "chase citations", "what cites X", "references of X", "citation graph" | `lit-search` (--chase) |
| `vault_import` | "import to vault", "add to vault", "extract literature for X", "save papers to vault" | `lit-search` → `lit-vault` |
| `review` | "review literature", "lit review on X", "analyze papers", "systematic review" | `lit-review` |
| `full` | "full pipeline", "everything for X", "complete workflow", "review + vault" | `lit-review` → `lit-vault` |
| `bib` | "generate bib", "bibliography for X", ".bib file", "BibTeX" | `lit-search` → `lit-bib` |
| `watch` | "watch papers on X", "monitor literature", "weekly update", "track new papers" | `lit-watch` |
| `annotate` | "annotate this paper", "read and annotate", "fill in notes for", "I finished reading" | `lit-annotate` |

Ambiguous intent: lean toward the more comprehensive option (e.g., `vault_import` over `search`).
If `review` is detected, ask whether the user also wants vault notes (→ `full`).

## Step 0: Parse what's clear

Extract from user message:
- **intent**: one of the 8 intents above
- **topic**: what to search for
- **paper**: DOI / arXiv ID / URL / local path (for chase/annotate)
- **papers_path**: existing papers.json path if user mentions one
- **project**: project ID if mentioned
- **scope**: results count, domain, date range if stated

Map domain from topic language:
- "DFT", "QM", "QTAIM", "IQA", "computational chemistry", "zeolite" → `comp-chem`
- "ML", "neural network", "deep learning", "machine learning" → `ml`
- "biology", "enzyme", "protein", "biochemistry" → `bio`
- "physics", "condensed matter", "quantum physics" → `physics`
- otherwise → `general`

## Step 0b: Mini-intake

Ask only for what's actually needed and not already provided. Bundle all questions for
the intent into ONE message — do not ask one question at a time.

### Per-intent questions

**search:**
- (optional) "Associate with a project? (for memory/context, or skip)"
- Mention defaults: "Will search for 20 papers, sorted by impact. Adjust?"

**chase:**
- If direction not stated: "Forward citations, backward references, or both? (default: both)"

**vault_import:**
- If project not stated: "Which project should these notes be linked to? (or skip for no project)"
- "Full-text fetch or abstract-only? Full-text = slower but better notes; abstract-only = fast."
- If full-text chosen: "Save downloaded PDFs anywhere? (provide path, or skip to discard after import)"
- If papers_path not provided: "Do you already have a papers.json from a previous search? (provide path, or skip to run a new search)"

**review:**
- "What should be included / excluded? (e.g. 'include only papers using DFT, exclude review articles') — or skip for default PRISMA scoring"
- "Also want vault notes after the review? (yes → full pipeline)"
- If project not stated: "Project context? (improves screening relevance)"
- "NotebookLM analysis included? (yes = full review with NLM; no = screening + .bib only)"

**full:**
- "Screening criteria? (include/exclude rules — or skip for default)"
- If project not stated: "Project? (required for vault notes to be project-linked)"
- "Full-text fetch for vault notes? (slower but better notes)"
- If full-text: "Save PDFs? (provide path or skip)"

**bib:**
- "Update an existing .bib file or create new? (if update, provide path)"
- "Output path for the .bib? (default: refs.bib in current directory)"
- If papers_path not provided: "Do you have an existing papers.json? (or run new search)"

**watch:**
- If neither project nor topics stated: "Monitor by project (reads project memory) or by explicit topics? Which project / what topics?"
- If project not stated and intent is watch: project OR topics is required — must ask.

**annotate:**
- If note not identified: "Which paper note? (filename, author+year prefix, or fuzzy name)"
- "Source material: paste your reading notes, provide a PDF path, a URL, or re-fetch? (or skip to annotate from abstract only)"

### Intake rules
- If a parameter is already clear from the message, do NOT ask for it again.
- Keep questions brief and offer clear options with defaults marked.
- For optional questions (project on search, PDF storage), make it easy to skip.
- After intake, proceed immediately to Step 1 — no further questions before showing the plan.

## Step 1: Show plan and get approval

Display:

```
Plan: [paraphrased intent in one line]

  Step N: [skill-name] — [what it will do]
           Flags: [key flags, including scope defaults so user sees what's happening]
  Step N+1: [skill-name] — [what it will do]
           Flags: [key flags]

Tip: [one optional enhancement, e.g. "Add --expand 3 to also search related topics" or
     "Add --adaptive to lit-review for deeper gap analysis"]

Proceed? Enter y to run, or describe what to change.
```

Always show defaults explicitly in flags (e.g. `--results 20 --sort impact`).
The "Tip" line is optional — only include when a flag would meaningfully improve results.

Wait for explicit confirmation (y / yes / ok / go) or change request.
If user requests changes: update the plan and show again. Do not run until confirmed.

## Step 2: Execute

Invoke sub-skills in order using the Skill tool. Pass file paths between steps.

### Per-intent invocation

**search:**
```
lit-search: --topic TOPIC --results N --sort impact [--domain D] [date flags]
            [--min-citations N if stated] [--expand N if stated]
```

**chase:**
```
lit-search: --chase PAPER --mode MODE --results N
```
MODE defaults to `both` unless user specified forward/backward.

**vault_import:**
```
lit-search: --topic TOPIC --results N --sort impact [--domain D] [date flags]
            (skip if papers_path provided)
lit-vault:  --papers PATH [--project PROJECT] [--no-full-text if chosen]
            [--output-dir if non-default] [--overwrite if re-importing]
```

**review:**
```
lit-review: --topic TOPIC --results N [--domain D] [--project PROJECT]
            [--criteria "TEXT"] [--no-notebooklm if chosen] [--expand N if stated]
            [--adaptive if stated]
```
lit-review runs its own search internally — do NOT run lit-search separately.

**full:**
```
lit-review: --topic TOPIC --results N [--domain D] [--project PROJECT]
            [--criteria "TEXT"] [--expand N if stated]
lit-vault:  --papers <screened papers output from lit-review>
            [--project PROJECT] [--no-full-text if chosen]
```

**bib:**
```
lit-search: --topic TOPIC --results N [--domain D]
            (skip if papers_path provided; also accepts --dois / --arxiv lists)
lit-bib:    --papers PATH [--output OUT.bib | --update EXISTING.bib]
            [--style phys] [--zotero | --no-zotero]
```

**watch:**
```
lit-watch:  [--project PROJECT | --topics "X, Y"] [--threshold 4]
            [--since DATE if override needed]
```

**annotate:**
```
lit-annotate: --note NOTE_IDENTIFIER [--text "..." | --pdf PATH | --url URL]
              [--project PROJECT if set]
```

### papers_path shortcut

If user supplies an existing papers.json, skip the lit-search step and pass that path
directly to the downstream skill (lit-vault, lit-bib, etc.).

## Step 3: Report

After all sub-skills complete:

```
Done.
  [skill-name]: [one-line result]
  [skill-name]: [one-line result]

[context-appropriate next-step suggestions]
```

## Error handling

| Problem | Action |
|---------|--------|
| review vs full boundary unclear | Ask "Also want vault notes?" before plan |
| Sub-skill fails | Report; offer retry with adjusted flags or skip to next step |
| No papers found | Suggest broader topic, `--months 60`, `--sources all` |
| papers.json path not found | Ask for correct path before proceeding |
| watch: neither project nor topics | Required — ask before plan |
| annotate: note not found (fuzzy match fails) | List closest matches; ask user to pick |
| Full-text fetch very slow (>3 min) | Warn user; offer to continue or switch to `--no-full-text` |
