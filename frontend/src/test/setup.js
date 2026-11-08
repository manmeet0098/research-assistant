import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// jsdom does not implement scrollIntoView, which the chat panel calls.
Element.prototype.scrollIntoView = vi.fn()

afterEach(() => cleanup())
