"""Claude calls: metadata extraction, summarization, and Q&A."""
import json
import os
import re

import anthropic

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
MAX_PAPER_CHARS = 150_000  # ~40k tokens; fits comfortably in context

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    return _client


def _ask(system: str, messages: list[dict], max_tokens: int = 1500) -> str:
    resp = client().messages.create(
        model=MODEL, max_tokens=max_tokens, system=system, messages=messages
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if resp.stop_reason == "max_tokens":
        # Never present a cut-off answer as if it were complete.
        text += "\n\n*(Response was cut off at the length limit.)*"
    return text


def extract_metadata(first_page: str) -> dict:
    """Ask Claude to pull title/authors/year/abstract from the first page of a paper."""
    system = (
        "You extract bibliographic metadata from the first page of a research paper. "
        "Reply with ONLY a JSON object with keys: title (string), authors (list of strings), "
        "year (integer or null), abstract (string). Copy the abstract verbatim. "
        "Use null / empty values if something is not present; never invent data."
    )
    raw = _ask(system, [{"role": "user", "content": first_page}], max_tokens=1500)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    data = json.loads(match.group(0)) if match else {}
    year = data.get("year")
    return {
        "title": (data.get("title") or "").strip(),
        "authors": [a for a in data.get("authors") or [] if isinstance(a, str)],
        "year": year if isinstance(year, int) else None,
        "abstract": (data.get("abstract") or "").strip(),
    }


def _paper_block(paper: dict) -> tuple[str, bool]:
    """Build the paper context. Returns (text, is_full_text)."""
    if paper.get("full_text"):
        return paper["full_text"][:MAX_PAPER_CHARS], True
    return f"Title: {paper['title']}\nAbstract: {paper.get('abstract') or '(none)'}", False


def summarize(paper: dict) -> str:
    body, full = _paper_block(paper)
    system = (
        "You are a research assistant. Write a summary of the paper for a graduate student "
        "who wants to decide quickly whether to read it. Hard limits: 250-350 words total, "
        "no title heading, no restating the paper's section structure. Use exactly these four "
        "Markdown sections, in this order, each starting with a bold label on its own line:\n"
        "**Problem** - 2-3 sentences.\n"
        "**Approach** - 3-4 sentences on the core idea, not every component.\n"
        "**Key Results** - at most 3 bullets, each with the most important number or finding.\n"
        "**Limitations** - 2-3 sentences, including any the authors acknowledge.\n"
        "Prefer prose to nested bullets. Leave out details a reader can get from the paper "
        "itself. Base everything on the provided text and finish all four sections."
    )
    if not full:
        system += (
            " Only the title and abstract are available, so start by noting that this summary "
            "is based on the abstract alone."
        )
    return _ask(
        system, [{"role": "user", "content": f"<paper>\n{body}\n</paper>"}], max_tokens=2000
    )


def answer(paper: dict, question: str, history: list[dict] | None = None) -> str:
    body, full = _paper_block(paper)
    system = (
        "You answer questions about a single research paper, provided below in <paper> tags. "
        "Answer only from the paper. If the paper does not contain the answer, say so plainly "
        "instead of guessing. Be concise and cite specifics (sections, numbers, dataset names) "
        "when the paper gives them."
    )
    if not full:
        system += " Only the title and abstract are available; mention this if it limits the answer."
    system += f"\n\n<paper>\n{body}\n</paper>"
    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in (history or [])
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    messages.append({"role": "user", "content": question})
    return _ask(system, messages)
