import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { createMemoryRouter, RouterProvider, Outlet } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import LibraryBeetsConfigPage from './LibraryBeetsConfigPage'
import type { Library } from '@/api/libraries'
import type { BeetsConfig } from '@/types/beets-config'

// Mock the config hooks
vi.mock('@/hooks/useConfig', () => ({
  useLibraryConfig: vi.fn(),
  useUpdateLibraryConfig: vi.fn(() => ({
    mutateAsync: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  })),
  useLibraryPathStatus: vi.fn(() => ({
    data: { directoryExists: true, databaseExists: true },
    isLoading: false,
    error: null,
  })),
  useInitializeLibrary: vi.fn(() => ({
    mutateAsync: vi.fn(),
    isPending: false,
  })),
}))

// Mock the config editor components
vi.mock('@/components/config-editor/PluginManager', () => ({
  default: vi.fn(() => <div data-testid="plugin-manager">PluginManager</div>),
}))

vi.mock('@/components/config-editor/sections/GeneralSettingsSection', () => ({
  default: vi.fn(() => <div data-testid="general-settings">GeneralSettings</div>),
}))

vi.mock('@/components/config-editor/sections/ImportSettingsSection', () => ({
  default: vi.fn(() => <div data-testid="import-settings">ImportSettings</div>),
}))

vi.mock('@/components/config-editor/sections/PathTemplatesSection', () => ({
  default: vi.fn(() => <div data-testid="path-templates">PathTemplates</div>),
}))

vi.mock('@/components/config-editor/sections/ConvertSettingsSection', () => ({
  default: vi.fn(() => <div data-testid="convert-settings">ConvertSettings</div>),
}))

const mockLibrary: Library = {
  id: 1,
  name: 'Test Library',
  slug: 'test-library',
  description: 'A test library',
  config_path: '/config/test.yaml',
  database_path: '/data/test.db',
  library_path: '/music/test',
  import_path: '/import/test',
}

const mockConfig: BeetsConfig = {
  directory: '/music/test',
  library: '/data/test.db',
  plugins: ['web', 'embedart'],
  import: {
    copy: true,
    move: false,
    write: true,
    log: '/logs/import.log',
  },
  paths: {},
}

// Layout component that provides outlet context
function MockLibraryLayout() {
  return <Outlet context={{ library: mockLibrary, albumCount: 10 }} />
}

