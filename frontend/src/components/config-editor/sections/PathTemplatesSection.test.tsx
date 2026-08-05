/**
 * Tests for PathTemplatesSection - the Paths tab of the beets config editor.
 *
 * Covers:
 *  - All four path template fields render (default, singleton, comp, soundtrack).
 *  - The Template Variables Reference is always visible (not collapsed).
 *  - Click-to-insert inserts the variable at the current caret position and
 *    keeps focus on the target input.
 *  - Clicking a variable with no field focused is a no-op.
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { useForm } from 'react-hook-form'

import PathTemplatesSection from './PathTemplatesSection'
import type { BeetsConfig } from '@/types/beets-config'

function Harness() {
  const form = useForm<BeetsConfig>({
    defaultValues: {
      paths: {
        default: '$albumartist/$album/$track - $title',
        singleton: 'Non-Album/$artist/$title',
        comp: 'Compilations/$album/$track - $title',
        albumtype_soundtrack: 'Soundtracks/$album/$track - $title',
      },
    } as unknown as BeetsConfig,
  })

  return <PathTemplatesSection form={form} />
}

describe('PathTemplatesSection', () => {
  it('renders all four path template fields (5.1)', () => {
    render(<Harness />)

    expect(screen.getByLabelText('Default Path')).toBeInTheDocument()
    expect(screen.getByLabelText('Singleton Path')).toBeInTheDocument()
    expect(screen.getByLabelText('Compilation Path')).toBeInTheDocument()
    expect(screen.getByLabelText('Soundtrack Path')).toBeInTheDocument()
  })

  it('shows the Template Variables Reference on initial load (5.2)', () => {
    render(<Harness />)

    // Reference heading should be in the document immediately — not hidden
    // inside a collapsed <details>.
    expect(screen.getByText(/Template Variables Reference/i)).toBeVisible()
    // And at least one common variable token should be present.
    expect(screen.getByText('$albumartist')).toBeVisible()
  })

  it('inserts a variable at the caret position of the focused field (5.3, 5.4, 5.6, 5.7)', async () => {
    render(<Harness />)

    const input = screen.getByLabelText('Default Path') as HTMLInputElement

    // Place the caret in the middle of the current value.
    input.focus()
    fireEvent.focus(input)
    input.setSelectionRange(13, 13) // after "$albumartist/"

    const variableButton = screen.getAllByText('$album')[0]
    fireEvent.click(variableButton)

    await waitFor(() => {
      expect(input.value).toBe('$albumartist/$album$album/$track - $title')
    })

    // Focus should return to the input after insert.
    await waitFor(() => {
      expect(document.activeElement).toBe(input)
    })
  })

  it('does nothing when a variable is clicked with no input focused (5.5)', () => {
    render(<Harness />)

    const input = screen.getByLabelText('Default Path') as HTMLInputElement
    const initialValue = input.value

    const variableButton = screen.getAllByText('$album')[0]
    fireEvent.click(variableButton)

    // No focus → no insert.
    expect(input.value).toBe(initialValue)
  })
})
