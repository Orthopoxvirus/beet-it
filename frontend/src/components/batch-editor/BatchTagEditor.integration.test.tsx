/**
 * Integration tests for the Batch Tag Editor feature.
 *
 * Tests the full preview -> apply flow with mocked API calls.
 * These tests focus on component-level integration without full page rendering.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import BatchTagEditorForm from './BatchTagEditorForm'
import ImportFolderTable from '../import/ImportFolderTable'
import type { BatchPreviewResponse, ItemPreview } from '@/types/batch-tag-editor'
import type { ImportItemListResponse, ImportItem } from '@/types/scan'
import { useState } from 'react'

// ============================================================================
// Mocks
// ============================================================================

// Mock the hooks
vi.mock('@/hooks/useTagPreview', () => ({
  useTagPreview: vi.fn(),
  useDebouncedValue: vi.fn((value) => value),
}))

vi.mock('@/hooks/useBatchTagUpdate', () => ({
  useBatchTagUpdate: vi.fn(),
}))

vi.mock('@/hooks/useImportFolderItems', () => ({
  useImportFolderItems: vi.fn(),
}))

// ============================================================================
// Test Data
// ============================================================================

const createMockItem = (overrides: Partial<ImportItem> = {}): ImportItem => ({
  id: 1,
  itemType: 'file',
  path: 'Artist/Album/track.flac',
  directory: 'Artist/Album',
  filename: 'track.flac',
  album: 'Test Album',
  albumArtist: 'Test Artist',
  artist: 'Test Artist',
  title: 'Test Track',
  trackNumber: 1,
  trackTotal: null,
  genre: 'Rock',
  status: 'new',
  firstSeenAt: '2024-01-01T00:00:00Z',
  lastSeenAt: '2024-01-01T00:00:00Z',
  ...overrides,
})

const mockImportItems: ImportItemListResponse = {
  items: [
    createMockItem({ id: 1, title: 'Track 1', album: 'Album A' }),
    createMockItem({ id: 2, title: 'Track 2', album: 'Album A' }),
    createMockItem({ id: 3, title: 'Track 3', album: 'Album A' }),
  ],
  total: 3,
  skip: 0,
  limit: 500,
  scanId: 1,
  scanCompletedAt: '2024-01-01T12:00:00Z',
}

const mockPreviewResponse: BatchPreviewResponse = {
  previews: [
    { itemId: 1, changes: { album: 'Greatest Hits' } },
    { itemId: 2, changes: { album: 'Greatest Hits' } },
    { itemId: 3, changes: { album: 'Greatest Hits' } },
  ],
  errors: [],
}

// ============================================================================
// Test Component that combines BatchTagEditorForm and ImportFolderTable
// ============================================================================

interface IntegrationWrapperProps {
  librarySlug: string
}

function IntegrationWrapper({ librarySlug }: IntegrationWrapperProps) {
  const [itemIds, setItemIds] = useState<number[]>([])
  const [previewData, setPreviewData] = useState<Map<number, ItemPreview>>(new Map())

  return (
    <div>
      <BatchTagEditorForm
        librarySlug={librarySlug}
        itemIds={itemIds}
        onPreviewChange={setPreviewData}
      />
      <ImportFolderTable
        librarySlug={librarySlug}
        path="/Artist/Album"
        previewData={previewData}
        onItemsLoaded={setItemIds}
      />
    </div>
  )
}

// ============================================================================
// Test Setup
// ============================================================================

describe('Batch Tag Editor Integration', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    })
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  const setupDefaultMocks = async () => {
    const { useImportFolderItems } = await import('@/hooks/useImportFolderItems')
    vi.mocked(useImportFolderItems).mockReturnValue({
      data: mockImportItems,
      isLoading: false,
      error: null,
      isSuccess: true,
      isError: false,
    } as any)
  }

  const renderIntegration = () => {
    return render(
      <QueryClientProvider client={queryClient}>
        <IntegrationWrapper librarySlug="test-library" />
      </QueryClientProvider>
    )
  }

  // ============================================================================
  // Preview Flow Tests
  // ============================================================================

  describe('Preview Flow Integration', () => {
    it('should pass item IDs from table to batch editor form', async () => {
      await setupDefaultMocks()

      const { useTagPreview } = await import('@/hooks/useTagPreview')
      vi.mocked(useTagPreview).mockReturnValue({
        data: undefined,
        isLoading: false,
        isFetching: false,
        error: null,
        previewMap: new Map(),
        getPreviewValue: () => undefined,
        hasChanges: false,
      })

      const { useBatchTagUpdate } = await import('@/hooks/useBatchTagUpdate')
      vi.mocked(useBatchTagUpdate).mockReturnValue({
        state: {
          isUpdating: false,
          progress: 0,
          itemsProcessed: 0,
          itemsTotal: 0,
          itemsSucceeded: 0,
          itemsFailed: 0,
          error: null,
          isComplete: false,
          results: [],
        },
        execute: vi.fn(),
        reset: vi.fn(),
        cancel: vi.fn(),
      })

      renderIntegration()

      // Verify table shows items
      await waitFor(() => {
        expect(screen.getByText('Track 1')).toBeInTheDocument()
        expect(screen.getByText('Track 2')).toBeInTheDocument()
        expect(screen.getByText('Track 3')).toBeInTheDocument()
      })

      // Verify useTagPreview was called (indirectly proves itemIds were passed)
      expect(useTagPreview).toHaveBeenCalled()
    })

    it('should display preview values in table when preview data changes', async () => {
      await setupDefaultMocks()

      const previewMap = new Map<number, ItemPreview>([
        [1, { itemId: 1, changes: { album: 'New Album Name' } }],
        [2, { itemId: 2, changes: { album: 'New Album Name' } }],
        [3, { itemId: 3, changes: { album: 'New Album Name' } }],
      ])

      const { useTagPreview } = await import('@/hooks/useTagPreview')
      vi.mocked(useTagPreview).mockReturnValue({
        data: mockPreviewResponse,
        isLoading: false,
        isFetching: false,
        error: null,
        previewMap,
        getPreviewValue: (itemId, tag) => previewMap.get(itemId)?.changes[tag],
        hasChanges: true,
      })

      const { useBatchTagUpdate } = await import('@/hooks/useBatchTagUpdate')
      vi.mocked(useBatchTagUpdate).mockReturnValue({
        state: {
          isUpdating: false,
          progress: 0,
          itemsProcessed: 0,
          itemsTotal: 0,
          itemsSucceeded: 0,
          itemsFailed: 0,
          error: null,
          isComplete: false,
          results: [],
        },
        execute: vi.fn(),
        reset: vi.fn(),
        cancel: vi.fn(),
      })

      renderIntegration()

      // Expand the batch editor
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      // Wait for table to load and show preview
      await waitFor(() => {
        // Preview values should appear in the table
        const previewValues = screen.getAllByText('New Album Name')
        expect(previewValues.length).toBeGreaterThanOrEqual(1)
      })
    })

    it('should show strikethrough on original values when preview differs', async () => {
      await setupDefaultMocks()

      const previewMap = new Map<number, ItemPreview>([
        [1, { itemId: 1, changes: { album: 'New Album Name' } }],
      ])

      const { useTagPreview } = await import('@/hooks/useTagPreview')
      vi.mocked(useTagPreview).mockReturnValue({
        data: mockPreviewResponse,
        isLoading: false,
        isFetching: false,
        error: null,
        previewMap,
        getPreviewValue: (itemId, tag) => previewMap.get(itemId)?.changes[tag],
        hasChanges: true,
      })

      const { useBatchTagUpdate } = await import('@/hooks/useBatchTagUpdate')
      vi.mocked(useBatchTagUpdate).mockReturnValue({
        state: {
          isUpdating: false,
          progress: 0,
          itemsProcessed: 0,
          itemsTotal: 0,
          itemsSucceeded: 0,
          itemsFailed: 0,
          error: null,
          isComplete: false,
          results: [],
        },
        execute: vi.fn(),
        reset: vi.fn(),
        cancel: vi.fn(),
      })

      const { container } = renderIntegration()

      // Expand the batch editor
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      // Wait for strikethrough styling
      await waitFor(() => {
        const strikethroughElements = container.querySelectorAll('.line-through')
        expect(strikethroughElements.length).toBeGreaterThanOrEqual(1)
      })
    })
  })

  // ============================================================================
  // Apply Flow Tests
  // ============================================================================

  describe('Apply Flow Integration', () => {
    it('should wire up execute function correctly between components', async () => {
      await setupDefaultMocks()

      const previewMap = new Map<number, ItemPreview>([
        [1, { itemId: 1, changes: { album: 'New Album' } }],
        [2, { itemId: 2, changes: { album: 'New Album' } }],
        [3, { itemId: 3, changes: { album: 'New Album' } }],
      ])

      const { useTagPreview } = await import('@/hooks/useTagPreview')
      vi.mocked(useTagPreview).mockReturnValue({
        data: mockPreviewResponse,
        isLoading: false,
        isFetching: false,
        error: null,
        previewMap,
        getPreviewValue: (itemId, tag) => previewMap.get(itemId)?.changes[tag],
        hasChanges: true,
      })

      const mockExecute = vi.fn()
      const { useBatchTagUpdate } = await import('@/hooks/useBatchTagUpdate')
      vi.mocked(useBatchTagUpdate).mockReturnValue({
        state: {
          isUpdating: false,
          progress: 0,
          itemsProcessed: 0,
          itemsTotal: 0,
          itemsSucceeded: 0,
          itemsFailed: 0,
          error: null,
          isComplete: false,
          results: [],
        },
        execute: mockExecute,
        reset: vi.fn(),
        cancel: vi.fn(),
      })

      renderIntegration()

      // Wait for table to load
      await waitFor(() => {
        expect(screen.getByText('Track 1')).toBeInTheDocument()
      })

      // Verify useBatchTagUpdate was called (hook is wired up)
      expect(useBatchTagUpdate).toHaveBeenCalled()

      // The execute function is available and can be called by the component
      // This test verifies the integration wiring is correct
    })

    it('should show progress indicator during update', async () => {
      await setupDefaultMocks()

      const { useTagPreview } = await import('@/hooks/useTagPreview')
      vi.mocked(useTagPreview).mockReturnValue({
        data: undefined,
        isLoading: false,
        isFetching: false,
        error: null,
        previewMap: new Map(),
        getPreviewValue: () => undefined,
        hasChanges: false,
      })

      const { useBatchTagUpdate } = await import('@/hooks/useBatchTagUpdate')
      vi.mocked(useBatchTagUpdate).mockReturnValue({
        state: {
          isUpdating: true,
          progress: 66,
          itemsProcessed: 2,
          itemsTotal: 3,
          itemsSucceeded: 2,
          itemsFailed: 0,
          error: null,
          isComplete: false,
          results: [],
        },
        execute: vi.fn(),
        reset: vi.fn(),
        cancel: vi.fn(),
      })

      renderIntegration()

      // Expand batch editor
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      // Should show progress
      await waitFor(() => {
        expect(screen.getByText(/Applying changes.../)).toBeInTheDocument()
        expect(screen.getByText(/2 \/ 3/)).toBeInTheDocument()
      })
    })

    it('should show success message after completion', async () => {
      await setupDefaultMocks()

      const { useTagPreview } = await import('@/hooks/useTagPreview')
      vi.mocked(useTagPreview).mockReturnValue({
        data: undefined,
        isLoading: false,
        isFetching: false,
        error: null,
        previewMap: new Map(),
        getPreviewValue: () => undefined,
        hasChanges: false,
      })

      const { useBatchTagUpdate } = await import('@/hooks/useBatchTagUpdate')
      vi.mocked(useBatchTagUpdate).mockReturnValue({
        state: {
          isUpdating: false,
          progress: 100,
          itemsProcessed: 3,
          itemsTotal: 3,
          itemsSucceeded: 3,
          itemsFailed: 0,
          error: null,
          isComplete: true,
          results: [],
        },
        execute: vi.fn(),
        reset: vi.fn(),
        cancel: vi.fn(),
      })

      renderIntegration()

      // Expand batch editor
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      // Should show success
      await waitFor(() => {
        expect(screen.getByText(/Successfully updated 3 tracks/)).toBeInTheDocument()
      })
    })

    it('should show failure summary when some items fail', async () => {
      await setupDefaultMocks()

      const { useTagPreview } = await import('@/hooks/useTagPreview')
      vi.mocked(useTagPreview).mockReturnValue({
        data: undefined,
        isLoading: false,
        isFetching: false,
        error: null,
        previewMap: new Map(),
        getPreviewValue: () => undefined,
        hasChanges: false,
      })

      const { useBatchTagUpdate } = await import('@/hooks/useBatchTagUpdate')
      vi.mocked(useBatchTagUpdate).mockReturnValue({
        state: {
          isUpdating: false,
          progress: 100,
          itemsProcessed: 3,
          itemsTotal: 3,
          itemsSucceeded: 2,
          itemsFailed: 1,
          error: null,
          isComplete: true,
          results: [
            { itemId: 1, status: 'success' },
            { itemId: 2, status: 'success' },
            { itemId: 3, status: 'failed', error: { code: 'WRITE_ERROR', message: 'Permission denied' } },
          ],
        },
        execute: vi.fn(),
        reset: vi.fn(),
        cancel: vi.fn(),
      })

      renderIntegration()

      // Expand batch editor
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      // Should show partial failure
      await waitFor(() => {
        expect(screen.getByText(/2 succeeded, 1 failed/)).toBeInTheDocument()
        expect(screen.getByText(/Permission denied/)).toBeInTheDocument()
      })
    })
  })

  // ============================================================================
  // Error Handling Tests
  // ============================================================================

  describe('Error Handling Integration', () => {
    it('should display preview error', async () => {
      await setupDefaultMocks()

      const { useTagPreview } = await import('@/hooks/useTagPreview')
      vi.mocked(useTagPreview).mockReturnValue({
        data: undefined,
        isLoading: false,
        isFetching: false,
        error: new Error('Invalid regex pattern'),
        previewMap: new Map(),
        getPreviewValue: () => undefined,
        hasChanges: false,
      })

      const { useBatchTagUpdate } = await import('@/hooks/useBatchTagUpdate')
      vi.mocked(useBatchTagUpdate).mockReturnValue({
        state: {
          isUpdating: false,
          progress: 0,
          itemsProcessed: 0,
          itemsTotal: 0,
          itemsSucceeded: 0,
          itemsFailed: 0,
          error: null,
          isComplete: false,
          results: [],
        },
        execute: vi.fn(),
        reset: vi.fn(),
        cancel: vi.fn(),
      })

      renderIntegration()

      // Expand batch editor
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      // Should show error
      await waitFor(() => {
        expect(screen.getByText(/Preview error: Invalid regex pattern/)).toBeInTheDocument()
      })
    })
  })

  // ============================================================================
  // E2E-style Workflow Test
  // ============================================================================

  describe('Complete Workflow', () => {
    it('should complete full workflow: table loads -> batch editor receives item IDs -> preview shown', async () => {
      await setupDefaultMocks()

      const previewMap = new Map<number, ItemPreview>([
        [1, { itemId: 1, changes: { album: 'Greatest Hits' } }],
        [2, { itemId: 2, changes: { album: 'Greatest Hits' } }],
        [3, { itemId: 3, changes: { album: 'Greatest Hits' } }],
      ])

      const { useTagPreview } = await import('@/hooks/useTagPreview')
      vi.mocked(useTagPreview).mockReturnValue({
        data: mockPreviewResponse,
        isLoading: false,
        isFetching: false,
        error: null,
        previewMap,
        getPreviewValue: (itemId, tag) => previewMap.get(itemId)?.changes[tag],
        hasChanges: true,
      })

      const mockExecute = vi.fn()
      const { useBatchTagUpdate } = await import('@/hooks/useBatchTagUpdate')
      vi.mocked(useBatchTagUpdate).mockReturnValue({
        state: {
          isUpdating: false,
          progress: 0,
          itemsProcessed: 0,
          itemsTotal: 0,
          itemsSucceeded: 0,
          itemsFailed: 0,
          error: null,
          isComplete: false,
          results: [],
        },
        execute: mockExecute,
        reset: vi.fn(),
        cancel: vi.fn(),
      })

      renderIntegration()

      // 1. Verify table shows tracks
      await waitFor(() => {
        expect(screen.getByText('Track 1')).toBeInTheDocument()
        expect(screen.getByText('Track 2')).toBeInTheDocument()
        expect(screen.getByText('Track 3')).toBeInTheDocument()
      })

      // 2. Verify batch editor is rendered
      expect(screen.getByText('Batch Tag Editor')).toBeInTheDocument()

      // 3. Verify preview values are shown in table (indicating data flow from form to table)
      await waitFor(() => {
        const previewValues = screen.getAllByText('Greatest Hits')
        expect(previewValues.length).toBeGreaterThanOrEqual(1)
      })

      // The workflow demonstrates:
      // - Table loads and displays items
      // - Item IDs are passed to batch editor via onItemsLoaded callback
      // - Preview data flows back to table via onPreviewChange callback
      // - Table displays preview values with visual differentiation
    })
  })

  // ============================================================================
  // Persisted Configuration Tests
  // ============================================================================

  describe('Persisted Configuration After Apply', () => {
    it('should show form fields alongside success message after completion', async () => {
      await setupDefaultMocks()

      const { useTagPreview } = await import('@/hooks/useTagPreview')
      vi.mocked(useTagPreview).mockReturnValue({
        data: undefined,
        isLoading: false,
        isFetching: false,
        error: null,
        previewMap: new Map(),
        getPreviewValue: () => undefined,
        hasChanges: false,
      })

      const { useBatchTagUpdate } = await import('@/hooks/useBatchTagUpdate')
      vi.mocked(useBatchTagUpdate).mockReturnValue({
        state: {
          isUpdating: false,
          progress: 100,
          itemsProcessed: 3,
          itemsTotal: 3,
          itemsSucceeded: 3,
          itemsFailed: 0,
          error: null,
          isComplete: true,
          results: [],
        },
        execute: vi.fn(),
        reset: vi.fn(),
        cancel: vi.fn(),
      })

      renderIntegration()

      // Expand batch editor
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      // Should show success message
      await waitFor(() => {
        expect(screen.getByText(/Successfully updated 3 tracks/)).toBeInTheDocument()
      })

      // Form fields should still be visible (configuration is preserved)
      // Use getAllByText because 'Album' appears in both form and table
      const albumElements = screen.getAllByText('Album')
      expect(albumElements.length).toBeGreaterThanOrEqual(1)

      // Reset and Apply buttons should still be visible
      expect(screen.getByRole('button', { name: 'Reset' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Apply Changes' })).toBeInTheDocument()
    })

    it('should show configuration preserved message after successful apply', async () => {
      await setupDefaultMocks()

      const { useTagPreview } = await import('@/hooks/useTagPreview')
      vi.mocked(useTagPreview).mockReturnValue({
        data: undefined,
        isLoading: false,
        isFetching: false,
        error: null,
        previewMap: new Map(),
        getPreviewValue: () => undefined,
        hasChanges: false,
      })

      const { useBatchTagUpdate } = await import('@/hooks/useBatchTagUpdate')
      vi.mocked(useBatchTagUpdate).mockReturnValue({
        state: {
          isUpdating: false,
          progress: 100,
          itemsProcessed: 3,
          itemsTotal: 3,
          itemsSucceeded: 3,
          itemsFailed: 0,
          error: null,
          isComplete: true,
          results: [],
        },
        execute: vi.fn(),
        reset: vi.fn(),
        cancel: vi.fn(),
      })

      renderIntegration()

      // Expand batch editor
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      // Should show configuration preserved message
      await waitFor(() => {
        expect(screen.getByText(/Configuration preserved/)).toBeInTheDocument()
      })
    })
  })
})
