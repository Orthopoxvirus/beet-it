import * as React from 'react'
import { cn } from '@/lib/utils'

/**
 * Complete alphabet including numbers/special character indicator.
 * Letters are displayed A-Z with '#' representing albums starting
 * with numbers or non-alphabetic characters.
 */
const ALPHABET = [
  'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
  'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', '#'
] as const

/**
 * Props for the AlphabetNav component.
 */
export interface AlphabetNavProps {
  /**
   * Array of letters that have content (albums).
   * Letters not in this array will be displayed as dimmed/disabled.
   */
  availableLetters: string[]

  /**
   * The currently active/visible letter section.
   * This letter will be highlighted in the navigation bar.
   */
  currentLetter: string | null

  /**
   * Callback fired when a letter is selected via click or drag.
   * Only fires for available (non-disabled) letters.
   */
  onLetterSelect: (letter: string) => void

  /**
   * Optional additional CSS classes to apply to the container.
   */
  className?: string
}

/**
 * AlphabetNav - A vertical alphabet navigation bar for quick scrolling.
 *
 * This component displays a fixed vertical bar with letters A-Z and '#'
 * for quick navigation through alphabetically sorted content. It supports
 * both click and touch-drag interactions using the Pointer Events API.
 *
 * @example
 * ```tsx
 * <AlphabetNav
 *   availableLetters={['A', 'B', 'M', 'T']}
 *   currentLetter="M"
 *   onLetterSelect={(letter) => scrollToLetter(letter)}
 * />
 * ```
 */
export function AlphabetNav({
  availableLetters,
  currentLetter,
  onLetterSelect,
  className,
}: AlphabetNavProps) {
  const navRef = React.useRef<HTMLElement>(null)
  const [isDragging, setIsDragging] = React.useState(false)
  const availableSet = React.useMemo(
    () => new Set(availableLetters),
    [availableLetters]
  )

  /**
   * Calculate which letter is at a given Y position within the nav element.
   */
  const getLetterAtPosition = React.useCallback((clientY: number): string | null => {
    const nav = navRef.current
    if (!nav) return null

    const rect = nav.getBoundingClientRect()
    const relativeY = clientY - rect.top
    const letterHeight = rect.height / ALPHABET.length
    const index = Math.floor(relativeY / letterHeight)

    if (index >= 0 && index < ALPHABET.length) {
      return ALPHABET[index]
    }
    return null
  }, [])

  /**
   * Handle letter selection, only if the letter is available.
   */
  const handleLetterSelect = React.useCallback(
    (letter: string) => {
      if (availableSet.has(letter)) {
        onLetterSelect(letter)
      }
    },
    [availableSet, onLetterSelect]
  )

  /**
   * Handle pointer down - start potential drag.
   */
  const handlePointerDown = React.useCallback(
    (e: React.PointerEvent) => {
      const nav = navRef.current
      if (!nav) return

      // Capture the pointer for drag tracking
      nav.setPointerCapture(e.pointerId)
      setIsDragging(true)

      const letter = getLetterAtPosition(e.clientY)
      if (letter) {
        handleLetterSelect(letter)
      }
    },
    [getLetterAtPosition, handleLetterSelect]
  )

  /**
   * Handle pointer move - update selection during drag.
   */
  const handlePointerMove = React.useCallback(
    (e: React.PointerEvent) => {
      if (!isDragging) return

      const letter = getLetterAtPosition(e.clientY)
      if (letter) {
        handleLetterSelect(letter)
      }
    },
    [isDragging, getLetterAtPosition, handleLetterSelect]
  )

  /**
   * Handle pointer up - end drag.
   */
  const handlePointerUp = React.useCallback(
    (e: React.PointerEvent) => {
      const nav = navRef.current
      if (nav && nav.hasPointerCapture(e.pointerId)) {
        nav.releasePointerCapture(e.pointerId)
      }
      setIsDragging(false)
    },
    []
  )

  /**
   * Handle pointer cancel - clean up drag state.
   */
  const handlePointerCancel = React.useCallback(
    (e: React.PointerEvent) => {
      const nav = navRef.current
      if (nav && nav.hasPointerCapture(e.pointerId)) {
        nav.releasePointerCapture(e.pointerId)
      }
      setIsDragging(false)
    },
    []
  )

  return (
    <nav
      ref={navRef}
      className={cn(
        // Fixed positioning on right edge. Hidden below sm — at phone widths the
        // 26 letters can't reach a usable tap-target height, and the nav eats
        // horizontal space the album grid needs. Use the top scroll or browser
        // find-in-page on mobile instead.
        'hidden sm:flex',
        'fixed right-2 top-1/2 -translate-y-1/2 z-50',
        // Flexbox column layout
        'flex-col items-center justify-center',
        // Visual styling
        'bg-background/80 backdrop-blur-sm rounded-full py-1 px-0.5',
        // Border and shadow
        'border border-border/50 shadow-sm',
        // Touch handling - prevent scroll conflicts
        'touch-none select-none',
        className
      )}
      role="navigation"
      aria-label="Alphabet navigation"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerCancel}
    >
      {ALPHABET.map((letter) => {
        const isAvailable = availableSet.has(letter)
        const isCurrent = letter === currentLetter

        return (
          <button
            key={letter}
            type="button"
            className={cn(
              // Base styles
              'w-5 h-4 text-[10px] font-medium leading-none',
              'flex items-center justify-center',
              'rounded-sm transition-colors',
              // Available letter styles
              isAvailable && [
                'text-foreground cursor-pointer',
                'hover:bg-accent hover:text-accent-foreground',
              ],
              // Unavailable (disabled) letter styles
              !isAvailable && [
                'text-muted-foreground/40 cursor-default',
                'pointer-events-none',
              ],
              // Current letter highlight
              isCurrent && isAvailable && [
                'bg-primary text-primary-foreground',
                'hover:bg-primary/90',
              ]
            )}
            onClick={() => handleLetterSelect(letter)}
            disabled={!isAvailable}
            aria-current={isCurrent ? 'location' : undefined}
            aria-disabled={!isAvailable}
            tabIndex={isAvailable ? 0 : -1}
          >
            {letter}
          </button>
        )
      })}
    </nav>
  )
}

AlphabetNav.displayName = 'AlphabetNav'

export { ALPHABET }
