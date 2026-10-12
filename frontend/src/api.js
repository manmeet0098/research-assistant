async function request(path, options) {
  const res = await fetch(`/api${path}`, options)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`)
  return data
}

const json = (body) => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const searchPapers = (q) => request(`/search?q=${encodeURIComponent(q)}&limit=10`)
export const listLibrary = () => request('/library')
export const savePaper = (paper) => request('/library', json(paper))
export const deletePaper = (id) => request(`/library/${id}`, { method: 'DELETE' })
export const summarizePaper = (id, refresh = false) =>
  request(`/library/${id}/summarize?refresh=${refresh}`, { method: 'POST' })
export const askPaper = (id, question, history) =>
  request(`/library/${id}/ask`, json({ question, history }))

export function uploadPdf(file) {
  const form = new FormData()
  form.append('file', file)
  return request('/upload', { method: 'POST', body: form })
}

// Read a streamed plain-text response, calling onText(fullTextSoFar) as it grows.
async function streamText(path, options, onText) {
  const res = await fetch(`/api${path}`, options)
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || `Request failed (${res.status})`)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let text = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    text += decoder.decode(value, { stream: true })
    onText(text)
  }
  text += decoder.decode()
  onText(text)
  return text
}

export const streamSummary = (id, refresh, onText) =>
  streamText(`/library/${id}/summarize/stream?refresh=${refresh}`, { method: 'POST' }, onText)
export const streamAnswer = (id, question, history, onText) =>
  streamText(`/library/${id}/ask/stream`, json({ question, history }), onText)
