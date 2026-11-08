import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import PaperCard from './PaperCard'

const paper = {
  title: 'Sparse Widget Routing',
  authors: ['Ann', 'Bob'],
  year: 2024,
  abstract: 'A short abstract.',
  url: 'https://example.org/p',
  source: 'search',
}

describe('PaperCard', () => {
  it('shows title, authors, year, abstract and a link', () => {
    render(<PaperCard paper={paper} />)
    expect(screen.getByText('Sparse Widget Routing')).toBeInTheDocument()
    expect(screen.getByText(/Ann, Bob/)).toBeInTheDocument()
    expect(screen.getByText(/2024/)).toBeInTheDocument()
    expect(screen.getByText('A short abstract.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /open paper/i })).toHaveAttribute('href', paper.url)
  })

  it('omits the link when the paper has no url', () => {
    render(<PaperCard paper={{ ...paper, url: null }} />)
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('falls back when abstract and authors are missing', () => {
    render(<PaperCard paper={{ ...paper, abstract: null, authors: [] }} />)
    expect(screen.getByText('No abstract available.')).toBeInTheDocument()
    expect(screen.getByText(/Unknown authors/)).toBeInTheDocument()
  })

  it('shortens long author lists with et al.', () => {
    const authors = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
    render(<PaperCard paper={{ ...paper, authors }} />)
    expect(screen.getByText(/et al\./)).toBeInTheDocument()
  })

  it('truncates a long abstract and expands on demand', async () => {
    const abstract = 'word '.repeat(200)
    render(<PaperCard paper={{ ...paper, abstract }} />)
    await userEvent.click(screen.getByRole('button', { name: 'more' }))
    expect(screen.getByRole('button', { name: 'less' })).toBeInTheDocument()
  })

  it('flags papers without full text', () => {
    render(<PaperCard paper={{ ...paper, has_full_text: false }} />)
    expect(screen.getByText('abstract only')).toBeInTheDocument()
  })

  it('calls onClick when the title is clicked', async () => {
    const onClick = vi.fn()
    render(<PaperCard paper={paper} onClick={onClick} />)
    await userEvent.click(screen.getByText('Sparse Widget Routing'))
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('renders provided action buttons', () => {
    render(<PaperCard paper={paper} actions={<button>Save</button>} />)
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument()
  })
})
