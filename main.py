import re
from fastapi import FastAPI, UploadFile, File, HTTPException
import fitz

app = FastAPI()


def extract_text(pdf_bytes: bytes) -> str:
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise RuntimeError("Failed to open PDF") from exc

    parts = []
    for page in doc:
        parts.append(page.get_text())

    return "\n".join(parts)


def split_articles(text: str):
    # patterns: Arabic "مادة", "المادة" and English "Article"
    patterns = [
        r"مادة\s*\(?\s*(\d+)\s*\)?",
        r"المادة\s*\(?\s*(\d+)\s*\)?",
        r"Article\s+(\d+)"
    ]

    matches = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            matches.append({"number": match.group(1), "start": match.start()})

    if not matches:
        return []

    matches.sort(key=lambda x: x["start"])

    articles = []
    for i, m in enumerate(matches):
        start = m["start"]
        end = matches[i + 1]["start"] if i + 1 < len(matches) else len(text)
        article_text = text[start:end].strip()
        articles.append({"article_number": m["number"], "article_text": article_text})

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
        text = extract_text(pdf_bytes)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to extract text from PDF")

    articles = split_articles(text)

    return {"total_articles": len(articles), "articles": articles}
