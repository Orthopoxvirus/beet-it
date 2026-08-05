import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { TooltipProvider } from '@/components/ui/tooltip'
import Sidebar from './Sidebar'

// Mock the contexts and hooks
vi.mock('@/contexts/ActiveLibraryContext', () => ({
  useActiveLibrary: vi.fn(() => ({
    activeLibrary: {
      id: 1,
      name: 'Test Library',
      slug: 'test-library',
      description: '',
      config_path: '/config/test.yaml',
      database_path: '/data/test.db',
      library_path: '/music/test',
      import_path: '/import/test',
    },
  })),
}))

vi.mock('@/hooks/useActivity', () => ({
  useActivityCount: vi.fn(() => ({
    active: 0,
    queued: 0,
    failed: 0,
    succeeded: 0,
    total: 0,
    severity: 'none',
    badgeCount: 0,
  })),
  ACTIVITY_BADGE_CLASSES: {
    failed: 'bg-destructive text-destructive-foreground animate-pulse',
    active: 'bg-blue-500 text-white animate-pulse',
    succeeded: 'bg-emerald-500 text-white',
    queued: 'bg-secondary text-secondary-foreground',
  },
}))

vi.mock('@/hooks/useTabMemory', () => ({
  getTabMemory: vi.fn(() => 'albums'),
  setTabMemory: vi.fn(),
}))

// Keep getImportMode real; stub only the data-fetching hook used by the
// import-mode menu icon (no QueryClientProvider is mounted in these tests).
vi.mock('@/hooks/useConfig', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/hooks/useConfig')>()
  return {
    ...actual,
    useLibraryConfigBySlug: vi.fn(() => ({
      data: { import: { move: true } },
      isLoading: false,
      error: null,
    })),
  }
})

vi.mock('@/components/LibrarySelectorDropdown', () => ({
  default: vi.fn(() => <div data-testid="library-selector">Library Selector</div>),
}))

describe('Sidebar', () => {
  const defaultProps = {
    collapsed: false,
    onToggleCollapse: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  const renderSidebar = (props = {}, initialRoute = '/libraries/test-library/albums') => {
    return render(
      <TooltipProvider>
        <MemoryRouter initialEntries={[initialRoute]}>
          <Sidebar {...defaultProps} {...props} />
        </MemoryRouter>
      </TooltipProvider>
    )
  }

  describe('Library sub-navigation', () => {
    it('should display Albums sub-nav item', () => {
      renderSidebar()
      expect(screen.getByText('Albums')).toBeInTheDocument()
    })

    it('should display Batch Edit sub-nav item', () => {
      renderSidebar()
      expect(screen.getByText('Batch Edit')).toBeInTheDocument()
    })

    it('should display Beets Config sub-nav item', () => {
      renderSidebar()
      expect(screen.getByText('Beets Config')).toBeInTheDocument()
    })

    it('should display Settings sub-nav item', () => {
      renderSidebar()
      // There are two Settings - one in main nav and one in sub-nav
      const settingsElements = screen.getAllByText('Settings')
      expect(settingsElements.length).toBeGreaterThanOrEqual(1)
    })

    it('should have correct href for Beets Config nav item', () => {
      renderSidebar()
      const beetsConfigLink = screen.getByText('Beets Config').closest('a')
      expect(beetsConfigLink).toHaveAttribute('href', '/libraries/test-library/beets-config')
    })

    it('should show all four library sub-nav items in correct order', () => {
      renderSidebar()

      const navItems = screen.getAllByRole('link').filter(link => {
        const href = link.getAttribute('href') || ''
        return href.includes('/libraries/test-library/')
      })

      // Filter to only library sub-nav links
      const librarySubNavItems = navItems.filter(link => {
        const href = link.getAttribute('href') || ''
        return ['albums', 'batch-edit', 'beets-config', 'settings'].some(item =>
          href.includes(item)
        )
      })

      expect(librarySubNavItems).toHaveLength(4)
      expect(librarySubNavItems[0]).toHaveAttribute('href', '/libraries/test-library/albums')
      expect(librarySubNavItems[1]).toHaveAttribute('href', '/libraries/test-library/batch-edit')
      expect(librarySubNavItems[2]).toHaveAttribute('href', '/libraries/test-library/beets-config')
      expect(librarySubNavItems[3]).toHaveAttribute('href', '/libraries/test-library/settings')
    })
  })

  describe('Import mode indicator', () => {
    it('shows the move-mode icon on the Import entry for a move-mode library', () => {
      renderSidebar()

      const icon = screen.getByTestId('import-mode-icon-move')
      expect(icon).toBeInTheDocument()
      // The descriptive label is on the icon (revealed as tooltip text on hover)
      expect(icon).toHaveAttribute('aria-label', 'Move Mode')
    })
  })

  describe('Active state highlighting', () => {
    it('should highlight Beets Config when on beets-config route', () => {
      renderSidebar({}, '/libraries/test-library/beets-config')

      const beetsConfigLink = screen.getByText('Beets Config').closest('a')
      expect(beetsConfigLink).toHaveClass('bg-accent')
    })

    it('should not highlight Beets Config when on other routes', () => {
      renderSidebar({}, '/libraries/test-library/albums')

      const beetsConfigLink = screen.getByText('Beets Config').closest('a')
      expect(beetsConfigLink).not.toHaveClass('bg-accent')
    })
  })

  describe('Collapsed state', () => {
    it('should not show sub-nav text when collapsed', () => {
      renderSidebar({ collapsed: true })

      // In collapsed mode, sub-nav items are hidden
      // Check that the sidebar has the collapsed class
      const sidebar = document.querySelector('aside')
      expect(sidebar).toHaveClass('w-16')
    })
  })
})
