import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  askPaper,
  deletePaper,
  listLibrary,
  savePaper,
  searchPapers,
  streamAnswer,
  streamSummary,
  summarizePaper,
  uploadPdf,
} from './api'

const jsonResponse = (body, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const streamResponse = (chunks, status = 200) =>
  new Response(
    new ReadableStream({
      start(controller) {
        const enc = new TextEncoder()
        chunks.forEach((c) => controller.enqueue(enc.encode(c)))
        controller.close()
      },
    }),
    { status },
  )

afterEach(() => vi.unstubAllGlobals())

function mockFetch(response) {
  const fn = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', fn)
  return fn
}

describe('request helpers', () => {
  it('searchPapers URL-encodes the query', async () => {
    const fetch = mockFetch(jsonResponse({ provider: 'semantic_scholar', results: [] }))
    await searchPapers('a b&c')
    expect(fetch.mock.calls[0][0]).toBe('/api/search?q=a%20b%26c&limit=10')
  })

  it('listLibrary returns parsed JSON', async () => {
    mockFetch(jsonResponse([{ id: 1 }]))
    expect(await listLibrary()).toEqual([{ id: 1 }])
  })

  it('savePaper POSTs the paper as JSON', async () => {
    const fetch = mockFetch(jsonResponse({ id: 1 }))
    await savePaper({ title: 'T' })
    const [url, options] = fetch.mock.calls[0]
    expect(url).toBe('/api/library')
    expect(options.method).toBe('POST')
    expect(JSON.parse(options.body)).toEqual({ title: 'T' })
  })

  it('deletePaper sends DELETE', async () => {
    const fetch = mockFetch(jsonResponse({ deleted: 3 }))
    await deletePaper(3)
    expect(fetch.mock.calls[0]).toEqual(['/api/library/3', { method: 'DELETE' }])
  })

  it('summarizePaper passes the refresh flag', async () => {
    const fetch = mockFetch(jsonResponse({ summary: 's' }))
    await summarizePaper(2, true)
    expect(fetch.mock.calls[0][0]).toBe('/api/library/2/summarize?refresh=true')
  })

  it('askPaper POSTs the question and history', async () => {
    const fetch = mockFetch(jsonResponse({ answer: 'a' }))
    await askPaper(5, 'why', [])
    const [url, options] = fetch.mock.calls[0]
    expect(url).toBe('/api/library/5/ask')
    expect(JSON.parse(options.body)).toEqual({ question: 'why', history: [] })
  })

  it('uploadPdf sends the file as multipart form data', async () => {
    const fetch = mockFetch(jsonResponse({ id: 1 }))
    const file = new File(['%PDF'], 'p.pdf', { type: 'application/pdf' })
    await uploadPdf(file)
    const body = fetch.mock.calls[0][1].body
    expect(body).toBeInstanceOf(FormData)
    expect(body.get('file').name).toBe('p.pdf')
  })

  it('throws the server detail message on an error response', async () => {
    mockFetch(jsonResponse({ detail: 'Query is empty' }, 400))
    await expect(searchPapers('x')).rejects.toThrow('Query is empty')
  })

  it('falls back to a generic message when the error has no JSON body', async () => {
    mockFetch(new Response('boom', { status: 500 }))
    await expect(listLibrary()).rejects.toThrow('Request failed (500)')
  })
})

describe('streaming helpers', () => {
  it('streamSummary reports the growing text and returns the full text', async () => {
    mockFetch(streamResponse(['Hel', 'lo ', 'world']))
    const seen = []
    const text = await streamSummary(1, false, (t) => seen.push(t))
    expect(text).toBe('Hello world')
    expect(seen).toContain('Hel')
    expect(seen.at(-1)).toBe('Hello world')
  })

  it('streamAnswer POSTs the question and history', async () => {
    const fetch = mockFetch(streamResponse(['ok']))
    await streamAnswer(4, 'why?', [{ role: 'user', content: 'hi' }], () => {})
    const [url, options] = fetch.mock.calls[0]
    expect(url).toBe('/api/library/4/ask/stream')
    expect(JSON.parse(options.body)).toEqual({
      question: 'why?',
      history: [{ role: 'user', content: 'hi' }],
    })
  })

  it('throws the server detail when the stream request is rejected', async () => {
    mockFetch(jsonResponse({ detail: 'LLM request failed' }, 502))
    await expect(streamSummary(1, false, () => {})).rejects.toThrow('LLM request failed')
  })
})
