import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import PaperDetail from './PaperDetail'

vi.mock('../api')

const paper = { id: 1, title: 'Widgets', has_full_text: true, summary: null }

beforeEach(() => vi.resetAllMocks())

describe('PaperDetail summary', () => {
  it('shows an existing summary', () => {
    render(<PaperDetail paper={{ ...paper, summary: 'Existing summary' }} onClose={() => {}} />)
    expect(screen.getByText('Existing summary')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Regenerate summary' })).toBeInTheDocument()
  })

  it('offers to generate a summary when there is none', () => {
    render(<PaperDetail paper={paper} onClose={() => {}} />)
    expect(screen.getByText('No summary yet.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Generate summary' })).toBeInTheDocument()
  })

  it('streams the summary into the panel', async () => {
    api.streamSummary.mockImplementation(async (id, refresh, onText) => {
      onText('Problem: widgets')
      return 'Problem: widgets'
    })
    render(<PaperDetail paper={paper} onClose={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: 'Generate summary' }))
    expect(await screen.findByText('Problem: widgets')).toBeInTheDocument()
    expect(api.streamSummary).toHaveBeenCalledWith(1, false, expect.any(Function))
  })

  it('keeps the previous summary and shows the error if regeneration fails', async () => {
    api.streamSummary.mockRejectedValue(new Error('LLM request failed'))
    render(<PaperDetail paper={{ ...paper, summary: 'Old summary' }} onClose={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: 'Regenerate summary' }))
    expect(await screen.findByText('LLM request failed')).toBeInTheDocument()
    expect(screen.getByText('Old summary')).toBeInTheDocument()
  })

  it('warns when only the abstract is available', () => {
    render(<PaperDetail paper={{ ...paper, has_full_text: false }} onClose={() => {}} />)
    expect(screen.getByText(/Full text isn't available/)).toBeInTheDocument()
  })
})

describe('PaperDetail questions', () => {
  it('asks a typed question and shows the streamed answer', async () => {
    api.streamAnswer.mockImplementation(async (id, q, history, onText) => {
      onText('Because of widgets.')
    })
    render(<PaperDetail paper={paper} onClose={() => {}} />)
    await userEvent.type(screen.getByPlaceholderText(/ask anything/i), 'Why?')
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByText('Because of widgets.')).toBeInTheDocument()
    expect(screen.getByText('Why?')).toBeInTheDocument()
    expect(api.streamAnswer).toHaveBeenCalledWith(1, 'Why?', [], expect.any(Function))
  })

  it('disables Ask until a question is typed', () => {
    render(<PaperDetail paper={paper} onClose={() => {}} />)
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled()
  })

  it('asks a suggested question when its chip is clicked', async () => {
    api.streamAnswer.mockImplementation(async (id, q, history, onText) => onText('An answer'))
    render(<PaperDetail paper={paper} onClose={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: 'What datasets are used?' }))
    await waitFor(() =>
      expect(api.streamAnswer).toHaveBeenCalledWith(1, 'What datasets are used?', [], expect.any(Function)),
    )
  })

  it('shows an error and removes the empty bubble when asking fails', async () => {
    api.streamAnswer.mockRejectedValue(new Error('Anthropic API key was rejected'))
    render(<PaperDetail paper={paper} onClose={() => {}} />)
    await userEvent.type(screen.getByPlaceholderText(/ask anything/i), 'Hi')
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByText('Anthropic API key was rejected')).toBeInTheDocument()
    expect(screen.queryByText('Thinking…')).not.toBeInTheDocument()
  })

  it('calls onClose', async () => {
    const onClose = vi.fn()
    render(<PaperDetail paper={paper} onClose={onClose} />)
    await userEvent.click(screen.getByRole('button', { name: /close/i }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})

describe('PaperDetail edge cases', () => {
  it('sends earlier turns as history on a follow-up question', async () => {
    api.streamAnswer.mockImplementation(async (id, q, history, onText) => onText(`answer to ${q}`))
    render(<PaperDetail paper={paper} onClose={() => {}} />)
    const box = screen.getByPlaceholderText(/ask anything/i)
    await userEvent.type(box, 'first{Enter}')
    await screen.findByText('answer to first')
    await userEvent.type(box, 'second{Enter}')
    await screen.findByText('answer to second')
    expect(api.streamAnswer).toHaveBeenLastCalledWith(
      1,
      'second',
      [
        { role: 'user', content: 'first' },
        { role: 'assistant', content: 'answer to first' },
      ],
      expect.any(Function),
    )
  })

  it('ignores a second question while one is still being answered', async () => {
    api.streamAnswer.mockImplementation(() => new Promise(() => {}))
    render(<PaperDetail paper={paper} onClose={() => {}} />)
    const box = screen.getByPlaceholderText(/ask anything/i)
    await userEvent.type(box, 'one{Enter}')
    await userEvent.type(box, 'two{Enter}')
    expect(api.streamAnswer).toHaveBeenCalledTimes(1)
  })

  it('does not submit a blank question', async () => {
    render(<PaperDetail paper={paper} onClose={() => {}} />)
    await userEvent.type(screen.getByPlaceholderText(/ask anything/i), '   {Enter}')
    expect(api.streamAnswer).not.toHaveBeenCalled()
  })

  it('keeps a partial answer and shows the error when the stream breaks midway', async () => {
    api.streamAnswer.mockImplementation(async (id, q, history, onText) => {
      onText('partial answer')
      throw new Error('connection lost')
    })
    render(<PaperDetail paper={paper} onClose={() => {}} />)
    await userEvent.type(screen.getByPlaceholderText(/ask anything/i), 'q{Enter}')
    expect(await screen.findByText('connection lost')).toBeInTheDocument()
    expect(screen.getByText('partial answer')).toBeInTheDocument()
  })

  it('keeps the partial summary when generation breaks midway', async () => {
    api.streamSummary.mockImplementation(async (id, refresh, onText) => {
      onText('partial summary')
      throw new Error('connection lost')
    })
    render(<PaperDetail paper={{ ...paper, summary: 'Old summary' }} onClose={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: 'Regenerate summary' }))
    expect(await screen.findByText('partial summary')).toBeInTheDocument()
    expect(screen.queryByText('Old summary')).not.toBeInTheDocument()
  })

  it('passes refresh=true when regenerating an existing summary', async () => {
    api.streamSummary.mockResolvedValue('new')
    render(<PaperDetail paper={{ ...paper, summary: 'Old' }} onClose={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: 'Regenerate summary' }))
    expect(api.streamSummary).toHaveBeenCalledWith(1, true, expect.any(Function))
  })
})

