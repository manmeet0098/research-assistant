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
    await userEvent.type(screen.getByPlaceholderText(/search papers/i), 'widgets')
    await userEvent.click(screen.getByRole('button', { name: 'Search', hidden: false, exact: true, description: '' }).closest('form').querySelector('button'))
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
})
