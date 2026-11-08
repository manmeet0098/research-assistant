import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from './api'
import App from './App'

vi.mock('./api')

const saved = {
  id: 1,
  external_id: 's2:1',
  title: 'Saved Paper',
  authors: ['Ann'],
  year: 2020,
  abstract: 'abs',
  source: 'search',
  has_full_text: true,
  summary: null,
}
const result = {
  external_id: 's2:2',
  title: 'Search Result',
  authors: ['Bob'],
  year: 2021,
  abstract: 'abs',
  url: 'https://example.org',
}

beforeEach(() => {
  vi.resetAllMocks()
  api.listLibrary.mockResolvedValue([])
})

describe('App', () => {
  it('shows the library size in the tab', async () => {
    api.listLibrary.mockResolvedValue([saved])
    render(<App />)
    expect(await screen.findByRole('button', { name: 'Library (1)' })).toBeInTheDocument()
  })

  it('searches and lists results', async () => {
    api.searchPapers.mockResolvedValue({ provider: 'semantic_scholar', results: [result] })
    render(<App />)
    await userEvent.type(screen.getByPlaceholderText(/search papers/i), 'widgets{Enter}')
    expect(await screen.findByText('Search Result')).toBeInTheDocument()
    expect(api.searchPapers).toHaveBeenCalledWith('widgets')
    expect(screen.getByText(/from Semantic Scholar/)).toBeInTheDocument()
  })

  it('says so when search falls back to arXiv', async () => {
    api.searchPapers.mockResolvedValue({ provider: 'arxiv', results: [result] })
    render(<App />)
    await userEvent.type(screen.getByPlaceholderText(/search papers/i), 'x{Enter}')
    expect(await screen.findByText(/arXiv \(Semantic Scholar was unavailable\)/)).toBeInTheDocument()
  })

  it('shows an empty-results message', async () => {
    api.searchPapers.mockResolvedValue({ provider: 'semantic_scholar', results: [] })
    render(<App />)
    await userEvent.type(screen.getByPlaceholderText(/search papers/i), 'zzz{Enter}')
    expect(await screen.findByText(/No papers found/)).toBeInTheDocument()
  })

  it('shows search errors', async () => {
    api.searchPapers.mockRejectedValue(new Error('Paper search is temporarily unavailable'))
    render(<App />)
    await userEvent.type(screen.getByPlaceholderText(/search papers/i), 'x{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent('temporarily unavailable')
  })

  it('saves a result and marks it saved', async () => {
    api.searchPapers.mockResolvedValue({ provider: 'semantic_scholar', results: [result] })
    api.savePaper.mockResolvedValue({ ...saved, external_id: 's2:2' })
    render(<App />)
    await userEvent.type(screen.getByPlaceholderText(/search papers/i), 'x{Enter}')
    api.listLibrary.mockResolvedValue([{ ...saved, external_id: 's2:2' }])
    await userEvent.click(await screen.findByRole('button', { name: 'Save to library' }))
    expect(await screen.findByText('✓ Saved')).toBeInTheDocument()
    expect(api.savePaper).toHaveBeenCalledWith(result)
  })

  it('lists saved papers in the library tab', async () => {
    api.listLibrary.mockResolvedValue([saved])
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Library (1)' }))
    expect(screen.getByText('Saved Paper')).toBeInTheDocument()
  })

  it('shows an empty-library hint', async () => {
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Library (0)' }))
    expect(screen.getByText(/library is empty/i)).toBeInTheDocument()
  })

  it('opens the detail panel for a library paper', async () => {
    api.listLibrary.mockResolvedValue([saved])
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Library (1)' }))
    await userEvent.click(screen.getByRole('button', { name: 'Summarize / Ask' }))
    expect(await screen.findByRole('button', { name: 'Generate summary' })).toBeInTheDocument()
  })

  it('removes a paper after confirmation', async () => {
    api.listLibrary.mockResolvedValue([saved])
    api.deletePaper.mockResolvedValue({ deleted: 1 })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Library (1)' }))
    api.listLibrary.mockResolvedValue([])
    await userEvent.click(screen.getByRole('button', { name: 'Remove' }))
    await waitFor(() => expect(api.deletePaper).toHaveBeenCalledWith(1))
  })

  it('uploads a PDF and selects the new paper', async () => {
    const uploaded = { ...saved, id: 9, title: 'Uploaded Paper', source: 'upload', external_id: null }
    api.uploadPdf.mockResolvedValue(uploaded)
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Library (0)' }))
    api.listLibrary.mockResolvedValue([uploaded])
    const input = document.querySelector('input[type=file]')
    await userEvent.upload(input, new File(['%PDF'], 'p.pdf', { type: 'application/pdf' }))
    await waitFor(() => expect(api.uploadPdf).toHaveBeenCalledOnce())
    expect((await screen.findAllByText('Uploaded Paper')).length).toBeGreaterThan(0)
  })

  it('switches back to the Search tab from the Library', async () => {
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Library (0)' }))
    expect(screen.queryByPlaceholderText(/search papers/i)).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Search', exact: true }))
    expect(screen.getByPlaceholderText(/search papers/i)).toBeInTheDocument()
  })

  it('the Upload PDF button opens the file chooser', async () => {
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Library (0)' }))
    const input = document.querySelector('input[type=file]')
    const open = vi.spyOn(input, 'click')
    await userEvent.click(screen.getByRole('button', { name: 'Upload PDF' }))
    expect(open).toHaveBeenCalledOnce()
    expect(input).toHaveAttribute('accept', 'application/pdf')
  })

  it('opens the detail panel when a paper title is clicked, and closes it again', async () => {
    api.listLibrary.mockResolvedValue([saved])
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Library (1)' }))
    await userEvent.click(screen.getByRole('heading', { name: 'Saved Paper' }))
    expect(await screen.findByRole('button', { name: 'Generate summary' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /close/i }))
    expect(screen.queryByRole('button', { name: 'Generate summary' })).not.toBeInTheDocument()
  })

  it('shows an upload error and keeps the library unchanged', async () => {
    api.uploadPdf.mockRejectedValue(new Error('That file is not a PDF'))
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Library (0)' }))
    const input = document.querySelector('input[type=file]')
    await userEvent.upload(input, new File(['hi'], 'x.pdf', { type: 'application/pdf' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('not a PDF')
    expect(screen.getByRole('button', { name: 'Library (0)' })).toBeInTheDocument()
  })

  it('does not remove a paper when the confirmation is declined', async () => {
    api.listLibrary.mockResolvedValue([saved])
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Library (1)' }))
    await userEvent.click(screen.getByRole('button', { name: 'Remove' }))
    expect(api.deletePaper).not.toHaveBeenCalled()
  })

  // BUG-6: PaperDetail starts from the stale library copy, so a summary generated earlier is not shown again.
  it.fails('shows a generated summary again after closing and reopening the paper', async () => {
    // A stand-in for the backend: it remembers the summary once one is generated.
    const library = [{ ...saved }]
    api.listLibrary.mockImplementation(async () => library.map((p) => ({ ...p })))
    api.streamSummary.mockImplementation(async (id, refresh, onText) => {
      library[0].summary = 'Generated summary'
      onText('Generated summary')
      return 'Generated summary'
    })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Library (1)' }))
    await userEvent.click(screen.getByRole('heading', { name: 'Saved Paper' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Generate summary' }))
    expect(await screen.findByText('Generated summary')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /close/i }))
    await userEvent.click(screen.getByRole('heading', { name: 'Saved Paper' }))
    expect(await screen.findByText('Generated summary')).toBeInTheDocument()
  })

  it('shows an error and lets the user retry when saving fails', async () => {
    api.searchPapers.mockResolvedValue({ provider: 'semantic_scholar', results: [result] })
    api.savePaper.mockRejectedValue(new Error('Request failed (500)'))
    render(<App />)
    await userEvent.type(screen.getByPlaceholderText(/search papers/i), 'x{Enter}')
    await userEvent.click(await screen.findByRole('button', { name: 'Save to library' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Request failed (500)')
    expect(screen.getByRole('button', { name: 'Save to library' })).toBeEnabled()
  })
})
