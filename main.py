import re
import unicodedata
from fastapi import FastAPI, UploadFile, File, HTTPException
import fitz  # PyMuPDF

app = FastAPI()


# -----------------------------
# 1. TEXT EXTRACTION (IMPROVED)
# -----------------------------
def extract_text(pdf_bytes: bytes) -> str:
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise RuntimeError("Failed to open PDF") from exc

    parts = []

    for page in doc:
        text = page.get_text("text")  # more stable than default
        parts.append(text)

    return "\n".join(parts)


# -----------------------------
# 2. NORMALIZATION (CRITICAL FIX)
# -----------------------------
def normalize_text(text: str) -> str:
    # Normalize unicode (fix Arabic presentation forms)
    text = unicodedata.normalize("NFKC", text)

    # Remove weird invisible chars
    text = re.sub(r"[\u200f\u200e\u202a-\u202e]", "", text)

    # Convert Arabic-Indic digits → English digits
    arabic_digits = "٠١٢٣٤٥٦٧٨٩"
    for i, d in enumerate(arabic_digits):
        text = text.replace(d, str(i))

    return text


# -----------------------------
# 3. ARTICLE SPLITTER (ROBUST)
# -----------------------------
def split_articles(text: str):
    text = normalize_text(text)

    # More flexible patterns (real-world PDFs are messy)
    patterns = [
        r"(?:^|\n)\s*المادة\s*[\(\[]?\s*(\d+)\s*[\)\]]?",
        r"(?:^|\n)\s*مادة\s*[\(\[]?\s*(\d+)\s*[\)\]]?",
        r"(?:^|\n)\s*Article\s*[:\-]?\s*(\d+)",
    ]

    matches = []

    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            matches.append({
                "number": match.group(1),
                "start": match.start()
            })

    # If regex fails → fallback strategy (VERY IMPORTANT for Arabic PDFs)
    if not matches:
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if "المادة" in line or "مادة" in line or "Article" in line:
                nums = re.findall(r"\d+", line)
                if nums:
                    matches.append({
                        "number": nums[0],
                        "start": i
                    })

        if not matches:
            return []

        # line-based reconstruction
        articles = []
        for i, m in enumerate(matches):
            start = m["start"]
            end = matches[i + 1]["start"] if i + 1 < len(matches) else len(lines)

            article_text = "\n".join(lines[start:end]).strip()

            articles.append({
                "article_number": m["number"],
                "article_text": article_text
            })

        return articles

    # Sort by position (regex case)
    matches.sort(key=lambda x: x["start"])

    articles = []

    for i, m in enumerate(matches):
        start = m["start"]
        end = matches[i + 1]["start"] if i + 1 < len(matches) else len(text)

        article_text = text[start:end].strip()

        articles.append({
            "article_number": m["number"],
            "article_text": article_text
        })

    return articles


# -----------------------------
# 4. API
# -----------------------------
@app.get("/")
async def root():
    return {"status": "running"}


@app.post("/parse-pdf")
async def parse_pdf(file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Uploaded file must be a PDF")

    pdf_bytes = await file.read()

    try:
        text = extract_text(pdf_bytes)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to extract text from PDF")

    # DEBUG (optional but useful)
    print("---- SAMPLE TEXT ----")
    print(text[:1000])

    articles = split_articles(text)

    return {
        "total_articles": len(articles),
        "articles": articles
    }
