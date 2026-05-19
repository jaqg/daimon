#!/usr/bin/env python3
"""Generate a QR code image. Prints LaTeX snippet to stdout on success."""

import argparse
import os
import subprocess
import sys

ERROR_MAP = {"L": "ERROR_CORRECT_L", "M": "ERROR_CORRECT_M", "Q": "ERROR_CORRECT_Q", "H": "ERROR_CORRECT_H"}


def _qrcode_python(data, output, size, fmt, error_key):
    import qrcode
    import qrcode.constants as qcc

    ec = getattr(qcc, ERROR_MAP[error_key])
    qr = qrcode.QRCode(error_correction=ec, box_size=size, border=4)
    qr.add_data(data)
    qr.make(fit=True)

    if fmt == "svg":
        import qrcode.image.svg
        img = qr.make_image(image_factory=qrcode.image.svg.SvgImage)
    else:
        img = qr.make_image(fill_color="black", back_color="white")

    path = f"{output}.{fmt}"
    img.save(path)
    return path


def _qrencode_cli(data, output, size, fmt, error_key):
    path = f"{output}.{fmt}"
    cmd = ["qrencode", "-o", path, "-s", str(size), "-l", error_key]
    if fmt == "svg":
        cmd += ["-t", "SVG"]
    cmd.append(data)
    subprocess.run(cmd, check=True)
    return path


def check_backend():
    try:
        import qrcode  # noqa: F401
        return "python"
    except ImportError:
        pass
    if subprocess.run(["which", "qrencode"], capture_output=True).returncode == 0:
        return "cli"
    return None


def latex_snippet(path, data, fmt):
    if fmt == "svg":
        pkg = "\\usepackage{svg}"
        inc = f"\\includesvg[width=3cm]{{{path}}}"
    else:
        pkg = "\\usepackage{graphicx}  % usually already loaded"
        inc = f"\\includegraphics[width=3cm]{{{path}}}"

    latex_pkg = f"\\usepackage{{qrcode}}"
    latex_inline = f"\\qrcode[height=3cm]{{{data}}}"

    return f"""\
LaTeX (image file — portable):
  {pkg}
  \\begin{{center}}
      {inc}\\\\
      \\small Scan for [description]
  \\end{{center}}

LaTeX (inline qrcode package — no image file needed):
  {latex_pkg}
  \\begin{{center}}
      {latex_inline}\\\\
      \\small Scan for [description]
  \\end{{center}}"""


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", required=True, help="URL or text to encode")
    p.add_argument("--output", default="qr", help="Output filename without extension")
    p.add_argument("--size", type=int, default=10, help="Module size in pixels")
    p.add_argument("--format", choices=["png", "svg"], default="png", dest="fmt")
    p.add_argument("--error", choices=["L", "M", "Q", "H"], default="H")
    args = p.parse_args()

    backend = check_backend()
    if backend is None:
        print("ERROR: No QR backend found. Install one:", file=sys.stderr)
        print("  pip install 'qrcode[pil]'", file=sys.stderr)
        print("  sudo pacman -S qrencode  (or apt install qrencode)", file=sys.stderr)
        sys.exit(1)

    try:
        if backend == "python":
            path = _qrcode_python(args.data, args.output, args.size, args.fmt, args.error)
        else:
            path = _qrencode_cli(args.data, args.output, args.size, args.fmt, args.error)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    size_bytes = os.path.getsize(path)
    size_str = f"{size_bytes / 1024:.1f} KB" if size_bytes >= 1024 else f"{size_bytes} B"
    encoded_display = args.data if len(args.data) <= 60 else args.data[:57] + "..."

    print(f"Generated: {path} ({size_str})")
    print(f"Encoded:   {encoded_display}")
    print(f"Error correction: {args.error}  Backend: {backend}")
    print()
    print(latex_snippet(path, args.data, args.fmt))


if __name__ == "__main__":
    main()
