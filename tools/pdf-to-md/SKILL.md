# PDF to Markdown (Pi vision)

Convert scientific/math PDFs to markdown with LaTeX equations using pi's built-in PDF reader and vision model.

## When to use
User provides a PDF file path and asks to convert it to markdown, or wants to analyze a math paper.

## Steps

1. Use pi's tools to read the PDF file. Approach depends on what's available:
   - **Vision model**: Ask the user's model to read the PDF via `read` tool (pi renders PDF pages as images for Gemini/Claude)
   - **Bash + pdftotext**: `!pdftotext <pdf_path> -` for fallback text extraction
   - **Marker** (if available): `!marker <pdf_path> --output_dir /tmp/pdf2md_<basename>`

2. Present the markdown content to the user with equations preserved as LaTeX.

## Notes
- Best results with Gemini or Claude models (handle vision well)
- DeepSeek models don't support images — use bash-based extraction instead
- For pure math papers, vision model approach gives accurate LaTeX equations
