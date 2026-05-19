---
name: qr-code
description: >
  Generate a QR code from a URL or text string. Outputs a PNG file and a ready-to-use LaTeX snippet.
  Invoke when the user says /qr-code, "generate a QR code", "make a QR code for [URL/text]",
  or asks to add a QR code to a poster, paper, or slide.
  Not poster-specific — works for any writing context.
tools: Bash
---

# qr-code

Generate a QR code image from a URL or text, with a LaTeX include snippet.

## Invocation

```
/qr-code <url-or-text> [--output NAME] [--size N] [--format png|svg] [--error L|M|Q|H]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `<url-or-text>` | required | URL or any text to encode |
| `--output` | `qr` | Output filename without extension |
| `--size` | `10` | Module size in pixels (10 → ~300px, 20 → ~600px for A0 print) |
| `--format` | `png` | `png` (recommended for LaTeX) or `svg` (vector; requires Inkscape in LaTeX) |
| `--error` | `H` | Error correction: `L` (7%) / `M` (15%) / `Q` (25%) / `H` (30%). Use `H` with logo overlay, `L` for dense data |

## Step 1 — Run the generation script

```bash
SCRIPT=$(find -L ~/.claude -path "*/qr-code/scripts/generate_qr.py" -type f | head -1)
python3 "$SCRIPT" --data "<url-or-text>" --output <name> --size <N> --format <fmt> --error <level>
```

The script handles dependency detection (Python `qrcode` preferred, `qrencode` CLI fallback),
generates the file, and prints the LaTeX snippets. If the script reports a missing backend,
tell the user to run `pip install 'qrcode[pil]'`.

## Step 2 — Report output

Display the script's output verbatim. No additional explanation needed unless the user asks.
