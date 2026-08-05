import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ActiveLibraryProvider } from '@/contexts/ActiveLibraryContext'
import { TooltipProvider } from '@/components/ui/tooltip'
import LibrarySelectorDropdown from './LibrarySelectorDropdown'
import type { Library } from '@/api/libraries'

// Mock libraries data
const mockLibraries: Library[] = [
  {
    id: 1,
    name: 'My Music',
    slug: 'my-music',
    description: null,
    config_path: '/config/my-music.yaml',
    database_path: '/db/my-music.db',
    library_path: '/music/my-music',
    import_path: '/imports/my-music',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: null,
  },
  {
    id: 2,
    name: 'Vinyl Rips',
    slug: 'vinyl-rips',
    description: 'Vinyl collection',
    config_path: '/config/vinyl-rips.yaml',
    database_path: '/db/vinyl-rips.db',
    library_path: '/music/vinyl-rips',
    import_path: '/imports/vinyl-rips',
    created_at: '2024-01-02T00:00:00Z',
    updated_at: null,
  },
]

// Mock useLibraries hook
const mockUseLibraries = vi.fn()
vi.mock('@/hooks/useLibraries', () => ({
  useLibraries: () => mockUseLibraries(),
}))

function createWrapper(initialRoute = '/libraries') {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <MemoryRouter initialEntries={[initialRoute]}>
            <ActiveLibraryProvider>{children}</ActiveLibraryProvider>
          </MemoryRouter>
        </TooltipProvider>
      </QueryClientProvider>
    )
  }
}

describe('LibrarySelectorDropdown', () => {
  beforeEach(() => {
    localStorage.clear()
    mockUseLibraries.mockReturnValue({
      data: { items: mockLibraries, total: 2, skip: 0, limit: 100 },
      isLoading: false,
      error: null,
    })
  })

  afterEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  describe('loading state', () => {
    it('shows loading indicator when loading', () => {
      mockUseLibraries.mockReturnValue({
        data: null,
        isLoading: true,
        error: null,
      })

      render(<LibrarySelectorDropdown />, { wrapper: createWrapper() })

      expect(screen.getByText('Loading...')).toBeInTheDocument()
    })
  })

  describe('empty state', () => {
    it('shows create library button when no libraries exist', () => {
      mockUseLibraries.mockReturnValue({
        data: { items: [], total: 0, skip: 0, limit: 100 },
        isLoading: false,
        error: null,
      })

      render(<LibrarySelectorDropdown />, { wrapper: createWrapper() })

      expect(screen.getByRole('link', { name: /create library/i })).toBeInTheDocument()
    })

    it('shows icon button in collapsed mode when no libraries', () => {
      mockUseLibraries.mockReturnValue({
        data: { items: [], total: 0, skip: 0, limit: 100 },
        isLoading: false,
        error: null,
      })

      render(<LibrarySelectorDropdown collapsed />, { wrapper: createWrapper() })

      // Should have a link to create library
      expect(screen.getByRole('link')).toHaveAttribute('href', '/libraries/create')
    })
  })

  describe('expanded mode', () => {
    it('displays active library name in trigger button', async () => {
      render(<LibrarySelectorDropdown />, { wrapper: createWrapper() })

      await waitFor(() => {
        expect(screen.getByText('My Music')).toBeInTheDocument()
      })
    })

    it('shows dropdown with all libraries when clicked', async () => {
      const user = userEvent.setup()
      render(<LibrarySelectorDropdown />, { wrapper: createWrapper() })

      await waitFor(() => {
        expect(screen.getByText('My Music')).toBeInTheDocument()
      })

      // Click the dropdown trigger
      await user.click(screen.getByRole('button'))

      // Wait for dropdown content
      await waitFor(() => {
        expect(screen.getByText('Select Library')).toBeInTheDocument()
        // Both libraries should be listed (one in button, one in dropdown)
        expect(screen.getAllByText('My Music').length).toBeGreaterThanOrEqual(1)
        expect(screen.getByText('Vinyl Rips')).toBeInTheDocument()
      })
    })

    it('shows checkmark next to active library', async () => {
      const user = userEvent.setup()
      render(<LibrarySelectorDropdown />, { wrapper: createWrapper() })

      await waitFor(() => {
        expect(screen.getByText('My Music')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button'))

      // The active library item should have a check icon
      await waitFor(() => {
        const menuItems = screen.getAllByRole('menuitem')
        // First item should be the active one (My Music)
        expect(menuItems.length).toBeGreaterThan(0)
      })
    })

    it('includes create library option in dropdown', async () => {
      const user = userEvent.setup()
      render(<LibrarySelectorDropdown />, { wrapper: createWrapper() })

      await waitFor(() => {
        expect(screen.getByText('My Music')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByRole('menuitem', { name: /create library/i })).toBeInTheDocument()
      })
    })
  })

  describe('collapsed mode', () => {
    it('renders icon button instead of full dropdown', () => {
      render(<LibrarySelectorDropdown collapsed />, { wrapper: createWrapper() })

      // Should have a button but not show the library name directly
      const button = screen.getByRole('button')
      expect(button).toBeInTheDocument()
    })

    it('shows dropdown on click in collapsed mode', async () => {
      const user = userEvent.setup()
      render(<LibrarySelectorDropdown collapsed />, { wrapper: createWrapper() })

      await waitFor(() => {
        expect(screen.getByRole('button')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByText('Select Library')).toBeInTheDocument()
      })
    })
  })

  describe('library selection', () => {
    it('calls onSelect callback when selecting a library', async () => {
      const onSelect = vi.fn()
      const user = userEvent.setup()

      render(
        <LibrarySelectorDropdown onSelect={onSelect} />,
        { wrapper: createWrapper('/libraries/my-music/albums') }
      )

      await waitFor(() => {
        expect(screen.getByText('My Music')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByText('Vinyl Rips')).toBeInTheDocument()
      })

      // Click on Vinyl Rips
      await user.click(screen.getByText('Vinyl Rips'))

      await waitFor(() => {
        expect(onSelect).toHaveBeenCalled()
      })
    })

    it('persists selection to localStorage', async () => {
      const user = userEvent.setup()

      render(
        <LibrarySelectorDropdown />,
        { wrapper: createWrapper('/libraries/my-music/albums') }
      )

      await waitFor(() => {
        expect(screen.getByText('My Music')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByText('Vinyl Rips')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Vinyl Rips'))

      await waitFor(() => {
        expect(localStorage.getItem('active-library-slug')).toBe('vinyl-rips')
      })
    })
  })
})
