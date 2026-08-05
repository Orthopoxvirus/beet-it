import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import { ActiveLibraryProvider } from '@/contexts/ActiveLibraryContext'
import LibraryRedirect from './LibraryRedirect'
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
]

// Mock useLibraries hook
const mockUseLibraries = vi.fn()
vi.mock('@/hooks/useLibraries', () => ({
  useLibraries: () => mockUseLibraries(),
}))

// Component to capture current location
function LocationDisplay() {
  const location = useLocation()
  return <div data-testid="location">{location.pathname}</div>
}

function createWrapper(initialRoute = '/libraries') {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[initialRoute]}>
          <ActiveLibraryProvider>
            <Routes>
              <Route path="/libraries" element={children} />
              <Route path="/libraries/:slug/:tab" element={<LocationDisplay />} />
              <Route path="/libraries/create" element={<div>Create Library Page</div>} />
            </Routes>
          </ActiveLibraryProvider>
        </MemoryRouter>
      </QueryClientProvider>
    )
  }
}

describe('LibraryRedirect', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  describe('loading state', () => {
    it('shows loading spinner while loading', () => {
      mockUseLibraries.mockReturnValue({
        data: null,
        isLoading: true,
        error: null,
      })

      render(<LibraryRedirect />, { wrapper: createWrapper() })

      expect(document.querySelector('.animate-spin')).toBeInTheDocument()
    })
  })

  describe('empty state', () => {
    it('shows empty state when no libraries exist', () => {
      mockUseLibraries.mockReturnValue({
        data: { items: [], total: 0, skip: 0, limit: 100 },
        isLoading: false,
        error: null,
      })

      render(<LibraryRedirect />, { wrapper: createWrapper() })

      expect(screen.getByText('No libraries yet')).toBeInTheDocument()
      expect(screen.getByRole('link', { name: /create library/i })).toBeInTheDocument()
    })
  })

  describe('redirect behavior', () => {
    it('redirects to active library with default tab', async () => {
      mockUseLibraries.mockReturnValue({
        data: { items: mockLibraries, total: 1, skip: 0, limit: 100 },
        isLoading: false,
        error: null,
      })

      render(<LibraryRedirect />, { wrapper: createWrapper() })

      await waitFor(() => {
        expect(screen.getByTestId('location')).toHaveTextContent('/libraries/my-music/albums')
      })
    })

    it('redirects to remembered tab', async () => {
      localStorage.setItem('nav-tab-memory:library', 'settings')

      mockUseLibraries.mockReturnValue({
        data: { items: mockLibraries, total: 1, skip: 0, limit: 100 },
        isLoading: false,
        error: null,
      })

      render(<LibraryRedirect />, { wrapper: createWrapper() })

      await waitFor(() => {
        expect(screen.getByTestId('location')).toHaveTextContent('/libraries/my-music/settings')
      })
    })

    it('uses stored active library', async () => {
      const secondLibrary: Library = {
        ...mockLibraries[0],
        id: 2,
        name: 'Vinyl Rips',
        slug: 'vinyl-rips',
      }
      localStorage.setItem('active-library-slug', 'vinyl-rips')

      mockUseLibraries.mockReturnValue({
        data: { items: [mockLibraries[0], secondLibrary], total: 2, skip: 0, limit: 100 },
        isLoading: false,
        error: null,
      })

      render(<LibraryRedirect />, { wrapper: createWrapper() })

      await waitFor(() => {
        expect(screen.getByTestId('location')).toHaveTextContent('/libraries/vinyl-rips/albums')
      })
    })
  })
})
