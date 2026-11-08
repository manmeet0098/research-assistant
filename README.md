# AI Research Assistant

A small web app for finding, organizing, and understanding research papers. Search for papers, save them to a local library, upload your own PDFs, and use Claude to summarize a paper or answer questions about it.

Built for CS 592 Homework 1 using a coding agent (Claude Code).

## Features

- **Search papers** by keyword or topic via the Semantic Scholar API (title, authors, year, abstract, link). If Semantic Scholar is rate-limited, search falls back to arXiv automatically.
- **Save to a local library** (SQLite). Saved papers persist across page refreshes and restarts. When a paper has an open-access PDF, its full text is downloaded and stored.
- **Upload PDFs.** The text is extracted with PyMuPDF, then Claude reads the first page to pull out the title, authors, year, and abstract.
- **Summarize** any library paper with Claude (Problem / Approach / Key Results / Limitations). Summaries use the paper's full text and are cached.
- **Ask questions** about a paper in a chat panel. Answers are grounded in the paper's text, and the model says so when the paper doesn't contain the answer.
- Papers without a retrievable PDF are marked **abstract only**, and summaries and answers for them use just the title and abstract.

## Architecture

```
React (Vite) frontend  ──/api proxy──▶  FastAPI backend  ──▶  SQLite (library.db)
                                              │
                                              ├──▶ Semantic Scholar / arXiv  (paper search)
                                              └──▶ Anthropic Claude API      (metadata, summaries, Q&A)
```

```
backend/
  main.py       FastAPI app and all HTTP endpoints
  search.py     Semantic Scholar search with arXiv fallback
  pdf.py        PDF download and text extraction (PyMuPDF)
  llm.py        Claude calls: metadata extraction, summarize, ask
  db.py         SQLite schema and helpers
frontend/src/
  App.jsx                    Search and Library tabs, upload
  components/PaperCard.jsx   Paper display (title, authors, year, abstract, link)
  components/PaperDetail.jsx Summary and Q&A panel
  api.js                     Backend client
```

The full paper text (up to about 150k characters) is passed to Claude with each request. There is no embedding or vector search, because a typical paper fits comfortably in the model's context window.

## Setup

Requirements: Python 3.10+ and Node.js 18+.

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # then edit .env and add your keys
uvicorn main:app --port 8000
```

`.env` settings:

| Variable | Required | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | yes | From console.anthropic.com |
| `SEMANTIC_SCHOLAR_API_KEY` | no | Free key from semanticscholar.org/product/api. Without it, the shared rate limit often triggers the arXiv fallback. |
| `CLAUDE_MODEL` | no | Defaults to `claude-sonnet-5-5` |

`.env` is git-ignored. Never commit it.

### 2. Frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The dev server proxies `/api` to the backend on port 8000.

If `npm run dev` fails with `Cannot find native binding` (a known npm bug with optional dependencies), install the binary for your platform, for example `npm install --no-save @rolldown/binding-darwin-arm64`, or delete `node_modules` and `package-lock.json` and run `npm install` again.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/search?q=...` | Search papers |
| GET | `/api/library` | List saved papers |
| POST | `/api/library` | Save a paper from search results |
| DELETE | `/api/library/{id}` | Remove a paper |
| POST | `/api/upload` | Upload a PDF (multipart `file`) |
| POST | `/api/library/{id}/summarize` | Generate or fetch the cached summary |
| POST | `/api/library/{id}/ask` | Ask a question (`{question, history}`) |
| POST | `/api/library/{id}/summarize/stream` | Same as `summarize`, streamed as plain text |
| POST | `/api/library/{id}/ask/stream` | Same as `ask`, streamed as plain text |

FastAPI also serves interactive docs at http://localhost:8000/docs.

## Known limitations

- Scanned (image-only) PDFs are not supported, since there is no OCR.
- Some search results have no open-access PDF, so they stay abstract-only.
- Semantic Scholar's API key allows 1 request/second, so searches are spaced out; if it still fails, search falls back to arXiv.
- Single-user, local-only app with no authentication.

## Testing

The tests never call real services: Semantic Scholar, arXiv and Claude are mocked, and every test uses its
own temporary SQLite database. They need no API keys and cost nothing to run.

### Backend (pytest)

```bash
cd backend
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest                                   # run the tests
python -m pytest --cov --cov-branch --cov-report=term-missing   # with line + branch coverage
```

Mutation testing (injects small bugs into the code and checks the tests notice; takes about a minute):

```bash
mutmut run          # then: mutmut results   |   mutmut show <name>
```

### Frontend (Vitest + Testing Library)

```bash
cd frontend
npm install
npm test                 # run the tests
npm run test:coverage    # with coverage
```

### Where the tests are

| Path | What it covers |
|---|---|
| `backend/tests/test_db.py`, `test_pdf.py`, `test_search.py`, `test_llm.py` | Unit tests for each backend module |
| `backend/tests/test_api_*.py` | The HTTP API end to end (search, library, upload, summaries, questions, streaming) |
| `backend/tests/test_requirements.py` | Acceptance tests derived from the HW1 requirements |
| `backend/tests/test_surviving_mutants.py` | Tests added for faults the mutation run found undetected |
| `backend/tests/test_robustness.py` | Regression tests for six bugs the suite found |
| `frontend/src/**/*.test.{js,jsx}` | API client, `PaperCard`, `PaperDetail`, and the `App` flows |

The suite was built in stages; each stage is tagged in git so the progression can be reproduced:
`hw2-round0` (initial), `hw2-round1`, `hw2-round2` (still shows the six bugs as expected failures), `hw2-bugfixes`.

