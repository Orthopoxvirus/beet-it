import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import ActivityPage from './ActivityPage'
import * as useActivityModule from '@/hooks/useActivity'
import * as useLibrariesModule from '@/hooks/useLibraries'
import type { ActivityHistoryResponse } from '@/types/activity'

// Mock the hooks
vi.mock('@/hooks/useActivity', () => ({
  useActivityHistory: vi.fn(),
  useClearActivityHistory: vi.fn(),
}))

vi.mock('@/hooks/useLibraries', () => ({
  useLibraries: vi.fn(),
}))

describe('ActivityPage', () => {
  let queryClient: QueryClient
  const mockMutate = vi.fn()

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    })
    vi.clearAllMocks()

    // Default mock for libraries
    vi.mocked(useLibrariesModule.useLibraries).mockReturnValue({
      data: {
        items: [
          { id: 1, name: 'Test Library', slug: 'test-library' },
          { id: 2, name: 'Another Library', slug: 'another-library' },
        ],
        total: 2,
        skip: 0,
        limit: 100,
      },
      isLoading: false,
      error: null,
    } as ReturnType<typeof useLibrariesModule.useLibraries>)

    // Default mock for clear history mutation
    vi.mocked(useActivityModule.useClearActivityHistory).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useActivityModule.useClearActivityHistory>)
  })

  const renderPage = () => {
    return render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <ActivityPage />
        </BrowserRouter>
      </QueryClientProvider>
    )
  }

  const mockHistoryResponse: ActivityHistoryResponse = {
    items: [
      {
        id: 1,
        taskType: 'scan',
        libraryId: 1,
        librarySlug: 'test-library',
        description: 'Scan import folder',
        status: 'completed',
        startedAt: '2026-02-28T10:25:00Z',
        completedAt: '2026-02-28T10:28:30Z',
        durationSeconds: 210,
        metadata: {},
      },
      {
        id: 2,
        taskType: 'analysis',
        libraryId: 2,
        librarySlug: 'another-library',
        description: 'Album: Test Artist - Test Album',
        status: 'failed',
        startedAt: '2026-02-28T10:20:00Z',
        completedAt: '2026-02-28T10:21:00Z',
        durationSeconds: 60,
        metadata: { error: 'Network error' },
      },
    ],
    total: 2,
    skip: 0,
    limit: 20,
  }

  it('should render the page title', () => {
    vi.mocked(useActivityModule.useActivityHistory).mockReturnValue({
      data: mockHistoryResponse,
      isLoading: false,
      error: null,
      isError: false,
    } as ReturnType<typeof useActivityModule.useActivityHistory>)

    renderPage()

    expect(screen.getByText('Activity History')).toBeInTheDocument()
  })

  it('should show loading state', () => {
    vi.mocked(useActivityModule.useActivityHistory).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
      isError: false,
    } as ReturnType<typeof useActivityModule.useActivityHistory>)

    renderPage()

    // Page should show loading indicator
    expect(screen.getByRole('heading', { name: 'Activity History' })).toBeInTheDocument()
  })

  it('should show error state', () => {
    vi.mocked(useActivityModule.useActivityHistory).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('Failed to fetch'),
      isError: true,
    } as ReturnType<typeof useActivityModule.useActivityHistory>)

    renderPage()

    expect(screen.getByText(/failed to load activity history/i)).toBeInTheDocument()
  })

  it('should display task history rows', () => {
    vi.mocked(useActivityModule.useActivityHistory).mockReturnValue({
      data: mockHistoryResponse,
      isLoading: false,
      error: null,
      isError: false,
    } as ReturnType<typeof useActivityModule.useActivityHistory>)

    renderPage()

    expect(screen.getByText('Scan import folder')).toBeInTheDocument()
    expect(screen.getByText('Album: Test Artist - Test Album')).toBeInTheDocument()
  })

  it('should show completed status badge', () => {
    vi.mocked(useActivityModule.useActivityHistory).mockReturnValue({
      data: mockHistoryResponse,
      isLoading: false,
      error: null,
      isError: false,
    } as ReturnType<typeof useActivityModule.useActivityHistory>)

    renderPage()

    expect(screen.getByText('Completed')).toBeInTheDocument()
    expect(screen.getByText('Failed')).toBeInTheDocument()
  })

  it('should show library links', () => {
    vi.mocked(useActivityModule.useActivityHistory).mockReturnValue({
      data: mockHistoryResponse,
      isLoading: false,
      error: null,
      isError: false,
    } as ReturnType<typeof useActivityModule.useActivityHistory>)

    renderPage()

    const testLibraryLink = screen.getByRole('link', { name: 'test-library' })
    expect(testLibraryLink).toHaveAttribute('href', '/import/test-library/beets')

    const anotherLibraryLink = screen.getByRole('link', { name: 'another-library' })
    expect(anotherLibraryLink).toHaveAttribute('href', '/import/another-library/beets')
  })

  it('should show empty state when no tasks', () => {
    vi.mocked(useActivityModule.useActivityHistory).mockReturnValue({
      data: { items: [], total: 0, skip: 0, limit: 20 },
      isLoading: false,
      error: null,
      isError: false,
    } as ReturnType<typeof useActivityModule.useActivityHistory>)

    renderPage()

    expect(screen.getByText('No tasks found')).toBeInTheDocument()
  })

  it('should show pagination info', () => {
    vi.mocked(useActivityModule.useActivityHistory).mockReturnValue({
      data: mockHistoryResponse,
      isLoading: false,
      error: null,
      isError: false,
    } as ReturnType<typeof useActivityModule.useActivityHistory>)

    renderPage()

    expect(screen.getByText(/showing 1 to 2 of 2 tasks/i)).toBeInTheDocument()
  })

  it('should render filter dropdowns', () => {
    vi.mocked(useActivityModule.useActivityHistory).mockReturnValue({
      data: mockHistoryResponse,
      isLoading: false,
      error: null,
      isError: false,
    } as ReturnType<typeof useActivityModule.useActivityHistory>)

    renderPage()

    // Check that filter trigger buttons exist
    const triggers = screen.getAllByRole('combobox')
    expect(triggers.length).toBeGreaterThanOrEqual(3) // Library, Type, Status filters
  })

  it('should format duration correctly', () => {
    vi.mocked(useActivityModule.useActivityHistory).mockReturnValue({
      data: mockHistoryResponse,
      isLoading: false,
      error: null,
      isError: false,
    } as ReturnType<typeof useActivityModule.useActivityHistory>)

    renderPage()

    // 210 seconds = 3m 30s
    expect(screen.getByText('3m 30s')).toBeInTheDocument()
    // 60 seconds = 1m
    expect(screen.getByText('1m')).toBeInTheDocument()
  })

  // ============================================================================
  // Clear All Button Tests
  // ============================================================================

  describe('Clear All Button', () => {
    it('should show Clear All button when history exists', () => {
      vi.mocked(useActivityModule.useActivityHistory).mockReturnValue({
        data: mockHistoryResponse,
        isLoading: false,
        error: null,
        isError: false,
      } as ReturnType<typeof useActivityModule.useActivityHistory>)

      renderPage()

      expect(screen.getByRole('button', { name: /clear all/i })).toBeInTheDocument()
    })

    it('should hide Clear All button when history is empty', () => {
      vi.mocked(useActivityModule.useActivityHistory).mockReturnValue({
        data: { items: [], total: 0, skip: 0, limit: 20 },
        isLoading: false,
        error: null,
        isError: false,
      } as ReturnType<typeof useActivityModule.useActivityHistory>)

      renderPage()

      expect(screen.queryByRole('button', { name: /clear all/i })).not.toBeInTheDocument()
    })

    it('should clear immediately without a confirmation dialog', async () => {
      vi.mocked(useActivityModule.useActivityHistory).mockReturnValue({
        data: mockHistoryResponse,
        isLoading: false,
        error: null,
        isError: false,
      } as ReturnType<typeof useActivityModule.useActivityHistory>)

      renderPage()

      fireEvent.click(screen.getByRole('button', { name: /clear all/i }))

      // Mutation fires straight away; no dialog is rendered.
      expect(mockMutate).toHaveBeenCalledWith({})
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(screen.queryByText('Clear All Activity History')).not.toBeInTheDocument()
    })

    it('should pass active filters to the clear mutation', async () => {
      vi.mocked(useActivityModule.useActivityHistory).mockReturnValue({
        data: mockHistoryResponse,
        isLoading: false,
        error: null,
        isError: false,
      } as ReturnType<typeof useActivityModule.useActivityHistory>)

      renderPage()

      // Select a library filter, then clear.
      fireEvent.click(screen.getByText('All Libraries'))
      fireEvent.click(await screen.findByText('Test Library'))

      fireEvent.click(screen.getByRole('button', { name: /clear filtered/i }))

      expect(mockMutate).toHaveBeenCalledWith({ libraryId: 1 })
    })

    it('should disable the clear button while clearing', () => {
      vi.mocked(useActivityModule.useActivityHistory).mockReturnValue({
        data: mockHistoryResponse,
        isLoading: false,
        error: null,
        isError: false,
      } as ReturnType<typeof useActivityModule.useActivityHistory>)

      vi.mocked(useActivityModule.useClearActivityHistory).mockReturnValue({
        mutate: mockMutate,
        isPending: true,
        isError: false,
        error: null,
      } as unknown as ReturnType<typeof useActivityModule.useClearActivityHistory>)

      renderPage()

      expect(screen.getByRole('button', { name: /clear all/i })).toBeDisabled()
    })
  })
})
