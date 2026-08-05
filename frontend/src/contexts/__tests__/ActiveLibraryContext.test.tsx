import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import {
  ActiveLibraryProvider,
  useActiveLibrary,
  useSyncActiveLibraryFromUrl,
} from '../ActiveLibraryContext'
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

// Mock the useLibraries hook
vi.mock('@/hooks/useLibraries', () => ({
  useLibraries: vi.fn(() => ({
    data: { items: mockLibraries, total: 2, skip: 0, limit: 100 },
    isLoading: false,
    error: null,
  })),
}))

// Test component to access context values
function TestConsumer() {
  const { activeLibrary, libraries, isLoading, setActiveLibrary } = useActiveLibrary()
  return (
    <div>
      <div data-testid="active-library">{activeLibrary?.slug || 'none'}</div>
      <div data-testid="library-count">{libraries.length}</div>
      <div data-testid="is-loading">{isLoading ? 'true' : 'false'}</div>
      <button onClick={() => setActiveLibrary(mockLibraries[1])}>
        Select Vinyl
      </button>
    </div>
  )
}

// Component to test URL sync
function TestUrlSync({ slug }: { slug: string }) {
  useSyncActiveLibraryFromUrl(slug)
  const { activeLibrary } = useActiveLibrary()
  return <div data-testid="synced-library">{activeLibrary?.slug || 'none'}</div>
}

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ActiveLibraryProvider>{children}</ActiveLibraryProvider>
        </MemoryRouter>
      </QueryClientProvider>
    )
  }
}

describe('ActiveLibraryContext', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  describe('initial state', () => {
    it('defaults to first library when no stored selection', async () => {
      render(<TestConsumer />, { wrapper: createWrapper() })

      await waitFor(() => {
        expect(screen.getByTestId('active-library')).toHaveTextContent('my-music')
      })
    })

    it('uses stored library slug from localStorage', async () => {
      localStorage.setItem('active-library-slug', 'vinyl-rips')

      render(<TestConsumer />, { wrapper: createWrapper() })

      await waitFor(() => {
        expect(screen.getByTestId('active-library')).toHaveTextContent('vinyl-rips')
      })
    })

    it('falls back to first library when stored slug does not exist', async () => {
      localStorage.setItem('active-library-slug', 'nonexistent')

      render(<TestConsumer />, { wrapper: createWrapper() })

      await waitFor(() => {
        expect(screen.getByTestId('active-library')).toHaveTextContent('my-music')
      })
    })

    it('provides all libraries', async () => {
      render(<TestConsumer />, { wrapper: createWrapper() })

      await waitFor(() => {
        expect(screen.getByTestId('library-count')).toHaveTextContent('2')
      })
    })
  })

  describe('setActiveLibrary', () => {
    it('updates active library', async () => {
      render(<TestConsumer />, { wrapper: createWrapper() })

      await waitFor(() => {
        expect(screen.getByTestId('active-library')).toHaveTextContent('my-music')
      })

      act(() => {
        screen.getByText('Select Vinyl').click()
      })

      await waitFor(() => {
        expect(screen.getByTestId('active-library')).toHaveTextContent('vinyl-rips')
      })
    })

    it('persists selection to localStorage', async () => {
      render(<TestConsumer />, { wrapper: createWrapper() })

      await waitFor(() => {
        expect(screen.getByTestId('active-library')).toHaveTextContent('my-music')
      })

      act(() => {
        screen.getByText('Select Vinyl').click()
      })

      await waitFor(() => {
        expect(localStorage.getItem('active-library-slug')).toBe('vinyl-rips')
      })
    })
  })

  describe('useSyncActiveLibraryFromUrl', () => {
    it('updates context when URL slug differs from active library', async () => {
      localStorage.setItem('active-library-slug', 'my-music')

      render(<TestUrlSync slug="vinyl-rips" />, { wrapper: createWrapper() })

      await waitFor(() => {
        expect(screen.getByTestId('synced-library')).toHaveTextContent('vinyl-rips')
      })
    })

    it('does not update when URL slug matches active library', async () => {
      localStorage.setItem('active-library-slug', 'my-music')

      render(<TestUrlSync slug="my-music" />, { wrapper: createWrapper() })

      await waitFor(() => {
        expect(screen.getByTestId('synced-library')).toHaveTextContent('my-music')
      })
    })
  })

  describe('useActiveLibrary outside provider', () => {
    it('throws error when used outside provider', () => {
      // Suppress console.error for expected error
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

      expect(() => {
        render(<TestConsumer />)
      }).toThrow('useActiveLibrary must be used within an ActiveLibraryProvider')

      consoleSpy.mockRestore()
    })
  })
})
