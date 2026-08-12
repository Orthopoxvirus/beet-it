import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import { ArtistFilter } from './ArtistFilter'

function setup(props: Partial<React.ComponentProps<typeof ArtistFilter>> = {}) {
  const onChange = vi.fn()
  render(
    <ArtistFilter
      inResult={['Beethoven', 'Die Ärzte']}
      others={['Aphex Twin', 'Zappa']}
      selected={[]}
      onChange={onChange}
      {...props}
    />
  )
  return { onChange }
}

const open = () => fireEvent.click(screen.getByLabelText('Filter by album artist'))
const optionTexts = () => screen.getAllByRole('option').map((o) => o.textContent)

describe('ArtistFilter', () => {
  it('counts the selection in the trigger label', () => {
    setup({ selected: ['Zappa'] })
    expect(screen.getByLabelText('Filter by album artist')).toHaveTextContent('1 album artist')
  })

  it('orders checked first, then in-result, then the rest', () => {
    setup({ selected: ['Zappa'] })
    open()
    expect(optionTexts()).toEqual(['Zappa', 'Beethoven', 'Die Ärzte', 'Aphex Twin'])
  })

  it('adds an artist without dropping the existing selection', () => {
    const { onChange } = setup({ selected: ['Zappa'] })
    open()
    fireEvent.click(screen.getByRole('option', { name: 'Beethoven' }))
    expect(onChange).toHaveBeenCalledWith(['Zappa', 'Beethoven'])
  })

  it('removes an already-selected artist', () => {
    const { onChange } = setup({ selected: ['Zappa'] })
    open()
    fireEvent.click(screen.getByRole('option', { name: 'Zappa' }))
    expect(onChange).toHaveBeenCalledWith([])
  })

  it('disables album artists not in the current result and ignores clicks on them', () => {
    const { onChange } = setup()
    open()
    // 'Aphex Twin' is an `others` entry — present but disabled.
    const other = screen.getByRole('option', { name: 'Aphex Twin' })
    expect(other).toBeDisabled()
    expect(other).toHaveAttribute('aria-disabled', 'true')
    fireEvent.click(other)
    expect(onChange).not.toHaveBeenCalled()
    // An in-result artist stays interactive.
    fireEvent.click(screen.getByRole('option', { name: 'Beethoven' }))
    expect(onChange).toHaveBeenCalledWith(['Beethoven'])
  })

  it('filters the visible list via the search box', () => {
    setup({ selected: ['Zappa'] })
    open()
    fireEvent.change(screen.getByLabelText('Filter album artists'), {
      target: { value: 'a' },
    })
    expect(optionTexts()).toEqual(['Zappa', 'Aphex Twin'])
  })

  it('clears the whole selection', () => {
    const { onChange } = setup({ selected: ['Zappa', 'Beethoven'] })
    open()
    fireEvent.click(screen.getByRole('button', { name: /clear 2 selected/i }))
    expect(onChange).toHaveBeenCalledWith([])
  })

  // Regression for #202: the list must scroll, not clip. A Radix ScrollArea
  // root carried max-height + overflow-hidden and clipped long lists (its
  // Viewport's height:100% can't resolve against a max-height-only parent).
  // The options must therefore live in a bounded, natively scrollable box.
  it('keeps the artist list in a bounded, natively scrollable container', () => {
    setup()
    open()
    const scroller = screen.getByRole('option', { name: 'Beethoven' }).closest('.overflow-y-auto')
    expect(scroller).not.toBeNull()
    expect(scroller).toHaveClass('max-h-64')
  })
})
