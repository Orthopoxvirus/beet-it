import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ThemeProvider } from '@/components/theme-provider'
import SettingsPage from './SettingsPage'

// Mock the settings API
vi.mock('@/api/settings', () => ({
  getSettings: vi.fn(),
  updateSettings: vi.fn(),
}))

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
    dispatchEvent: vi.fn(() => true),
  })
}

describe('SettingsPage', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })
    localStorage.clear()
    window.matchMedia = createMatchMedia(false)
  })

  afterEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  const renderSettingsPage = () => {
    return render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <SettingsPage />
        </ThemeProvider>
      </QueryClientProvider>
    )
  }

  describe('rendering', () => {
    it('should render the settings page with title', async () => {
      const { getSettings } = await import('@/api/settings')
      vi.mocked(getSettings).mockResolvedValue({
        id: 1,
        preferences: { themeMode: 'system' },
        createdAt: '2024-01-01T00:00:00Z',
        updatedAt: '2024-01-01T00:00:00Z',
      })

      renderSettingsPage()

      expect(screen.getByText('Settings')).toBeInTheDocument()
      expect(screen.getByText('Manage your application preferences')).toBeInTheDocument()
    })

    it('should render theme selection options', async () => {
      const { getSettings } = await import('@/api/settings')
      vi.mocked(getSettings).mockResolvedValue({
        id: 1,
        preferences: { themeMode: 'system' },
        createdAt: '2024-01-01T00:00:00Z',
        updatedAt: '2024-01-01T00:00:00Z',
      })

      renderSettingsPage()

      await waitFor(() => {
        expect(screen.getByText('Appearance')).toBeInTheDocument()
      })

      expect(screen.getByText('Light')).toBeInTheDocument()
      expect(screen.getByText('Dark')).toBeInTheDocument()
      expect(screen.getByText('System')).toBeInTheDocument()
    })

    it('should show loading state while fetching settings', async () => {
      const { getSettings } = await import('@/api/settings')
      // Create a promise that won't resolve immediately
      let resolvePromise: (value: any) => void
      const pendingPromise = new Promise((resolve) => {
        resolvePromise = resolve
      })
      vi.mocked(getSettings).mockReturnValue(pendingPromise as any)

      renderSettingsPage()

      expect(document.querySelector('.animate-spin')).toBeInTheDocument()

      // Resolve to clean up
      resolvePromise!({
        id: 1,
        preferences: { themeMode: 'system' },
        createdAt: '2024-01-01T00:00:00Z',
        updatedAt: '2024-01-01T00:00:00Z',
      })
    })

    it('should show error state when settings fail to load', async () => {
      const { getSettings } = await import('@/api/settings')
      vi.mocked(getSettings).mockRejectedValue(new Error('Network error'))

      renderSettingsPage()

      // Wait for loading to finish and error to appear
      await waitFor(
        () => {
          expect(
            screen.getByText('Failed to load settings from server. Your preferences are saved locally.')
          ).toBeInTheDocument()
        },
        { timeout: 3000 }
      )
    })
  })

  describe('theme selection', () => {
    it('should reflect current theme mode in radio selection', async () => {
      localStorage.setItem('theme-mode', 'dark')

      const { getSettings } = await import('@/api/settings')
      vi.mocked(getSettings).mockResolvedValue({
        id: 1,
        preferences: { themeMode: 'dark' },
        createdAt: '2024-01-01T00:00:00Z',
        updatedAt: '2024-01-01T00:00:00Z',
      })

      render(
        <QueryClientProvider client={queryClient}>
          <ThemeProvider defaultThemeMode="dark">
            <SettingsPage />
          </ThemeProvider>
        </QueryClientProvider>
      )

      await waitFor(() => {
        const darkRadio = screen.getByRole('radio', { name: /dark/i })
        expect(darkRadio).toBeChecked()
      })
    })

    it('should update theme when selecting a different mode', async () => {
      const user = userEvent.setup()

      const { getSettings, updateSettings } = await import('@/api/settings')
      vi.mocked(getSettings).mockResolvedValue({
        id: 1,
        preferences: { themeMode: 'system' },
        createdAt: '2024-01-01T00:00:00Z',
        updatedAt: '2024-01-01T00:00:00Z',
      })
      vi.mocked(updateSettings).mockResolvedValue({
        id: 1,
        preferences: { themeMode: 'dark' },
        createdAt: '2024-01-01T00:00:00Z',
        updatedAt: '2024-01-01T00:00:00Z',
      })

      renderSettingsPage()

      await waitFor(() => {
        expect(screen.getByText('Appearance')).toBeInTheDocument()
      })

      const darkRadio = screen.getByRole('radio', { name: /dark/i })
      await user.click(darkRadio)

      // Should update localStorage
      expect(localStorage.getItem('theme-mode')).toBe('dark')

      // Should call update API
      await waitFor(() => {
        expect(updateSettings).toHaveBeenCalledWith({
          preferences: { themeMode: 'dark' },
        })
      })
    })

    it('should apply dark class to document when dark mode selected', async () => {
      const user = userEvent.setup()

      const { getSettings, updateSettings } = await import('@/api/settings')
      vi.mocked(getSettings).mockResolvedValue({
        id: 1,
        preferences: { themeMode: 'light' },
        createdAt: '2024-01-01T00:00:00Z',
        updatedAt: '2024-01-01T00:00:00Z',
      })
      vi.mocked(updateSettings).mockResolvedValue({
        id: 1,
        preferences: { themeMode: 'dark' },
        createdAt: '2024-01-01T00:00:00Z',
        updatedAt: '2024-01-01T00:00:00Z',
      })

      render(
        <QueryClientProvider client={queryClient}>
          <ThemeProvider defaultThemeMode="light">
            <SettingsPage />
          </ThemeProvider>
        </QueryClientProvider>
      )

      await waitFor(() => {
        expect(screen.getByText('Appearance')).toBeInTheDocument()
      })

      const darkRadio = screen.getByRole('radio', { name: /dark/i })
      await user.click(darkRadio)

      expect(document.documentElement.classList.contains('dark')).toBe(true)
    })
  })

  describe('API synchronization', () => {
    it('should show saving indicator during API update', async () => {
      const user = userEvent.setup()

      const { getSettings, updateSettings } = await import('@/api/settings')
      vi.mocked(getSettings).mockResolvedValue({
        id: 1,
        preferences: { themeMode: 'system' },
        createdAt: '2024-01-01T00:00:00Z',
        updatedAt: '2024-01-01T00:00:00Z',
      })

      // Create a pending promise
      let resolveUpdate: (value: any) => void
      const pendingPromise = new Promise((resolve) => {
        resolveUpdate = resolve
      })
      vi.mocked(updateSettings).mockReturnValue(pendingPromise as any)

      renderSettingsPage()

      await waitFor(() => {
        expect(screen.getByText('Appearance')).toBeInTheDocument()
      })

      const darkRadio = screen.getByRole('radio', { name: /dark/i })
      await user.click(darkRadio)

      expect(screen.getByText('Saving...')).toBeInTheDocument()

      // Resolve to clean up
      resolveUpdate!({
        id: 1,
        preferences: { themeMode: 'dark' },
        createdAt: '2024-01-01T00:00:00Z',
        updatedAt: '2024-01-01T00:00:00Z',
      })
    })

    it('should show error when API update fails', async () => {
      const user = userEvent.setup()

      const { getSettings, updateSettings } = await import('@/api/settings')
      vi.mocked(getSettings).mockResolvedValue({
        id: 1,
        preferences: { themeMode: 'system' },
        createdAt: '2024-01-01T00:00:00Z',
        updatedAt: '2024-01-01T00:00:00Z',
      })
      vi.mocked(updateSettings).mockRejectedValue(new Error('Network error'))

      renderSettingsPage()

      await waitFor(() => {
        expect(screen.getByText('Appearance')).toBeInTheDocument()
      })

      const darkRadio = screen.getByRole('radio', { name: /dark/i })
      await user.click(darkRadio)

      await waitFor(() => {
        expect(
          screen.getByText('Failed to sync to server. Your preference is saved locally.')
        ).toBeInTheDocument()
      })

      // But localStorage should still be updated
      expect(localStorage.getItem('theme-mode')).toBe('dark')
    })

    it('should continue working with localStorage when API is unavailable', async () => {
      const user = userEvent.setup()

      const { getSettings, updateSettings } = await import('@/api/settings')
      vi.mocked(getSettings).mockRejectedValue(new Error('API unavailable'))
      vi.mocked(updateSettings).mockRejectedValue(new Error('API unavailable'))

      renderSettingsPage()

      // Wait for error state
      await waitFor(
        () => {
          expect(
            screen.getByText('Failed to load settings from server. Your preferences are saved locally.')
          ).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      // Theme options should still be available
      const darkRadio = screen.getByRole('radio', { name: /dark/i })
      await user.click(darkRadio)

      // localStorage should be updated
      expect(localStorage.getItem('theme-mode')).toBe('dark')
    })
  })

  describe('backend reconciliation', () => {
    it('should sync theme from backend when different from localStorage', async () => {
      // localStorage has 'light' but backend has 'dark'
      localStorage.setItem('theme-mode', 'light')

      const { getSettings } = await import('@/api/settings')
      vi.mocked(getSettings).mockResolvedValue({
        id: 1,
        preferences: { themeMode: 'dark' },
        createdAt: '2024-01-01T00:00:00Z',
        updatedAt: '2024-01-01T00:00:00Z',
      })

      renderSettingsPage()

      // After settings load, the dark radio should be selected
      await waitFor(() => {
        const darkRadio = screen.getByRole('radio', { name: /dark/i })
        expect(darkRadio).toBeChecked()
      })

      // localStorage should be updated to match backend
      expect(localStorage.getItem('theme-mode')).toBe('dark')
    })
  })
})
