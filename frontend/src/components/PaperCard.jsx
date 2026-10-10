import { useState } from 'react'

export default function PaperCard({ paper, actions, onClick, selected }) {
  const [expanded, setExpanded] = useState(false)
  const abstract = paper.abstract || 'No abstract available.'
  const long = abstract.length > 350

  return (
    <article className={`card${selected ? ' selected' : ''}${onClick ? ' clickable' : ''}`}>
      <h3 onClick={onClick}>{paper.title}</h3>
      <p className="meta">
        {paper.authors?.length ? paper.authors.slice(0, 6).join(', ') : 'Unknown authors'}
        {paper.authors?.length > 6 && ' et al.'}
        {paper.year ? ` · ${paper.year}` : ''}
        {paper.source && <span className={`badge ${paper.source}`}>{paper.source}</span>}
        {paper.has_full_text === false && <span className="badge warn">abstract only</span>}
      </p>
      <p className="abstract">
        {expanded || !long ? abstract : `${abstract.slice(0, 350)}…`}
        {long && (
          <button className="link" onClick={() => setExpanded(!expanded)}>
            {expanded ? 'less' : 'more'}
          </button>
        )}
      </p>
      <div className="row">
        {paper.url && (
          <a href={paper.url} target="_blank" rel="noreferrer">
            Open paper ↗
          </a>
        )}
        {actions}
      </div>
    </article>
  )
}
