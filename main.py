"""
Arabic legal-PDF parser (FastAPI).

WHY THIS IS NOT YOUR ORIGINAL PyMuPDF VERSION
---------------------------------------------
The target PDFs are produced by doPDF, which writes a *bidi-damaged* text
layer. Empirically, on Law No. 14/2025 (Egyptian Labor Law, 298 articles):

  * PyMuPDF get_text() -> readable Arabic prose, but multi-digit article
    numbers come out reordered (14 -> 41, 104 -> 401). Unusable for citation.
  * pdftotext -raw     -> article numbers and ordering are CORRECT (1..298),
    which is what we need for article_number. (Prose word-order is imperfect,
    see the note at the bottom.)

This parser therefore extracts with `pdftotext -raw` (poppler) and adds the
three fixes the original was missing:
  1. Normalize Arabic-Indic AND Farsi/Extended digits to ASCII (the file uses
     both; the original only handled U+0660-0669).
  2. Match the article marker with the number's parentheses in EITHER
     orientation -- the body prints them mirrored, e.g. `مادة)1(`.
  3. Drop cross-references ("...as stated in article (41)...") with a
     sequentiality filter, since a real statute is numbered 1, 2, 3, ...

REQUIREMENT: poppler-utils must be installed in the runtime image.
  Debian/Ubuntu (Railway):  apt-get install -y poppler-utils
  Or add a Dockerfile/nixpacks step that installs it.
"""

import re
import shutil
import subprocess
import tempfile
import unicodedata

from fastapi import FastAPI, UploadFile, File, HTTPException

app = FastAPI()

# --- digit maps: Arabic-Indic (٠-٩) and Extended/Farsi (۰-۹) -> ASCII ---
_DIGIT_MAP = {}
for _i, _d in enumerate("٠١٢٣٤٥٦٧٨٩"):
    _DIGIT_MAP[ord(_d)] = str(_i)
for _i, _d in enumerate("۰۱۲۳۴۵۶۷۸۹"):
    _DIGIT_MAP[ord(_d)] = str(_i)

# line-anchored article heading: optional "ال", the marker (مادة / المادة / ماده),
# then any spaces / parens (either orientation) / brackets / tatweel / colon,
# then the (already ASCII-normalized) number.
_HEADING_RE = re.compile(
    r"(?:^|\n)[ \t]*"
    r"(?:ال)?ماد[ةه]"
    r"[\s()\[\]ـ:.]*?"
    r"(\d{1,4})",
    re.MULTILINE,
)

# how big a forward jump in numbering we tolerate before treating a match as a
# cross-reference rather than the next article (covers a few missed headings).
_MAX_FORWARD_GAP = 3


def extract_text_raw(pdf_bytes: bytes) -> str:
    """Extract text with `pdftotext -raw` (correct number order for doPDF output)."""
    if not shutil.which("pdftotext"):
        raise RuntimeError(
            "pdftotext not found. Install poppler-utils in the runtime image "
            "(apt-get install -y poppler-utils)."
        )
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(pdf_bytes)
        tmp.flush()
        proc = subprocess.run(
            ["pdftotext", "-raw", tmp.name, "-"],
            capture_output=True,
        )
    if proc.returncode != 0:
        raise RuntimeError(
            "pdftotext failed: " + proc.stderr.decode("utf-8", "replace")[:300]
        )
    return proc.stdout.decode("utf-8", "replace")


def normalize_text(text: str) -> str:
    # NFKC folds Arabic presentation forms (U+FE70-FEFF, U+FB50-FDFF) back to
    # base letters, which is what makes the marker matchable at all.
    text = unicodedata.normalize("NFKC", text)
    # strip bidi control characters
    text = re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]", "", text)
    # Arabic-Indic + Farsi digits -> ASCII
    text = text.translate(_DIGIT_MAP)
    return text


def split_articles(text: str):
    text = normalize_text(text)

    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return []

    # Sequentiality filter: walk matches in document order and keep only those
    # that advance the article sequence. This rejects cross-references (which
    # point backward or far forward) and stray in-text numbers.
    kept = []
    expected = 1
    for m in matches:
        num = int(m.group(1))
        if num == expected or (expected < num <= expected + _MAX_FORWARD_GAP):
            kept.append((num, m.start()))
            expected = num + 1

    articles = []
    for i, (num, start) in enumerate(kept):
        end = kept[i + 1][1] if i + 1 < len(kept) else len(text)
        body = re.sub(r"\s+", " ", text[start:end]).strip()
        if len(body) < 30:
            continue
        articles.append(
            {
                "article_number": str(num),
                "article_text": body,
            }
        )
    return articles


@app.get("/")
async def root():
    return {"status": "running"}


@app.post("/parse-pdf")
async def parse_pdf(file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Uploaded file must be a PDF")

    pdf_bytes = await file.read()
    try:
        text = extract_text_raw(pdf_bytes)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    articles = split_articles(text)
    return {
        "total_articles": len(articles),
        "articles": articles,
    }


# ----------------------------------------------------------------------------
# READABILITY CAVEAT (important for your RAG quality)
# ----------------------------------------------------------------------------
# `pdftotext -raw` gives correct *numbers*, but because this PDF stores Arabic
# in visual order, the *prose* word-order inside article_text is imperfect
# (words occasionally appear out of sequence or split across line breaks). All
# the words are present, so keyword/embedding overlap still works, but it is
# not clean reading order.
#
# For production-grade Arabic text from these doPDF files, the robust fix is a
# bidi-aware OCR service rather than the text layer:
#   * Google Document AI or Azure AI "Read" handle Arabic RTL + digits far more
#     reliably than Tesseract (local Tesseract here misread the heading word
#     and digits).
#   * Or obtain cleaner source PDFs (the official gazette / a legal database)
#     instead of a doPDF print, which is the worst-case input.
# Happy to wire either of those in.
