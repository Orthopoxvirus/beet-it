import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useForm, FormProvider } from 'react-hook-form'
import GeneralSettingsSection from './GeneralSettingsSection'
import type { BeetsConfig } from '@/types/beets-config'
import { getDefaultBeetsConfig } from '@/types/beets-config'

// Mock the hooks
vi.mock('@/hooks/useConfig', () => ({
  useLibraryPathStatus: vi.fn(),
  useInitializeLibrary: vi.fn(),
}))

// Helper wrapper component that provides form context
function FormWrapper({
  children,
  defaultValues,
}: {
  children: (form: ReturnType<typeof useForm<BeetsConfig>>) => React.ReactNode
  defaultValues?: BeetsConfig
}) {
  const form = useForm<BeetsConfig>({
    defaultValues: defaultValues ?? getDefaultBeetsConfig('/test/music', '/test/db.db'),
  })

  return <FormProvider {...form}>{children(form)}</FormProvider>
}

describe('GeneralSettingsSection', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    })
    vi.clearAllMocks()
  })

  const renderComponent = (libraryId?: number, defaultValues?: BeetsConfig) => {
    return render(
      <QueryClientProvider client={queryClient}>
        <FormWrapper defaultValues={defaultValues}>
          {(form) => (
            <GeneralSettingsSection form={form} libraryId={libraryId} />
          )}
        </FormWrapper>
      </QueryClientProvider>
    )
  }

  describe('Basic rendering', () => {
    beforeEach(async () => {
      const { useLibraryPathStatus, useInitializeLibrary } = await import(
        '@/hooks/useConfig'
      )
      vi.mocked(useLibraryPathStatus).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: null,
      } as ReturnType<typeof useLibraryPathStatus>)
      vi.mocked(useInitializeLibrary).mockReturnValue({
        mutateAsync: vi.fn(),
        isPending: false,
      } as unknown as ReturnType<typeof useInitializeLibrary>)
    })

    it('should render Library Directory field', () => {
      renderComponent()
      expect(screen.getByLabelText(/library directory/i)).toBeInTheDocument()
    })

    it('should render Database File field', () => {
      renderComponent()
      expect(screen.getByLabelText(/database file/i)).toBeInTheDocument()
    })

    it('should render Art Filename field', () => {
      renderComponent()
      expect(screen.getByLabelText(/art filename/i)).toBeInTheDocument()
    })

    it('should render Threaded Operations toggle', () => {
      renderComponent()
      expect(screen.getByLabelText(/threaded operations/i)).toBeInTheDocument()
    })

    it('should render Use Original Date toggle', () => {
      renderComponent()
      expect(screen.getByLabelText(/use original date/i)).toBeInTheDocument()
    })

    it('should render Per-Disc Track Numbers toggle', () => {
      renderComponent()
      expect(screen.getByLabelText(/per-disc track numbers/i)).toBeInTheDocument()
    })

    it('should render browse buttons for path fields', () => {
      renderComponent()
      const browseButtons = screen.getAllByTitle(/browse for/i)
      expect(browseButtons).toHaveLength(2)
    })
  })

  describe('Without library ID', () => {
    beforeEach(async () => {
      const { useLibraryPathStatus, useInitializeLibrary } = await import(
        '@/hooks/useConfig'
      )
      vi.mocked(useLibraryPathStatus).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: null,
      } as ReturnType<typeof useLibraryPathStatus>)
      vi.mocked(useInitializeLibrary).mockReturnValue({
        mutateAsync: vi.fn(),
        isPending: false,
      } as unknown as ReturnType<typeof useInitializeLibrary>)
    })

    it('should not show warning icons when libraryId is not provided', () => {
      renderComponent(undefined)
      expect(screen.queryByLabelText(/warning/i)).not.toBeInTheDocument()
    })

    it('should not show Initialize button when libraryId is not provided', () => {
      renderComponent(undefined)
      expect(
        screen.queryByRole('button', { name: /initialize/i })
      ).not.toBeInTheDocument()
    })

    it('should not show path status loading state when libraryId is not provided', () => {
      renderComponent(undefined)
      expect(
        screen.queryByText(/checking path status/i)
      ).not.toBeInTheDocument()
    })
  })

  describe('Path status loading', () => {
    it('should show loading indicator while checking path status', async () => {
      const { useLibraryPathStatus, useInitializeLibrary } = await import(
        '@/hooks/useConfig'
      )
      vi.mocked(useLibraryPathStatus).mockReturnValue({
        data: undefined,
        isLoading: true,
        error: null,
      } as ReturnType<typeof useLibraryPathStatus>)
      vi.mocked(useInitializeLibrary).mockReturnValue({
        mutateAsync: vi.fn(),
        isPending: false,
      } as unknown as ReturnType<typeof useInitializeLibrary>)

      renderComponent(1)

      await waitFor(() => {
        expect(screen.getByText(/checking path status/i)).toBeInTheDocument()
      })
    })
  })

  describe('Path status error', () => {
    it('should show error message when path status check fails', async () => {
      const { useLibraryPathStatus, useInitializeLibrary } = await import(
        '@/hooks/useConfig'
      )
      vi.mocked(useLibraryPathStatus).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: new Error('Network error'),
      } as ReturnType<typeof useLibraryPathStatus>)
      vi.mocked(useInitializeLibrary).mockReturnValue({
        mutateAsync: vi.fn(),
        isPending: false,
      } as unknown as ReturnType<typeof useInitializeLibrary>)

      renderComponent(1)

      await waitFor(() => {
        expect(screen.getByText(/failed to check path status/i)).toBeInTheDocument()
        expect(screen.getByText(/network error/i)).toBeInTheDocument()
      })
    })
  })

  describe('Warning indicators when paths are missing', () => {
    it('should show warning icon when directory does not exist', async () => {
      const { useLibraryPathStatus, useInitializeLibrary } = await import(
        '@/hooks/useConfig'
      )
      vi.mocked(useLibraryPathStatus).mockReturnValue({
        data: {
          directoryExists: false,
          databaseExists: true,
          directoryPath: '/test/music',
          databasePath: '/test/db.db',
        },
        isLoading: false,
        error: null,
      } as ReturnType<typeof useLibraryPathStatus>)
      vi.mocked(useInitializeLibrary).mockReturnValue({
        mutateAsync: vi.fn(),
        isPending: false,
      } as unknown as ReturnType<typeof useInitializeLibrary>)

      renderComponent(1)

      await waitFor(() => {
        // Should show warning indicator for directory
        const warnings = screen.getAllByLabelText('Warning')
        expect(warnings.length).toBeGreaterThanOrEqual(1)
      })
    })

    it('should show warning icon when database does not exist', async () => {
      const { useLibraryPathStatus, useInitializeLibrary } = await import(
        '@/hooks/useConfig'
      )
      vi.mocked(useLibraryPathStatus).mockReturnValue({
        data: {
          directoryExists: true,
          databaseExists: false,
          directoryPath: '/test/music',
          databasePath: '/test/db.db',
        },
        isLoading: false,
        error: null,
      } as ReturnType<typeof useLibraryPathStatus>)
      vi.mocked(useInitializeLibrary).mockReturnValue({
        mutateAsync: vi.fn(),
        isPending: false,
      } as unknown as ReturnType<typeof useInitializeLibrary>)

      renderComponent(1)

      await waitFor(() => {
        // Should show warning indicator for database
        const warnings = screen.getAllByLabelText('Warning')
        expect(warnings.length).toBeGreaterThanOrEqual(1)
      })
    })

    it('should not show warning icons when both paths exist', async () => {
      const { useLibraryPathStatus, useInitializeLibrary } = await import(
        '@/hooks/useConfig'
      )
      vi.mocked(useLibraryPathStatus).mockReturnValue({
        data: {
          directoryExists: true,
          databaseExists: true,
          directoryPath: '/test/music',
          databasePath: '/test/db.db',
        },
        isLoading: false,
        error: null,
      } as ReturnType<typeof useLibraryPathStatus>)
      vi.mocked(useInitializeLibrary).mockReturnValue({
        mutateAsync: vi.fn(),
        isPending: false,
      } as unknown as ReturnType<typeof useInitializeLibrary>)

      renderComponent(1)

      await waitFor(() => {
        expect(screen.queryByLabelText('Warning')).not.toBeInTheDocument()
      })
    })
  })

  describe('Initialize button', () => {
    it('should show Initialize button when directory is missing', async () => {
      const { useLibraryPathStatus, useInitializeLibrary } = await import(
        '@/hooks/useConfig'
      )
      vi.mocked(useLibraryPathStatus).mockReturnValue({
        data: {
          directoryExists: false,
          databaseExists: true,
          directoryPath: '/test/music',
          databasePath: '/test/db.db',
        },
        isLoading: false,
        error: null,
      } as ReturnType<typeof useLibraryPathStatus>)
      vi.mocked(useInitializeLibrary).mockReturnValue({
        mutateAsync: vi.fn(),
        isPending: false,
      } as unknown as ReturnType<typeof useInitializeLibrary>)

      renderComponent(1)

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /initialize library resources/i })
        ).toBeInTheDocument()
      })
    })

    it('should show Initialize button when database is missing', async () => {
      const { useLibraryPathStatus, useInitializeLibrary } = await import(
        '@/hooks/useConfig'
      )
      vi.mocked(useLibraryPathStatus).mockReturnValue({
        data: {
          directoryExists: true,
          databaseExists: false,
          directoryPath: '/test/music',
          databasePath: '/test/db.db',
        },
        isLoading: false,
        error: null,
      } as ReturnType<typeof useLibraryPathStatus>)
      vi.mocked(useInitializeLibrary).mockReturnValue({
        mutateAsync: vi.fn(),
        isPending: false,
      } as unknown as ReturnType<typeof useInitializeLibrary>)

      renderComponent(1)

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /initialize library resources/i })
        ).toBeInTheDocument()
      })
    })

    it('should NOT show Initialize button when both paths exist', async () => {
      const { useLibraryPathStatus, useInitializeLibrary } = await import(
        '@/hooks/useConfig'
      )
      vi.mocked(useLibraryPathStatus).mockReturnValue({
        data: {
          directoryExists: true,
          databaseExists: true,
          directoryPath: '/test/music',
          databasePath: '/test/db.db',
        },
        isLoading: false,
        error: null,
      } as ReturnType<typeof useLibraryPathStatus>)
      vi.mocked(useInitializeLibrary).mockReturnValue({
        mutateAsync: vi.fn(),
        isPending: false,
      } as unknown as ReturnType<typeof useInitializeLibrary>)

      renderComponent(1)

      await waitFor(() => {
        expect(
          screen.queryByRole('button', { name: /initialize library resources/i })
        ).not.toBeInTheDocument()
      })
    })

    it('should show loading state when initializing', async () => {
      const { useLibraryPathStatus, useInitializeLibrary } = await import(
        '@/hooks/useConfig'
      )
      vi.mocked(useLibraryPathStatus).mockReturnValue({
        data: {
          directoryExists: false,
          databaseExists: false,
          directoryPath: '/test/music',
          databasePath: '/test/db.db',
        },
        isLoading: false,
        error: null,
      } as ReturnType<typeof useLibraryPathStatus>)
      vi.mocked(useInitializeLibrary).mockReturnValue({
        mutateAsync: vi.fn(),
        isPending: true,
      } as unknown as ReturnType<typeof useInitializeLibrary>)

      renderComponent(1)

      await waitFor(() => {
        expect(screen.getByText(/initializing/i)).toBeInTheDocument()
      })
    })

    it('should call initializeLibrary when button is clicked', async () => {
      const mockMutateAsync = vi.fn().mockResolvedValue({
        success: true,
        directoryCreated: true,
        databaseInitialized: true,
        message: 'Library resources initialized successfully',
      })

      const { useLibraryPathStatus, useInitializeLibrary } = await import(
        '@/hooks/useConfig'
      )
      vi.mocked(useLibraryPathStatus).mockReturnValue({
        data: {
          directoryExists: false,
          databaseExists: false,
          directoryPath: '/test/music',
          databasePath: '/test/db.db',
        },
        isLoading: false,
        error: null,
      } as ReturnType<typeof useLibraryPathStatus>)
      vi.mocked(useInitializeLibrary).mockReturnValue({
        mutateAsync: mockMutateAsync,
        isPending: false,
      } as unknown as ReturnType<typeof useInitializeLibrary>)

      renderComponent(1)

      await waitFor(() => {
        const initButton = screen.getByRole('button', {
          name: /initialize library resources/i,
        })
        fireEvent.click(initButton)
      })

      expect(mockMutateAsync).toHaveBeenCalledWith(1)
    })

    it('should show success message after successful initialization', async () => {
      const mockMutateAsync = vi.fn().mockResolvedValue({
        success: true,
        directoryCreated: true,
        databaseInitialized: true,
        message: 'Library resources initialized successfully',
      })

      const { useLibraryPathStatus, useInitializeLibrary } = await import(
        '@/hooks/useConfig'
      )
      vi.mocked(useLibraryPathStatus).mockReturnValue({
        data: {
          directoryExists: false,
          databaseExists: false,
          directoryPath: '/test/music',
          databasePath: '/test/db.db',
        },
        isLoading: false,
        error: null,
      } as ReturnType<typeof useLibraryPathStatus>)
      vi.mocked(useInitializeLibrary).mockReturnValue({
        mutateAsync: mockMutateAsync,
        isPending: false,
      } as unknown as ReturnType<typeof useInitializeLibrary>)

      renderComponent(1)

      const initButton = await screen.findByRole('button', {
        name: /initialize library resources/i,
      })
      fireEvent.click(initButton)

      await waitFor(() => {
        expect(
          screen.getByText(/library resources initialized successfully/i)
        ).toBeInTheDocument()
      })
    })

    it('should show error message when initialization fails', async () => {
      const mockMutateAsync = vi
        .fn()
        .mockRejectedValue(new Error('Initialization failed'))

      const { useLibraryPathStatus, useInitializeLibrary } = await import(
        '@/hooks/useConfig'
      )
      vi.mocked(useLibraryPathStatus).mockReturnValue({
        data: {
          directoryExists: false,
          databaseExists: false,
          directoryPath: '/test/music',
          databasePath: '/test/db.db',
        },
        isLoading: false,
        error: null,
      } as ReturnType<typeof useLibraryPathStatus>)
      vi.mocked(useInitializeLibrary).mockReturnValue({
        mutateAsync: mockMutateAsync,
        isPending: false,
      } as unknown as ReturnType<typeof useInitializeLibrary>)

      renderComponent(1)

      const initButton = await screen.findByRole('button', {
        name: /initialize library resources/i,
      })
      fireEvent.click(initButton)

      await waitFor(() => {
        expect(screen.getByText(/initialization failed/i)).toBeInTheDocument()
      })
    })
  })

  describe('Initialization message display', () => {
    it('should show message about both paths missing when neither exists', async () => {
      const { useLibraryPathStatus, useInitializeLibrary } = await import(
        '@/hooks/useConfig'
      )
      vi.mocked(useLibraryPathStatus).mockReturnValue({
        data: {
          directoryExists: false,
          databaseExists: false,
          directoryPath: '/test/music',
          databasePath: '/test/db.db',
        },
        isLoading: false,
        error: null,
      } as ReturnType<typeof useLibraryPathStatus>)
      vi.mocked(useInitializeLibrary).mockReturnValue({
        mutateAsync: vi.fn(),
        isPending: false,
      } as unknown as ReturnType<typeof useInitializeLibrary>)

      renderComponent(1)

      await waitFor(() => {
        expect(
          screen.getByText(/both the library directory and database file are missing/i)
        ).toBeInTheDocument()
      })
    })

    it('should show message about directory missing when only directory is missing', async () => {
      const { useLibraryPathStatus, useInitializeLibrary } = await import(
        '@/hooks/useConfig'
      )
      vi.mocked(useLibraryPathStatus).mockReturnValue({
        data: {
          directoryExists: false,
          databaseExists: true,
          directoryPath: '/test/music',
          databasePath: '/test/db.db',
        },
        isLoading: false,
        error: null,
      } as ReturnType<typeof useLibraryPathStatus>)
      vi.mocked(useInitializeLibrary).mockReturnValue({
        mutateAsync: vi.fn(),
        isPending: false,
      } as unknown as ReturnType<typeof useInitializeLibrary>)

      renderComponent(1)

      await waitFor(() => {
        expect(
          screen.getByText(/the library directory does not exist/i)
        ).toBeInTheDocument()
      })
    })

    it('should show message about database missing when only database is missing', async () => {
      const { useLibraryPathStatus, useInitializeLibrary } = await import(
        '@/hooks/useConfig'
      )
      vi.mocked(useLibraryPathStatus).mockReturnValue({
        data: {
          directoryExists: true,
          databaseExists: false,
          directoryPath: '/test/music',
          databasePath: '/test/db.db',
        },
        isLoading: false,
        error: null,
      } as ReturnType<typeof useLibraryPathStatus>)
      vi.mocked(useInitializeLibrary).mockReturnValue({
        mutateAsync: vi.fn(),
        isPending: false,
      } as unknown as ReturnType<typeof useInitializeLibrary>)

      renderComponent(1)

      await waitFor(() => {
        expect(
          screen.getByText(/the database file does not exist/i)
        ).toBeInTheDocument()
      })
    })
  })
})
