import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AlphabetNav, ALPHABET } from './AlphabetNav'

describe('AlphabetNav', () => {
  const defaultProps = {
    availableLetters: ['A', 'B', 'M', 'T'],
    currentLetter: null,
    onLetterSelect: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('rendering', () => {
    it('should render all alphabet letters plus #', () => {
      render(<AlphabetNav {...defaultProps} />)

      // Check that all 27 letters are rendered (A-Z + #)
      ALPHABET.forEach((letter) => {
        expect(screen.getByRole('button', { name: letter })).toBeInTheDocument()
      })
    })

    it('should render with navigation role and proper aria label', () => {
      render(<AlphabetNav {...defaultProps} />)

      const nav = screen.getByRole('navigation', { name: 'Alphabet navigation' })
      expect(nav).toBeInTheDocument()
    })

    it('should apply custom className', () => {
      render(<AlphabetNav {...defaultProps} className="custom-class" />)

      const nav = screen.getByRole('navigation')
      expect(nav).toHaveClass('custom-class')
    })
  })

  describe('letter availability', () => {
    it('should enable available letters', () => {
      render(<AlphabetNav {...defaultProps} availableLetters={['A', 'B', 'C']} />)

      expect(screen.getByRole('button', { name: 'A' })).not.toBeDisabled()
      expect(screen.getByRole('button', { name: 'B' })).not.toBeDisabled()
      expect(screen.getByRole('button', { name: 'C' })).not.toBeDisabled()
    })

    it('should disable unavailable letters', () => {
      render(<AlphabetNav {...defaultProps} availableLetters={['A']} />)

      expect(screen.getByRole('button', { name: 'B' })).toBeDisabled()
      expect(screen.getByRole('button', { name: 'Z' })).toBeDisabled()
      expect(screen.getByRole('button', { name: '#' })).toBeDisabled()
    })

    it('should handle empty availableLetters', () => {
      render(<AlphabetNav {...defaultProps} availableLetters={[]} />)

      // All letters should be disabled
      ALPHABET.forEach((letter) => {
        expect(screen.getByRole('button', { name: letter })).toBeDisabled()
      })
    })

    it('should handle # as an available letter', () => {
      render(<AlphabetNav {...defaultProps} availableLetters={['#']} />)

      expect(screen.getByRole('button', { name: '#' })).not.toBeDisabled()
      expect(screen.getByRole('button', { name: 'A' })).toBeDisabled()
    })
  })

  describe('current letter highlight', () => {
    it('should highlight the current letter', () => {
      render(<AlphabetNav {...defaultProps} currentLetter="M" />)

      const currentButton = screen.getByRole('button', { name: 'M' })
      expect(currentButton).toHaveAttribute('aria-current', 'location')
    })

    it('should not highlight other letters', () => {
      render(<AlphabetNav {...defaultProps} currentLetter="M" />)

      const otherButton = screen.getByRole('button', { name: 'A' })
      expect(otherButton).not.toHaveAttribute('aria-current')
    })

    it('should handle null currentLetter', () => {
      render(<AlphabetNav {...defaultProps} currentLetter={null} />)

      // No letter should have aria-current
      ALPHABET.forEach((letter) => {
        const button = screen.getByRole('button', { name: letter })
        expect(button).not.toHaveAttribute('aria-current')
      })
    })
  })

  describe('click interactions', () => {
    it('should call onLetterSelect when clicking an available letter', () => {
      const onLetterSelect = vi.fn()
      render(<AlphabetNav {...defaultProps} onLetterSelect={onLetterSelect} />)

      fireEvent.click(screen.getByRole('button', { name: 'A' }))
      expect(onLetterSelect).toHaveBeenCalledWith('A')
    })

    it('should call onLetterSelect for # symbol', () => {
      const onLetterSelect = vi.fn()
      render(
        <AlphabetNav
          {...defaultProps}
          availableLetters={['#']}
          onLetterSelect={onLetterSelect}
        />
      )

      fireEvent.click(screen.getByRole('button', { name: '#' }))
      expect(onLetterSelect).toHaveBeenCalledWith('#')
    })

    it('should not call onLetterSelect when clicking a disabled letter', () => {
      const onLetterSelect = vi.fn()
      render(
        <AlphabetNav
          {...defaultProps}
          availableLetters={['A']}
          onLetterSelect={onLetterSelect}
        />
      )

      // Click a disabled letter (B is not in availableLetters)
      fireEvent.click(screen.getByRole('button', { name: 'B' }))
      expect(onLetterSelect).not.toHaveBeenCalled()
    })
  })

  describe('pointer events', () => {
    // Note: Full pointer event testing with getBoundingClientRect-based position
    // calculation is limited in jsdom. These tests verify that the component
    // has proper pointer event handlers attached and CSS classes for touch handling.

    beforeEach(() => {
      // Mock pointer capture methods for jsdom
      Element.prototype.setPointerCapture = vi.fn()
      Element.prototype.releasePointerCapture = vi.fn()
      Element.prototype.hasPointerCapture = vi.fn().mockReturnValue(true)
    })

    it('should have touch-action none to prevent scroll conflicts', () => {
      render(<AlphabetNav {...defaultProps} />)

      const nav = screen.getByRole('navigation')
      expect(nav).toHaveClass('touch-none')
    })

    it('should have select-none to prevent text selection during drag', () => {
      render(<AlphabetNav {...defaultProps} />)

      const nav = screen.getByRole('navigation')
      expect(nav).toHaveClass('select-none')
    })

    it('should set pointer capture on pointer down', () => {
      render(<AlphabetNav {...defaultProps} />)

      const nav = screen.getByRole('navigation')

      // Fire pointer down - verifies handler is attached
      fireEvent.pointerDown(nav, { clientY: 0 })

      // The pointer capture should be set (pointerId may be undefined in jsdom)
      expect(Element.prototype.setPointerCapture).toHaveBeenCalled()
    })

    it('should release pointer capture on pointer up', () => {
      render(<AlphabetNav {...defaultProps} />)

      const nav = screen.getByRole('navigation')

      // Fire pointer down then up
      fireEvent.pointerDown(nav, { clientY: 0 })
      fireEvent.pointerUp(nav, { clientY: 0 })

      // The pointer capture should be released
      expect(Element.prototype.releasePointerCapture).toHaveBeenCalled()
    })
  })

  describe('accessibility', () => {
    it('should have proper tabIndex for available letters', () => {
      render(<AlphabetNav {...defaultProps} availableLetters={['A', 'B']} />)

      expect(screen.getByRole('button', { name: 'A' })).toHaveAttribute('tabIndex', '0')
      expect(screen.getByRole('button', { name: 'B' })).toHaveAttribute('tabIndex', '0')
    })

    it('should have tabIndex -1 for unavailable letters', () => {
      render(<AlphabetNav {...defaultProps} availableLetters={['A']} />)

      expect(screen.getByRole('button', { name: 'Z' })).toHaveAttribute('tabIndex', '-1')
    })

    it('should have aria-disabled on unavailable letters', () => {
      render(<AlphabetNav {...defaultProps} availableLetters={['A']} />)

      expect(screen.getByRole('button', { name: 'Z' })).toHaveAttribute('aria-disabled', 'true')
    })
  })

  describe('ALPHABET constant', () => {
    it('should contain 27 items (A-Z plus #)', () => {
      expect(ALPHABET).toHaveLength(27)
    })

    it('should start with A and end with #', () => {
      expect(ALPHABET[0]).toBe('A')
      expect(ALPHABET[25]).toBe('Z')
      expect(ALPHABET[26]).toBe('#')
    })

    it('should be in alphabetical order with # at the end', () => {
      const letters = ALPHABET.slice(0, 26)
      const sortedLetters = [...letters].sort()
      expect(letters).toEqual(sortedLetters)
      expect(ALPHABET[26]).toBe('#')
    })
  })
})
