import { useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { askPaper, summarizePaper } from '../api'

export default function PaperDetail({ paper, onClose }) {
  const [summary, setSummary] = useState(paper.summary)
  const [summarizing, setSummarizing] = useState(false)
  const [messages, setMessages] = useState([])
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState('')
  const endRef = useRef(null)

  useEffect(() => {
    if (messages.length > 0) endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, asking])

  async function runSummary(refresh = false) {
    setSummarizing(true)
    setError('')
    try {
      setSummary((await summarizePaper(paper.id, refresh)).summary)
    } catch (e) {
      setError(e.message)
    } finally {
      setSummarizing(false)
    }
  }

  async function ask(q) {
    if (!q.trim() || asking) return
    const history = messages
    setMessages([...history, { role: 'user', content: q }])
    setQuestion('')
    setAsking(true)
    setError('')
    try {
      const { answer } = await askPaper(paper.id, q, history)
      setMessages((m) => [...m, { role: 'assistant', content: answer }])
    } catch (e) {
      setError(e.message)
    } finally {
      setAsking(false)
    }
  }

  const suggestions = [
    'What problem does this paper address?',
    'What is the main idea of the proposed approach?',
    'What datasets are used?',
    'What are the major limitations?',
    'How does this method compare with the baselines?',
  ]

  return (
    <section className="detail">
      <div className="row between">
        <h2>{paper.title}</h2>
        <button className="link" onClick={onClose}>✕ Close</button>
      </div>
      {!paper.has_full_text && (
        <p className="notice">Full text isn't available for this paper, so answers use the abstract only.</p>
      )}

      <h4>Summary</h4>
      {summary ? (
        <div className="markdown"><Markdown remarkPlugins={[remarkGfm]}>{summary}</Markdown></div>
      ) : (
        <p className="muted">No summary yet.</p>
      )}
      <button onClick={() => runSummary(Boolean(summary))} disabled={summarizing}>
        {summarizing ? 'Summarizing…' : summary ? 'Regenerate summary' : 'Generate summary'}
      </button>

      <h4>Ask a question</h4>
      <div className="chat">
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.role === 'assistant' ? <Markdown remarkPlugins={[remarkGfm]}>{m.content}</Markdown> : m.content}
          </div>
        ))}
        {asking && <div className="msg assistant muted">Thinking…</div>}
        <div ref={endRef} />
      </div>
      {messages.length === 0 && (
        <div className="chips">
          {suggestions.map((s) => (
            <button key={s} className="chip" onClick={() => ask(s)}>{s}</button>
          ))}
        </div>
      )}
      <form onSubmit={(e) => { e.preventDefault(); ask(question) }} className="row">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask anything about this paper…"
        />
        <button disabled={asking || !question.trim()}>Ask</button>
      </form>
      {error && <p className="error">{error}</p>}
    </section>
  )
}
