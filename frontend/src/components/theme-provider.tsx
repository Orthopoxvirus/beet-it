import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from 'react'

// ============================================================================
// Types
// ============================================================================

/**
 * Theme mode options
 * - "light": Always use light theme
 * - "dark": Always use dark theme
 * - "system": Match OS theme preference
 */
export type ThemeMode = 'light' | 'dark' | 'system'

/**
 * Resolved theme (actual visual theme being applied)
 */
export type Theme = 'light' | 'dark'

/**
 * Context value exposed by ThemeProvider
 */
export interface ThemeContextValue {
  /** Resolved/actual theme being displayed */
  theme: Theme
  /** User's preference (may be "system") */
  themeMode: ThemeMode
  /** Update the theme mode */
  setThemeMode: (mode: ThemeMode) => void
}

// ============================================================================
// Constants
// ============================================================================

const THEME_MODE_KEY = 'theme-mode'
const DEFAULT_THEME_MODE: ThemeMode = 'system'

// ============================================================================
// Context
// ============================================================================

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined)

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Get the stored theme mode from localStorage
 */
function getStoredThemeMode(): ThemeMode {
  if (typeof window === 'undefined') return DEFAULT_THEME_MODE
  const stored = localStorage.getItem(THEME_MODE_KEY)
  if (stored === 'light' || stored === 'dark' || stored === 'system') {
    return stored
  }
  return DEFAULT_THEME_MODE
}

/**
 * Check if the system prefers dark mode
 */
function getSystemPrefersDark(): boolean {
  if (typeof window === 'undefined') return false
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

/**
 * Resolve the theme mode to an actual theme
 */
function resolveTheme(mode: ThemeMode): Theme {
  if (mode === 'system') {
    return getSystemPrefersDark() ? 'dark' : 'light'
  }
  return mode
}

/**
 * Apply the theme to the document
 */
function applyTheme(theme: Theme): void {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  if (theme === 'dark') {
    root.classList.add('dark')
  } else {
    root.classList.remove('dark')
  }
}

// ============================================================================
// Provider Component
// ============================================================================

interface ThemeProviderProps {
  children: ReactNode
  /** Optional initial theme mode (for testing) */
  defaultThemeMode?: ThemeMode
}

export function ThemeProvider({ children, defaultThemeMode }: ThemeProviderProps) {
  // Initialize from localStorage or default
  const [themeMode, setThemeModeState] = useState<ThemeMode>(
    () => defaultThemeMode ?? getStoredThemeMode()
  )

  // Resolved theme based on mode and system preference
  const [theme, setTheme] = useState<Theme>(() => resolveTheme(themeMode))

  // Update the theme mode and persist to localStorage
  const setThemeMode = useCallback((mode: ThemeMode) => {
    setThemeModeState(mode)
    localStorage.setItem(THEME_MODE_KEY, mode)

    const resolved = resolveTheme(mode)
    setTheme(resolved)
    applyTheme(resolved)
  }, [])

  // Listen for system preference changes when in "system" mode
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')

    const handleChange = () => {
      if (themeMode === 'system') {
        const newTheme = resolveTheme('system')
        setTheme(newTheme)
        applyTheme(newTheme)
      }
    }

    mediaQuery.addEventListener('change', handleChange)
    return () => mediaQuery.removeEventListener('change', handleChange)
  }, [themeMode])

  // Listen for localStorage changes from other tabs
  useEffect(() => {
    const handleStorageChange = (event: StorageEvent) => {
      if (event.key === THEME_MODE_KEY && event.newValue) {
        const newMode = event.newValue as ThemeMode
        if (newMode === 'light' || newMode === 'dark' || newMode === 'system') {
          setThemeModeState(newMode)
          const resolved = resolveTheme(newMode)
          setTheme(resolved)
          applyTheme(resolved)
        }
      }
    }

    window.addEventListener('storage', handleStorageChange)
    return () => window.removeEventListener('storage', handleStorageChange)
  }, [])

  // Apply initial theme on mount (in case head script didn't run or for hydration)
  useEffect(() => {
    applyTheme(theme)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const value: ThemeContextValue = {
    theme,
    themeMode,
    setThemeMode,
  }

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  )
}

// ============================================================================
// Hook
// ============================================================================

/**
 * Hook to access theme context
 * Must be used within a ThemeProvider
 */
export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext)
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}
