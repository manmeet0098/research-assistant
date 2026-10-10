import { useEffect, useRef, useState } from 'react'
import { deletePaper, listLibrary, savePaper, searchPapers, uploadPdf } from './api'
import PaperCard from './components/PaperCard'
import PaperDetail from './components/PaperDetail'
import './App.css'

export default function App() {
  const [tab, setTab] = useState('search')
  const [library, setLibrary] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [provider, setProvider] = useState('')
  const [busy, setBusy] = useState('') // '', 'search', 'upload', or 'save:<external_id>'
  const [error, setError] = useState('')
  const fileRef = useRef(null)

  const refreshLibrary = async () => setLibrary(await listLibrary())
  useEffect(() => { refreshLibrary().catch((e) => setError(e.message)) }, [])

  const savedIds = new Set(library.map((p) => p.external_id).filter(Boolean))
  const selected = library.find((p) => p.id === selectedId)

  async function run(label, fn) {
    setBusy(label)
    setError('')
    try {
      return await fn()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  const onSearch = (e) => {
    e.preventDefault()
    if (!query.trim()) return
    run('search', async () => {
      const data = await searchPapers(query)
      setResults(data.results)
      setProvider(data.provider)
    })
  }

  const onSave = (paper) =>
    run(`save:${paper.external_id}`, async () => {
      await savePaper(paper)
      await refreshLibrary()
    })

  const onUpload = (e) => {
    const file = e.target.files[0]
    e.target.value = ''
    if (!file) return
    run('upload', async () => {
      const paper = await uploadPdf(file)
      await refreshLibrary()
      setSelectedId(paper.id)
    })
  }

  const onDelete = (paper) =>
    run('delete', async () => {
      if (!window.confirm(`Remove "${paper.title}" from your library?`)) return
      await deletePaper(paper.id)
      if (selectedId === paper.id) setSelectedId(null)
      await refreshLibrary()
    })

  return (
    <div className="app">
      <header>
        <h1>AI Research Assistant</h1>
        <nav>
          <button className={tab === 'search' ? 'tab active' : 'tab'} onClick={() => setTab('search')}>
            Search
          </button>
          <button className={tab === 'library' ? 'tab active' : 'tab'} onClick={() => setTab('library')}>
            Library ({library.length})
          </button>
        </nav>
      </header>

      {error && <p className="error" role="alert">{error}</p>}

      {tab === 'search' && (
        <main>
          <form onSubmit={onSearch} className="row">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search papers by keyword or topic…"
              autoFocus
            />
            <button disabled={busy === 'search' || !query.trim()}>
              {busy === 'search' ? 'Searching…' : 'Search'}
            </button>
          </form>
          {results && (
            <p className="muted">
              {results.length} results from {provider === 'arxiv' ? 'arXiv (Semantic Scholar was unavailable)' : 'Semantic Scholar'}
            </p>
          )}
          {results?.map((paper) => (
            <PaperCard
              key={paper.external_id}
              paper={paper}
              actions={
                savedIds.has(paper.external_id) ? (
                  <span className="saved">✓ Saved</span>
                ) : (
                  <button onClick={() => onSave(paper)} disabled={busy === `save:${paper.external_id}`}>
                    {busy === `save:${paper.external_id}` ? 'Saving…' : 'Save to library'}
                  </button>
                )
              }
            />
          ))}
          {results?.length === 0 && <p className="muted">No papers found. Try different keywords.</p>}
        </main>
      )}

      {tab === 'library' && (
        <main className={selected ? 'split' : ''}>
          <div>
            <div className="row between">
              <p className="muted">Click a paper to summarize it or ask questions.</p>
              <>
                <input ref={fileRef} type="file" accept="application/pdf" hidden onChange={onUpload} />
                <button onClick={() => fileRef.current.click()} disabled={busy === 'upload'}>
                  {busy === 'upload' ? 'Processing PDF…' : 'Upload PDF'}
                </button>
              </>
            </div>
            {library.length === 0 && (
              <p className="muted">Your library is empty. Save papers from search or upload a PDF.</p>
            )}
            {library.map((paper) => (
              <PaperCard
                key={paper.id}
                paper={paper}
                selected={paper.id === selectedId}
                onClick={() => setSelectedId(paper.id)}
                actions={
                  <>
                    <button onClick={() => setSelectedId(paper.id)}>Summarize / Ask</button>
                    <button className="danger" onClick={() => onDelete(paper)}>Remove</button>
                  </>
                }
              />
            ))}
          </div>
          {selected && <PaperDetail key={selected.id} paper={selected} onClose={() => setSelectedId(null)} />}
        </main>
      )}
    </div>
  )
}
