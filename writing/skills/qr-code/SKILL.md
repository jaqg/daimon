---
name: qr-code
description: >
  Generate a QR code from a URL or text string. Outputs a PNG file and a ready-to-use LaTeX snippet.
  Invoke when the user says /qr-code, "generate a QR code", "make a QR code for [URL/text]",
  or asks to add a QR code to a poster, paper, or slide.
  Not poster-specific — works for any writing context.
tools: Bash, Write
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
| `--output` | `qr` | Output filename without extension (e.g. `--output github` → `github.png`) |
| `--size` | `10` | Module size in pixels (higher = larger image). 10 → ~300px, 20 → ~600px |
| `--format` | `png` | `png` (raster, for inclusion as image) or `svg` (vector) |
| `--error` | `H` | Error correction level: `L` (7%), `M` (15%), `Q` (25%), `H` (30%). Use `H` when adding a logo overlay; `L` for maximum data density |

## Step 1 — Check dependencies

```bash
python3 -c "import qrcode, qrcode.image.svg" 2>/dev/null && echo "ok" || echo "missing"
```

If missing:
```bash
pip install "qrcode[pil]" qrcode
```

If pip is unavailable, fall back to `qrencode` CLI:
```bash
which qrencode && echo "ok" || echo "missing"
```

If neither is available, tell the user to install one:
- `pip install "qrcode[pil]"` (recommended)
- or `sudo pacman -S qrencode` / `sudo apt install qrencode`

## Step 2 — Generate the QR code

**With Python `qrcode` (preferred):**

For PNG:
```python
import qrcode

qr = qrcode.QRCode(
    error_correction=qrcode.constants.ERROR_CORRECT_H,  # adjust per --error flag
    box_size=10,       # adjust per --size flag
    border=4,
)
qr.add_data("%%DATA%%")
qr.make(fit=True)
img = qr.make_image(fill_color="black", back_color="white")
img.save("%%OUTPUT%%.png")
```

Error correction constants:
| Flag | Constant |
|------|----------|
| L | `ERROR_CORRECT_L` |
| M | `ERROR_CORRECT_M` |
| Q | `ERROR_CORRECT_Q` |
| H | `ERROR_CORRECT_H` |

For SVG:
```python
import qrcode
import qrcode.image.svg

factory = qrcode.image.svg.SvgImage
qr = qrcode.QRCode(
    error_correction=qrcode.constants.ERROR_CORRECT_H,
    box_size=10,
    border=4,
    image_factory=factory,
)
qr.add_data("%%DATA%%")
qr.make(fit=True)
img = qr.make_image()
img.save("%%OUTPUT%%.svg")
```

**With `qrencode` CLI (fallback):**
```bash
# PNG
qrencode -o "%%OUTPUT%%.png" -s 10 -l H "%%DATA%%"

# SVG
qrencode -o "%%OUTPUT%%.svg" -s 10 -l H -t SVG "%%DATA%%"
```

Write the generation code as an inline Python script and execute it with `Bash`. Do not write a `.py` file unless the user asks.

## Step 3 — Verify and report

Check the output file was created:
```bash
ls -lh %%OUTPUT%%.png   # or .svg
```

Then report:
- File path and size
- Encoded content (truncated if long)
- Error correction level used

Print the LaTeX snippet for including the QR code:

**As an image (PNG or SVG via `svg` package):**
```latex
\usepackage{graphicx}   % already in poster template

% In the poster body:
\begin{center}
    \includegraphics[width=3cm]{%%OUTPUT%%.png}\\
    \small Scan for [description]
\end{center}
```

**Using the `qrcode` LaTeX package (generates QR inline, no image file needed):**
```latex
\usepackage{qrcode}

% In the poster body:
\begin{center}
    \qrcode[height=3cm]{%%DATA%%}\\
    \small Scan for [description]
\end{center}
```

Note: the `\qrcode{}` LaTeX package approach requires no image file but adds compile-time dependency. The image approach (`\includegraphics`) is more portable and works everywhere.

## Edge cases

- **Long URLs:** QR codes can encode long strings but become denser. For URLs >100 chars, recommend using a URL shortener first (e.g. `https://doi.org/...` is already short).
- **Special characters in data:** wrap in quotes in the bash call; Python handles automatically.
- **SVG in LaTeX:** requires `\usepackage{svg}` and Inkscape installed; PNG is simpler and recommended for posters.
- **High-DPI printing:** for A0 poster printing, use `--size 20` or higher to ensure the QR code is sharp at print resolution.
