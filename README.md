# FastAPI PDF Article Splitter

This repository contains a small FastAPI app that extracts text from uploaded PDFs (using PyMuPDF / fitz) and splits the text into articles by matching patterns like "مادة (1)", "المادة (1)", or "Article 1".

## Files
- `main.py` — the FastAPI app.
- `requirements.txt` — Python dependencies.
- `Procfile` — process command for platforms that use Procfile (Railway honors this).
- `Dockerfile` — container image for Docker-based deployment.
- `.gitignore`

## Deploy to Railway (quick)
1. Push this repo to GitHub (already done).
2. Create a new project on Railway and connect your GitHub repo.
3. Railway will detect this is a Python app. Ensure the start command is:
   `uvicorn main:app --host 0.0.0.0 --port $PORT`
   (The included `Procfile` already sets that.)
4. Deploy. Railway sets the `PORT` env var automatically.

Alternatively, pick Docker deployment and Railway will build the provided `Dockerfile`.

## Test locally
1. Create and activate a virtualenv:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Run locally:
   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

3. Example curl to test (replace `file.pdf` with your PDF):
   ```bash
   curl -F "file=@file.pdf" http://localhost:8000/parse-pdf
   ```

## Notes & improvements
- The article splitting uses simple regex patterns and works for numeric article headings. If PDFs use different formatting (non-standard parentheses, non-numeric labels, or images-only pages) you may need OCR or improved heuristics.
- For production you may want to:
  - Add request size limits or streaming processing if PDFs can be very large.
  - Add logging, metrics, and better error handling.
  - Pin dependency versions for reproducible builds.
