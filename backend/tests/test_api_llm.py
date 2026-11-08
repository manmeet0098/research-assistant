from conftest import api_error, auth_error


# ---------- summarize ----------
def test_summarize_returns_and_stores_summary(client, fake_llm, saved_paper):
    fake_llm.reply = "the summary"
    body = client.post(f"/api/library/{saved_paper['id']}/summarize").json()
    assert body == {"summary": "the summary", "cached": False}
    assert client.get(f"/api/library/{saved_paper['id']}").json()["summary"] == "the summary"


def test_summarize_uses_cache_on_second_call(client, fake_llm, saved_paper):
    url = f"/api/library/{saved_paper['id']}/summarize"
    client.post(url)
    calls_after_first = len(fake_llm.calls)
    body = client.post(url).json()
    assert body["cached"] is True
    assert len(fake_llm.calls) == calls_after_first


def test_summarize_refresh_regenerates(client, fake_llm, saved_paper):
    url = f"/api/library/{saved_paper['id']}/summarize"
    fake_llm.reply = "old"
    client.post(url)
    fake_llm.reply = "new"
    body = client.post(url, params={"refresh": "true"}).json()
    assert body == {"summary": "new", "cached": False}


def test_summarize_reports_502_on_rejected_key(client, fake_llm, saved_paper):
    fake_llm.error = auth_error()
    response = client.post(f"/api/library/{saved_paper['id']}/summarize")
    assert response.status_code == 502
    assert "API key" in response.json()["detail"]


def test_summarize_reports_502_on_other_llm_errors(client, fake_llm, saved_paper):
    fake_llm.error = api_error()
    response = client.post(f"/api/library/{saved_paper['id']}/summarize")
    assert response.status_code == 502
    assert "LLM request failed" in response.json()["detail"]


# ---------- ask ----------
def test_ask_returns_answer(client, fake_llm, saved_paper):
    fake_llm.reply = "42"
    response = client.post(f"/api/library/{saved_paper['id']}/ask", json={"question": "Meaning?"})
    assert response.json() == {"answer": "42"}


def test_ask_passes_history_and_question_to_the_llm(client, fake_llm, saved_paper):
    history = [{"role": "user", "content": "q1"}, {"role": "assistant", "content": "a1"}]
    client.post(f"/api/library/{saved_paper['id']}/ask", json={"question": "q2", "history": history})
    assert [m["content"] for m in fake_llm.calls[-1]["messages"]] == ["q1", "a1", "q2"]


def test_ask_rejects_blank_question(client, saved_paper):
    response = client.post(f"/api/library/{saved_paper['id']}/ask", json={"question": "   "})
    assert response.status_code == 400


def test_ask_reports_502_on_llm_failure(client, fake_llm, saved_paper):
    fake_llm.error = api_error()
    response = client.post(f"/api/library/{saved_paper['id']}/ask", json={"question": "q"})
    assert response.status_code == 502


# ---------- streaming ----------
def test_stream_summary_sends_text_and_saves_it(client, fake_llm, saved_paper):
    fake_llm.chunks = ["Problem. ", "Approach."]
    response = client.post(f"/api/library/{saved_paper['id']}/summarize/stream")
    assert response.status_code == 200
    assert response.text == "Problem. Approach."
    assert client.get(f"/api/library/{saved_paper['id']}").json()["summary"] == "Problem. Approach."


def test_stream_summary_uses_cache(client, fake_llm, saved_paper):
    url = f"/api/library/{saved_paper['id']}/summarize/stream"
    fake_llm.chunks = ["cached text"]
    client.post(url)
    calls = len(fake_llm.calls)
    assert client.post(url).text == "cached text"
    assert len(fake_llm.calls) == calls


def test_stream_summary_refresh_regenerates(client, fake_llm, saved_paper):
    url = f"/api/library/{saved_paper['id']}/summarize/stream"
    fake_llm.chunks = ["old"]
    client.post(url)
    fake_llm.chunks = ["new"]
    assert client.post(url, params={"refresh": "true"}).text == "new"


def test_stream_ask_sends_answer(client, fake_llm, saved_paper):
    fake_llm.chunks = ["part one ", "part two"]
    response = client.post(f"/api/library/{saved_paper['id']}/ask/stream", json={"question": "q"})
    assert response.text == "part one part two"


def test_stream_ask_rejects_blank_question(client, saved_paper):
    response = client.post(f"/api/library/{saved_paper['id']}/ask/stream", json={"question": ""})
    assert response.status_code == 400


def test_stream_errors_before_first_chunk_become_http_errors(client, fake_llm, saved_paper):
    fake_llm.error = auth_error()
    response = client.post(f"/api/library/{saved_paper['id']}/summarize/stream")
    assert response.status_code == 502


def test_stream_interrupted_midway_is_flagged_and_not_saved(client, fake_llm, saved_paper):
    fake_llm.chunks = ["first ", "second ", "third"]
    fake_llm.error_after = 1
    response = client.post(f"/api/library/{saved_paper['id']}/summarize/stream")
    assert response.status_code == 200
    assert "Stream interrupted" in response.text
    assert client.get(f"/api/library/{saved_paper['id']}").json()["summary"] is None
