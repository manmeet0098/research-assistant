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
