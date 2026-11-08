"""Claude calls: metadata extraction, summarization, and Q&A."""
import json
import os
import re
from collections.abc import Iterator

import anthropic

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
MAX_PAPER_CHARS = 150_000  # ~40k tokens; fits comfortably in context
CUT_OFF_NOTE = "\n\n*(Response was cut off at the length limit.)*"

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
        text += CUT_OFF_NOTE
    return text


def _stream(system: str, messages: list[dict], max_tokens: int = 1500) -> Iterator[str]:
    """Yield the response text as it is generated."""
    with client().messages.stream(
        model=MODEL, max_tokens=max_tokens, system=system, messages=messages
    ) as stream:
        yield from stream.text_stream
        if stream.get_final_message().stop_reason == "max_tokens":
            yield CUT_OFF_NOTE


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
    try:
        data = json.loads(match.group(0)) if match else {}
    except ValueError:  # the model produced something that only looks like JSON
        data = {}
    year = data.get("year")
    return {
        "title": _text(data.get("title")),
        "authors": _authors(data.get("authors")),
        "year": year if isinstance(year, int) and not isinstance(year, bool) else None,
        "abstract": _text(data.get("abstract")),
    }


def _text(value) -> str:
    """Metadata is best-effort: anything that is not a string counts as missing."""
    return value.strip() if isinstance(value, str) else ""


def _authors(value) -> list[str]:
    if isinstance(value, str):  # a single name must not be split into letters
        value = [value]
    if not isinstance(value, list):
        return []
    return [a.strip() for a in value if isinstance(a, str) and a.strip()]


def _paper_block(paper: dict) -> tuple[str, bool]:
    """Build the paper context. Returns (text, is_full_text)."""
    if paper.get("full_text"):
        return paper["full_text"][:MAX_PAPER_CHARS], True
    return f"Title: {paper['title']}\nAbstract: {paper.get('abstract') or '(none)'}", False


def _summary_request(paper: dict) -> tuple[str, list[dict], int]:
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
    messages = [{"role": "user", "content": f"<paper>\n{body}\n</paper>"}]
    return system, messages, 2000


def _answer_request(
    paper: dict, question: str, history: list[dict] | None
) -> tuple[str, list[dict], int]:
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
    return system, messages, 1500


def summarize(paper: dict) -> str:
    return _ask(*_summary_request(paper))


def answer(paper: dict, question: str, history: list[dict] | None = None) -> str:
    return _ask(*_answer_request(paper, question, history))


def stream_summary(paper: dict) -> Iterator[str]:
    return _stream(*_summary_request(paper))


def stream_answer(paper: dict, question: str, history: list[dict] | None = None) -> Iterator[str]:
    return _stream(*_answer_request(paper, question, history))
