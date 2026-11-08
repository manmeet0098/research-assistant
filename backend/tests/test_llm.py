import llm

FULL = {"title": "T", "abstract": "ABSTRACT TEXT", "full_text": "FULL BODY TEXT"}
ABSTRACT_ONLY = {"title": "T", "abstract": "ABSTRACT TEXT", "full_text": None}


def test_extract_metadata_parses_json(fake_llm):
    fake_llm.reply = '{"title": " My Title ", "authors": ["A", "B"], "year": 2021, "abstract": "abs"}'
    assert llm.extract_metadata("page") == {
        "title": "My Title",
        "authors": ["A", "B"],
        "year": 2021,
        "abstract": "abs",
    }


def test_extract_metadata_tolerates_text_around_json(fake_llm):
    fake_llm.reply = 'Here you go:\n```json\n{"title": "X", "authors": [], "year": null, "abstract": ""}\n```'
    assert llm.extract_metadata("page")["title"] == "X"


def test_extract_metadata_defaults_for_missing_fields(fake_llm):
    fake_llm.reply = "{}"
    assert llm.extract_metadata("page") == {"title": "", "authors": [], "year": None, "abstract": ""}


def test_extract_metadata_rejects_non_integer_year(fake_llm):
    fake_llm.reply = '{"title": "X", "year": "2021"}'
    assert llm.extract_metadata("page")["year"] is None


def test_summarize_uses_full_text(fake_llm):
    fake_llm.reply = "a summary"
    assert llm.summarize(FULL) == "a summary"
    sent = fake_llm.calls[-1]
    assert "FULL BODY TEXT" in sent["messages"][0]["content"]
    assert "abstract alone" not in sent["system"]


def test_summarize_abstract_only_notes_limitation(fake_llm):
    llm.summarize(ABSTRACT_ONLY)
    sent = fake_llm.calls[-1]
    assert "ABSTRACT TEXT" in sent["messages"][0]["content"]
    assert "abstract alone" in sent["system"]


def test_response_cut_off_is_flagged_and_keeps_the_text(fake_llm):
    fake_llm.reply = "partial summary"
    fake_llm.stop_reason = "max_tokens"
    result = llm.summarize(FULL)
    assert result.startswith("partial summary")
    assert result.endswith(llm.CUT_OFF_NOTE)


def test_complete_response_has_no_cut_off_note(fake_llm):
    fake_llm.reply = "complete"
    assert llm.summarize(FULL) == "complete"


def test_answer_includes_history_and_question(fake_llm):
    history = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "system", "content": "ignored"},
        {"role": "user", "content": ""},
    ]
    llm.answer(FULL, "q2", history)
    messages = fake_llm.calls[-1]["messages"]
    assert [m["content"] for m in messages] == ["q1", "a1", "q2"]


def test_answer_puts_paper_in_system_prompt(fake_llm):
    llm.answer(FULL, "q")
    assert "FULL BODY TEXT" in fake_llm.calls[-1]["system"]


def test_paper_text_is_truncated_to_the_limit(fake_llm):
    llm.summarize({"title": "T", "full_text": "x" * (llm.MAX_PAPER_CHARS + 5000)})
    content = fake_llm.calls[-1]["messages"][0]["content"]
    assert content.count("x") == llm.MAX_PAPER_CHARS


def test_client_is_created_once_and_reused(monkeypatch):
    created = []

    class StubAnthropic:
        def __init__(self):
            created.append(self)

    monkeypatch.setattr(llm.anthropic, "Anthropic", StubAnthropic)
    monkeypatch.setattr(llm, "_client", None)
    assert llm.client() is llm.client()
    assert len(created) == 1


def test_stream_summary_yields_chunks(fake_llm):
    fake_llm.chunks = ["one ", "two ", "three"]
    assert "".join(llm.stream_summary(FULL)) == "one two three"


def test_stream_flags_cut_off(fake_llm):
    fake_llm.chunks = ["partial"]
    fake_llm.stop_reason = "max_tokens"
    assert "cut off" in "".join(llm.stream_answer(FULL, "q"))