describe('LibraryBeetsConfigPage', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    })
    vi.clearAllMocks()
  })

  const renderPage = (slug: string = 'test-library') => {
    const router = createMemoryRouter(
      [
        {
          path: '/libraries/:slug',
          element: <MockLibraryLayout />,
          children: [
            {
              path: 'beets-config',
              element: <LibraryBeetsConfigPage />,
            },
          ],
        },
      ],
      {
        initialEntries: [`/libraries/${slug}/beets-config`],
      }
    )

    return render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    )
  }

  describe('Loading state', () => {
    it('should show loading spinner while fetching config', async () => {
      const { useLibraryConfig } = await import('@/hooks/useConfig')

      vi.mocked(useLibraryConfig).mockReturnValue({
        data: undefined,
        isLoading: true,
        error: null,
      } as ReturnType<typeof useLibraryConfig>)

      renderPage()

      // Should show loading spinner
      const spinner = document.querySelector('.animate-spin')
      expect(spinner).toBeInTheDocument()
    })
  })

  describe('Error state', () => {
    it('should show error message when config fetch fails', async () => {
      const { useLibraryConfig } = await import('@/hooks/useConfig')

      vi.mocked(useLibraryConfig).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: new Error('Network error'),
      } as ReturnType<typeof useLibraryConfig>)

      renderPage()

      await waitFor(() => {
        // Check for the error title
        expect(screen.getByRole('heading', { name: /failed to load configuration/i })).toBeInTheDocument()
        // Check for the error details
        expect(screen.getByText('Network error')).toBeInTheDocument()
      })
    })
  })

  describe('Config editor display', () => {
    beforeEach(async () => {
      const { useLibraryConfig } = await import('@/hooks/useConfig')

      vi.mocked(useLibraryConfig).mockReturnValue({
        data: mockConfig,
        isLoading: false,
        error: null,
      } as ReturnType<typeof useLibraryConfig>)
    })

    it('should display page title with library name', async () => {
      renderPage()

      await waitFor(() => {
        expect(screen.getByText('Beets Configuration')).toBeInTheDocument()
        expect(screen.getByText('Test Library')).toBeInTheDocument()
      })
    })

    it('should display config tabs', async () => {
      renderPage()

      await waitFor(() => {
        expect(screen.getByRole('tab', { name: 'General' })).toBeInTheDocument()
        expect(screen.getByRole('tab', { name: 'Plugins' })).toBeInTheDocument()
        expect(screen.getByRole('tab', { name: 'Paths' })).toBeInTheDocument()
        expect(screen.getByRole('tab', { name: 'Import' })).toBeInTheDocument()
        expect(screen.getByRole('tab', { name: 'Convert' })).toBeInTheDocument()
      })
    })

    it('should show Save Configuration button', async () => {
      renderPage()

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /save configuration/i })).toBeInTheDocument()
      })
    })

    it('should show Discard button', async () => {
      renderPage()

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /discard/i })).toBeInTheDocument()
      })
    })

    it('should render general settings section by default', async () => {
      renderPage()

      await waitFor(() => {
        expect(screen.getByTestId('general-settings')).toBeInTheDocument()
      })
    })

    it('should have clickable plugins tab', async () => {
      renderPage()

      await waitFor(() => {
        const pluginsTab = screen.getByRole('tab', { name: 'Plugins' })
        expect(pluginsTab).toBeInTheDocument()
        expect(pluginsTab).not.toBeDisabled()
      })
    })

    it('should have clickable import tab', async () => {
      renderPage()

      await waitFor(() => {
        const importTab = screen.getByRole('tab', { name: 'Import' })
        expect(importTab).toBeInTheDocument()
        expect(importTab).not.toBeDisabled()
      })
    })
  })

  describe('Save functionality', () => {
    it('should render save button', async () => {
      const { useLibraryConfig, useUpdateLibraryConfig } = await import('@/hooks/useConfig')

      vi.mocked(useLibraryConfig).mockReturnValue({
        data: mockConfig,
        isLoading: false,
        error: null,
      } as ReturnType<typeof useLibraryConfig>)

      vi.mocked(useUpdateLibraryConfig).mockReturnValue({
        mutateAsync: vi.fn(),
        isPending: false,
        isError: false,
        error: null,
      } as unknown as ReturnType<typeof useUpdateLibraryConfig>)

      renderPage()

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /save configuration/i })).toBeInTheDocument()
      })
    })

    it('should show loading spinner when saving', async () => {
      const { useLibraryConfig, useUpdateLibraryConfig } = await import('@/hooks/useConfig')

      vi.mocked(useLibraryConfig).mockReturnValue({
        data: mockConfig,
        isLoading: false,
        error: null,
      } as ReturnType<typeof useLibraryConfig>)

      vi.mocked(useUpdateLibraryConfig).mockReturnValue({
        mutateAsync: vi.fn(),
        isPending: true,
        isError: false,
        error: null,
      } as unknown as ReturnType<typeof useUpdateLibraryConfig>)

      renderPage()

      await waitFor(() => {
        const saveButton = screen.getByRole('button', { name: /save configuration/i })
        expect(saveButton).toBeDisabled()
        // Check for spinner inside the button
        const spinner = saveButton.querySelector('.animate-spin')
        expect(spinner).toBeInTheDocument()
      })
    })

    it('should show error message when save fails', async () => {
      const { useLibraryConfig, useUpdateLibraryConfig } = await import('@/hooks/useConfig')

      vi.mocked(useLibraryConfig).mockReturnValue({
        data: mockConfig,
        isLoading: false,
        error: null,
      } as ReturnType<typeof useLibraryConfig>)

      vi.mocked(useUpdateLibraryConfig).mockReturnValue({
        mutateAsync: vi.fn(),
        isPending: false,
        isError: true,
        error: new Error('Failed to save configuration'),
      } as unknown as ReturnType<typeof useUpdateLibraryConfig>)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('Failed to save configuration')).toBeInTheDocument()
      })
    })
  })

  describe('Discard functionality', () => {
    it('should have disabled discard button when no changes are made', async () => {
      const { useLibraryConfig } = await import('@/hooks/useConfig')

      vi.mocked(useLibraryConfig).mockReturnValue({
        data: mockConfig,
        isLoading: false,
        error: null,
      } as ReturnType<typeof useLibraryConfig>)

      renderPage()

      await waitFor(() => {
        const discardButton = screen.getByRole('button', { name: /discard/i })
        expect(discardButton).toBeDisabled()
      })
    })
  })
})
