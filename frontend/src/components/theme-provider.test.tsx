import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, act, renderHook } from '@testing-library/react'
import { ThemeProvider, useTheme, type ThemeMode } from './theme-provider'

// Mock matchMedia
const createMatchMedia = (prefersDark: boolean) => {
  const listeners: ((e: MediaQueryListEvent) => void)[] = []

  return (query: string): MediaQueryList => ({
    matches: query.includes('dark') ? prefersDark : !prefersDark,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: (_: string, cb: (e: MediaQueryListEvent) => void) => {
      listeners.push(cb)
    },
    removeEventListener: (_: string, cb: (e: MediaQueryListEvent) => void) => {
      const index = listeners.indexOf(cb)
      if (index > -1) listeners.splice(index, 1)
    },
    dispatchEvent: vi.fn((event: MediaQueryListEvent) => {
      listeners.forEach((cb) => cb(event))
      return true
    }),
  })
}

describe('ThemeProvider', () => {
  let originalMatchMedia: typeof window.matchMedia
  let originalLocalStorage: Storage

  beforeEach(() => {
    // Store originals
    originalMatchMedia = window.matchMedia
    originalLocalStorage = window.localStorage

    // Clear localStorage
    localStorage.clear()

    // Default to light mode system preference
    window.matchMedia = createMatchMedia(false)
  })

  afterEach(() => {
    // Restore originals
    window.matchMedia = originalMatchMedia
    localStorage.clear()
  })

  describe('initialization', () => {
    it('should initialize with system theme mode when no localStorage value', () => {
      const TestComponent = () => {
        const { themeMode, theme } = useTheme()
        return (
          <div>
            <span data-testid="mode">{themeMode}</span>
            <span data-testid="theme">{theme}</span>
          </div>
        )
      }

      render(
        <ThemeProvider>
          <TestComponent />
        </ThemeProvider>
      )

      expect(screen.getByTestId('mode')).toHaveTextContent('system')
      expect(screen.getByTestId('theme')).toHaveTextContent('light')
    })

    it('should initialize from localStorage value', () => {
      localStorage.setItem('theme-mode', 'dark')

      const TestComponent = () => {
        const { themeMode, theme } = useTheme()
        return (
          <div>
            <span data-testid="mode">{themeMode}</span>
            <span data-testid="theme">{theme}</span>
          </div>
        )
      }

      render(
        <ThemeProvider>
          <TestComponent />
        </ThemeProvider>
      )

      expect(screen.getByTestId('mode')).toHaveTextContent('dark')
      expect(screen.getByTestId('theme')).toHaveTextContent('dark')
    })

    it('should respect defaultThemeMode prop', () => {
      const TestComponent = () => {
        const { themeMode } = useTheme()
        return <span data-testid="mode">{themeMode}</span>
      }

      render(
        <ThemeProvider defaultThemeMode="dark">
          <TestComponent />
        </ThemeProvider>
      )

      expect(screen.getByTestId('mode')).toHaveTextContent('dark')
    })
  })

  describe('setThemeMode', () => {
    it('should update theme mode and persist to localStorage', () => {
      const TestComponent = () => {
        const { themeMode, setThemeMode } = useTheme()
        return (
          <div>
            <span data-testid="mode">{themeMode}</span>
            <button onClick={() => setThemeMode('dark')}>Set Dark</button>
          </div>
        )
      }

      render(
        <ThemeProvider>
          <TestComponent />
        </ThemeProvider>
      )

      expect(screen.getByTestId('mode')).toHaveTextContent('system')

      act(() => {
        screen.getByText('Set Dark').click()
      })

      expect(screen.getByTestId('mode')).toHaveTextContent('dark')
      expect(localStorage.getItem('theme-mode')).toBe('dark')
    })

    it('should apply dark class to document when dark mode', () => {
      const TestComponent = () => {
        const { setThemeMode } = useTheme()
        return <button onClick={() => setThemeMode('dark')}>Set Dark</button>
      }

      render(
        <ThemeProvider>
          <TestComponent />
        </ThemeProvider>
      )

      act(() => {
        screen.getByText('Set Dark').click()
      })

      expect(document.documentElement.classList.contains('dark')).toBe(true)
    })

    it('should remove dark class when switching to light mode', () => {
      document.documentElement.classList.add('dark')

      const TestComponent = () => {
        const { setThemeMode } = useTheme()
        return <button onClick={() => setThemeMode('light')}>Set Light</button>
      }

      render(
        <ThemeProvider defaultThemeMode="dark">
          <TestComponent />
        </ThemeProvider>
      )

      act(() => {
        screen.getByText('Set Light').click()
      })

      expect(document.documentElement.classList.contains('dark')).toBe(false)
    })
  })

  describe('system theme', () => {
    it('should resolve to dark when system prefers dark', () => {
      window.matchMedia = createMatchMedia(true)

      const TestComponent = () => {
        const { theme, themeMode } = useTheme()
        return (
          <div>
            <span data-testid="mode">{themeMode}</span>
            <span data-testid="theme">{theme}</span>
          </div>
        )
      }

      render(
        <ThemeProvider>
          <TestComponent />
        </ThemeProvider>
      )

      expect(screen.getByTestId('mode')).toHaveTextContent('system')
      expect(screen.getByTestId('theme')).toHaveTextContent('dark')
    })

    it('should resolve to light when system prefers light', () => {
      window.matchMedia = createMatchMedia(false)

      const TestComponent = () => {
        const { theme, themeMode } = useTheme()
        return (
          <div>
            <span data-testid="mode">{themeMode}</span>
            <span data-testid="theme">{theme}</span>
          </div>
        )
      }

      render(
        <ThemeProvider>
          <TestComponent />
        </ThemeProvider>
      )

      expect(screen.getByTestId('mode')).toHaveTextContent('system')
      expect(screen.getByTestId('theme')).toHaveTextContent('light')
    })
  })

  describe('cross-tab synchronization', () => {
    it('should update when storage event is fired', () => {
      const TestComponent = () => {
        const { themeMode } = useTheme()
        return <span data-testid="mode">{themeMode}</span>
      }

      render(
        <ThemeProvider>
          <TestComponent />
        </ThemeProvider>
      )

      expect(screen.getByTestId('mode')).toHaveTextContent('system')

      // Simulate storage event from another tab
      act(() => {
        const event = new StorageEvent('storage', {
          key: 'theme-mode',
          newValue: 'dark',
          oldValue: 'system',
          storageArea: localStorage,
        })
        window.dispatchEvent(event)
      })

      expect(screen.getByTestId('mode')).toHaveTextContent('dark')
    })

    it('should ignore storage events for other keys', () => {
      const TestComponent = () => {
        const { themeMode } = useTheme()
        return <span data-testid="mode">{themeMode}</span>
      }

      render(
        <ThemeProvider>
          <TestComponent />
        </ThemeProvider>
      )

      expect(screen.getByTestId('mode')).toHaveTextContent('system')

      // Simulate storage event for different key
      act(() => {
        const event = new StorageEvent('storage', {
          key: 'other-key',
          newValue: 'some-value',
          oldValue: null,
          storageArea: localStorage,
        })
        window.dispatchEvent(event)
      })

      // Should remain unchanged
      expect(screen.getByTestId('mode')).toHaveTextContent('system')
    })

    it('should ignore invalid theme mode values', () => {
      const TestComponent = () => {
        const { themeMode } = useTheme()
        return <span data-testid="mode">{themeMode}</span>
      }

      render(
        <ThemeProvider>
          <TestComponent />
        </ThemeProvider>
      )

      expect(screen.getByTestId('mode')).toHaveTextContent('system')

      // Simulate storage event with invalid value
      act(() => {
        const event = new StorageEvent('storage', {
          key: 'theme-mode',
          newValue: 'invalid-mode',
          oldValue: 'system',
          storageArea: localStorage,
        })
        window.dispatchEvent(event)
      })

      // Should remain unchanged
      expect(screen.getByTestId('mode')).toHaveTextContent('system')
    })
  })

  describe('useTheme hook', () => {
    it('should throw error when used outside provider', () => {
      // Suppress console.error for this test
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

      const TestComponent = () => {
        useTheme()
        return null
      }

      expect(() => render(<TestComponent />)).toThrow(
        'useTheme must be used within a ThemeProvider'
      )

      consoleSpy.mockRestore()
    })

    it('should return theme context value', () => {
      const { result } = renderHook(() => useTheme(), {
        wrapper: ({ children }) => <ThemeProvider>{children}</ThemeProvider>,
      })

      expect(result.current).toHaveProperty('theme')
      expect(result.current).toHaveProperty('themeMode')
      expect(result.current).toHaveProperty('setThemeMode')
      expect(typeof result.current.setThemeMode).toBe('function')
    })
  })
})
