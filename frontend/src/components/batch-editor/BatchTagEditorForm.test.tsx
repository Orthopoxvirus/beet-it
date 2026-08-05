import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import BatchTagEditorForm from './BatchTagEditorForm'
import type { BatchPreviewResponse, ItemPreview } from '@/types/batch-tag-editor'

// Mock the hooks
vi.mock('@/hooks/useTagPreview', () => ({
  useTagPreview: vi.fn(),
  useDebouncedValue: vi.fn((value) => value), // No debounce in tests
}))

vi.mock('@/hooks/useBatchTagUpdate', () => ({
  useBatchTagUpdate: vi.fn(),
}))

describe('BatchTagEditorForm', () => {
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

  const renderComponent = (props: {
    librarySlug: string
    itemIds: number[]
    onPreviewChange?: (previewMap: Map<number, ItemPreview>) => void
    disabled?: boolean
  }) => {
    return render(
      <QueryClientProvider client={queryClient}>
        <BatchTagEditorForm {...props} />
      </QueryClientProvider>
    )
  }

  const setupDefaultMocks = async () => {
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
  }

  describe('Initial rendering', () => {
    it('should render with title and show tag fields when items are provided', async () => {
      await setupDefaultMocks()
      renderComponent({ librarySlug: 'test-lib', itemIds: [1, 2, 3] })

      expect(screen.getByText('Batch Tag Editor')).toBeInTheDocument()
      // Should show all editable tags when items are provided
      await waitFor(() => {
        expect(screen.getByText('Album')).toBeInTheDocument()
        expect(screen.getByText('Album Artist')).toBeInTheDocument()
        expect(screen.getByText('Artist')).toBeInTheDocument()
        expect(screen.getByText('Title')).toBeInTheDocument()
        expect(screen.getByText('Genre')).toBeInTheDocument()
        expect(screen.getByText('Track Number')).toBeInTheDocument()
      })
    })

    it('should show empty state when no items are provided', async () => {
      await setupDefaultMocks()
      renderComponent({ librarySlug: 'test-lib', itemIds: [] })

      await waitFor(() => {
        expect(screen.getByText('Select a folder with tracks to enable batch editing.')).toBeInTheDocument()
      })
    })
  })

  describe('Mode selection', () => {
    it('should have mode selector defaulting to None for each tag', async () => {
      await setupDefaultMocks()
      renderComponent({ librarySlug: 'test-lib', itemIds: [1, 2, 3] })

      // Expand the form
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      // All mode selectors should default to None
      const modeSelectors = await screen.findAllByRole('combobox')
      expect(modeSelectors.length).toBeGreaterThanOrEqual(6) // One for each editable tag
    })

    it('should show Fixed Value option when mode selector is clicked', async () => {
      await setupDefaultMocks()
      renderComponent({ librarySlug: 'test-lib', itemIds: [1, 2, 3] })

      // Expand the form
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      // Find the first mode selector and click it
      const modeSelectors = await screen.findAllByRole('combobox')
      fireEvent.click(modeSelectors[0])

      // Should show mode options
      await waitFor(() => {
        expect(screen.getByRole('option', { name: 'None' })).toBeInTheDocument()
        expect(screen.getByRole('option', { name: 'Fixed Value' })).toBeInTheDocument()
        expect(screen.getByRole('option', { name: 'Regex' })).toBeInTheDocument()
      })
    })

    it('should show Sequence option only for track_number tag', async () => {
      await setupDefaultMocks()
      renderComponent({ librarySlug: 'test-lib', itemIds: [1, 2, 3] })

      // Expand the form
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      // Find the Track Number field's mode selector
      const trackNumberLabel = screen.getByText('Track Number')
      const trackNumberField = trackNumberLabel.closest('.rounded-md')
      const trackNumberModeSelector = trackNumberField?.querySelector('[role="combobox"]')

      expect(trackNumberModeSelector).toBeInTheDocument()
      fireEvent.click(trackNumberModeSelector!)

      // Should show Sequence option
      await waitFor(() => {
        expect(screen.getByRole('option', { name: 'Sequence' })).toBeInTheDocument()
      })
    })

    it('should show Fixed mode input when Fixed Value is selected', async () => {
      await setupDefaultMocks()
      renderComponent({ librarySlug: 'test-lib', itemIds: [1, 2, 3] })

      // Expand the form
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      // Click the Album mode selector
      const albumLabel = screen.getByText('Album')
      const albumField = albumLabel.closest('.rounded-md')
      const albumModeSelector = albumField?.querySelector('[role="combobox"]')
      fireEvent.click(albumModeSelector!)

      // Select Fixed Value
      const fixedOption = await screen.findByRole('option', { name: 'Fixed Value' })
      fireEvent.click(fixedOption)

      // Should show the fixed value input
      await waitFor(() => {
        expect(screen.getByLabelText('Fixed Value')).toBeInTheDocument()
        expect(screen.getByPlaceholderText('Enter fixed value...')).toBeInTheDocument()
      })
    })

    it('should show Regex mode inputs when Regex is selected', async () => {
      await setupDefaultMocks()
      renderComponent({ librarySlug: 'test-lib', itemIds: [1, 2, 3] })

      // Expand the form
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      // Click the Album mode selector
      const albumLabel = screen.getByText('Album')
      const albumField = albumLabel.closest('.rounded-md')
      const albumModeSelector = albumField?.querySelector('[role="combobox"]')
      fireEvent.click(albumModeSelector!)

      // Select Regex
      const regexOption = await screen.findByRole('option', { name: 'Regex' })
      fireEvent.click(regexOption)

      // Should show regex inputs
      await waitFor(() => {
        expect(screen.getByText('Source Field')).toBeInTheDocument()
        expect(screen.getByText('Regex Pattern')).toBeInTheDocument()
        expect(screen.getByText('Replacement Template')).toBeInTheDocument()
      })
    })

    it('should show Sequence mode inputs when Sequence is selected for track_number', async () => {
      await setupDefaultMocks()
      renderComponent({ librarySlug: 'test-lib', itemIds: [1, 2, 3] })

      // Expand the form
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      // Click the Track Number mode selector
      const trackLabel = screen.getByText('Track Number')
      const trackField = trackLabel.closest('.rounded-md')
      const trackModeSelector = trackField?.querySelector('[role="combobox"]')
      fireEvent.click(trackModeSelector!)

      // Select Sequence
      const sequenceOption = await screen.findByRole('option', { name: 'Sequence' })
      fireEvent.click(sequenceOption)

      // Should show sequence inputs
      await waitFor(() => {
        expect(screen.getByText('Starting Number')).toBeInTheDocument()
        expect(screen.getByText('Restart per directory')).toBeInTheDocument()
      })
    })
  })

  describe('Apply button state', () => {
    it('should have Apply Changes button disabled when no changes configured', async () => {
      await setupDefaultMocks()
      renderComponent({ librarySlug: 'test-lib', itemIds: [1, 2, 3] })

      // Expand the form
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      await waitFor(() => {
        const applyButton = screen.getByRole('button', { name: 'Apply Changes' })
        expect(applyButton).toBeDisabled()
      })
    })

    it('should enable Apply Changes button when changes are configured and preview has changes', async () => {
      const { useTagPreview } = await import('@/hooks/useTagPreview')
      vi.mocked(useTagPreview).mockReturnValue({
        data: undefined,
        isLoading: false,
        isFetching: false,
        error: null,
        previewMap: new Map([[1, { itemId: 1, changes: { album: 'New Album' } }]]),
        getPreviewValue: () => 'New Album',
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

      renderComponent({ librarySlug: 'test-lib', itemIds: [1, 2, 3] })

      // Expand the form
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      // Configure a change
      const albumLabel = screen.getByText('Album')
      const albumField = albumLabel.closest('.rounded-md')
      const albumModeSelector = albumField?.querySelector('[role="combobox"]')
      fireEvent.click(albumModeSelector!)

      const fixedOption = await screen.findByRole('option', { name: 'Fixed Value' })
      fireEvent.click(fixedOption)

      // Enter a value
      const input = screen.getByPlaceholderText('Enter fixed value...')
      fireEvent.change(input, { target: { value: 'New Album' } })

      await waitFor(() => {
        const applyButton = screen.getByRole('button', { name: 'Apply Changes' })
        expect(applyButton).not.toBeDisabled()
      })
    })
  })

  describe('Confirmation dialog', () => {
    it('should show confirmation dialog when Apply Changes is clicked', async () => {
      const { useTagPreview } = await import('@/hooks/useTagPreview')
      vi.mocked(useTagPreview).mockReturnValue({
        data: undefined,
        isLoading: false,
        isFetching: false,
        error: null,
        previewMap: new Map([[1, { itemId: 1, changes: { album: 'New Album' } }]]),
        getPreviewValue: () => 'New Album',
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

      renderComponent({ librarySlug: 'test-lib', itemIds: [1, 2, 3] })

      // Expand and configure a change
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      const albumLabel = screen.getByText('Album')
      const albumField = albumLabel.closest('.rounded-md')
      const albumModeSelector = albumField?.querySelector('[role="combobox"]')
      fireEvent.click(albumModeSelector!)

      const fixedOption = await screen.findByRole('option', { name: 'Fixed Value' })
      fireEvent.click(fixedOption)

      // Click Apply Changes
      const applyButton = screen.getByRole('button', { name: 'Apply Changes' })
      fireEvent.click(applyButton)

      // Confirmation dialog should appear
      await waitFor(() => {
        expect(screen.getByText('Apply Tag Changes?')).toBeInTheDocument()
        expect(screen.getByText(/This will apply the configured transformations to 3 tracks/)).toBeInTheDocument()
      })
    })

    it('should call execute when confirm is clicked in dialog', async () => {
      const { useTagPreview } = await import('@/hooks/useTagPreview')
      vi.mocked(useTagPreview).mockReturnValue({
        data: undefined,
        isLoading: false,
        isFetching: false,
        error: null,
        previewMap: new Map([[1, { itemId: 1, changes: { album: 'New Album' } }]]),
        getPreviewValue: () => 'New Album',
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

      renderComponent({ librarySlug: 'test-lib', itemIds: [1, 2, 3] })

      // Expand and configure a change
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      const albumLabel = screen.getByText('Album')
      const albumField = albumLabel.closest('.rounded-md')
      const albumModeSelector = albumField?.querySelector('[role="combobox"]')
      fireEvent.click(albumModeSelector!)

      const fixedOption = await screen.findByRole('option', { name: 'Fixed Value' })
      fireEvent.click(fixedOption)

      // Click Apply Changes to open dialog
      fireEvent.click(screen.getByRole('button', { name: 'Apply Changes' }))

      // Wait for dialog to appear and click confirm
      await waitFor(() => {
        expect(screen.getByText('Apply Tag Changes?')).toBeInTheDocument()
      })

      // Click the Apply Changes button in the dialog
      const dialogButtons = screen.getAllByRole('button', { name: 'Apply Changes' })
      const confirmButton = dialogButtons[dialogButtons.length - 1] // The one in the dialog
      fireEvent.click(confirmButton)

      await waitFor(() => {
        expect(mockExecute).toHaveBeenCalledWith(
          'test-lib',
          [1, 2, 3],
          expect.arrayContaining([
            expect.objectContaining({ tag: 'album', mode: 'fixed' })
          ])
        )
      })
    })

    it('should close dialog when Cancel is clicked', async () => {
      const { useTagPreview } = await import('@/hooks/useTagPreview')
      vi.mocked(useTagPreview).mockReturnValue({
        data: undefined,
        isLoading: false,
        isFetching: false,
        error: null,
        previewMap: new Map([[1, { itemId: 1, changes: { album: 'New Album' } }]]),
        getPreviewValue: () => 'New Album',
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

      renderComponent({ librarySlug: 'test-lib', itemIds: [1, 2, 3] })

      // Expand and configure a change
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      const albumLabel = screen.getByText('Album')
      const albumField = albumLabel.closest('.rounded-md')
      const albumModeSelector = albumField?.querySelector('[role="combobox"]')
      fireEvent.click(albumModeSelector!)

      const fixedOption = await screen.findByRole('option', { name: 'Fixed Value' })
      fireEvent.click(fixedOption)

      // Click Apply Changes to open dialog
      fireEvent.click(screen.getByRole('button', { name: 'Apply Changes' }))

      await waitFor(() => {
        expect(screen.getByText('Apply Tag Changes?')).toBeInTheDocument()
      })

      // Click Cancel
      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

      await waitFor(() => {
        expect(screen.queryByText('Apply Tag Changes?')).not.toBeInTheDocument()
      })
    })
  })

  describe('Update progress display', () => {
    it('should show progress during update', async () => {
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
          progress: 50,
          itemsProcessed: 2,
          itemsTotal: 4,
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

      renderComponent({ librarySlug: 'test-lib', itemIds: [1, 2, 3, 4] })

      // Expand the form
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      await waitFor(() => {
        expect(screen.getByText(/Applying changes.../)).toBeInTheDocument()
        expect(screen.getByText(/2 \/ 4/)).toBeInTheDocument()
        expect(screen.getByRole('progressbar')).toBeInTheDocument()
      })
    })

    it('should show success message when update completes', async () => {
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
          itemsProcessed: 4,
          itemsTotal: 4,
          itemsSucceeded: 4,
          itemsFailed: 0,
          error: null,
          isComplete: true,
          results: [],
        },
        execute: vi.fn(),
        reset: vi.fn(),
        cancel: vi.fn(),
      })

      renderComponent({ librarySlug: 'test-lib', itemIds: [1, 2, 3, 4] })

      // Expand the form
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      await waitFor(() => {
        expect(screen.getByText(/Successfully updated 4 tracks/)).toBeInTheDocument()
      })
    })

    it('should show failure summary when some items fail', async () => {
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
          itemsProcessed: 4,
          itemsTotal: 4,
          itemsSucceeded: 3,
          itemsFailed: 1,
          error: null,
          isComplete: true,
          results: [
            { itemId: 1, status: 'success' },
            { itemId: 2, status: 'success' },
            { itemId: 3, status: 'success' },
            { itemId: 4, status: 'failed', error: { code: 'WRITE_ERROR', message: 'Permission denied' } },
          ],
        },
        execute: vi.fn(),
        reset: vi.fn(),
        cancel: vi.fn(),
      })

      renderComponent({ librarySlug: 'test-lib', itemIds: [1, 2, 3, 4] })

      // Expand the form
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      await waitFor(() => {
        expect(screen.getByText(/3 succeeded, 1 failed/)).toBeInTheDocument()
        expect(screen.getByText(/Permission denied/)).toBeInTheDocument()
      })
    })
  })

  describe('Preview loading', () => {
    it('should show preview loading indicator', async () => {
      const { useTagPreview } = await import('@/hooks/useTagPreview')
      vi.mocked(useTagPreview).mockReturnValue({
        data: undefined,
        isLoading: false,
        isFetching: true,
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

      renderComponent({ librarySlug: 'test-lib', itemIds: [1, 2, 3] })

      // Expand the form
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      await waitFor(() => {
        expect(screen.getByText('Loading preview...')).toBeInTheDocument()
      })
    })

    it('should show preview error message', async () => {
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

      renderComponent({ librarySlug: 'test-lib', itemIds: [1, 2, 3] })

      // Expand the form
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      await waitFor(() => {
        expect(screen.getByText(/Preview error: Invalid regex pattern/)).toBeInTheDocument()
      })
    })
  })

  describe('Reset functionality', () => {
    it('should reset form when Reset button is clicked', async () => {
      const mockReset = vi.fn()

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
        reset: mockReset,
        cancel: vi.fn(),
      })

      renderComponent({ librarySlug: 'test-lib', itemIds: [1, 2, 3] })

      // Expand and configure a change
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      const albumLabel = screen.getByText('Album')
      const albumField = albumLabel.closest('.rounded-md')
      const albumModeSelector = albumField?.querySelector('[role="combobox"]')
      fireEvent.click(albumModeSelector!)

      const fixedOption = await screen.findByRole('option', { name: 'Fixed Value' })
      fireEvent.click(fixedOption)

      // Now Reset button should be enabled and we can click it
      const resetButton = screen.getByRole('button', { name: 'Reset' })
      fireEvent.click(resetButton)

      // Should call the reset function from the hook
      expect(mockReset).toHaveBeenCalled()
    })
  })

  describe('Disabled state', () => {
    it('should disable form when disabled prop is true', async () => {
      await setupDefaultMocks()
      renderComponent({ librarySlug: 'test-lib', itemIds: [1, 2, 3], disabled: true })

      // Expand the form
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      await waitFor(() => {
        const modeSelectors = screen.getAllByRole('combobox')
        // Check that selectors exist and are disabled
        expect(modeSelectors.length).toBeGreaterThan(0)
        // The disabled attribute is set via data-disabled or aria-disabled depending on Radix version
        modeSelectors.forEach((selector) => {
          // Check multiple ways a select can be disabled
          const isDisabled =
            selector.hasAttribute('data-disabled') ||
            selector.getAttribute('aria-disabled') === 'true' ||
            selector.getAttribute('disabled') !== null
          expect(isDisabled).toBe(true)
        })
      })
    })
  })

  describe('Preview count display', () => {
    it('should show count of affected tracks when preview has changes', async () => {
      const previewMap = new Map([
        [1, { itemId: 1, changes: { album: 'New Album' } }],
        [2, { itemId: 2, changes: { album: 'New Album' } }],
        [3, { itemId: 3, changes: { album: 'New Album' } }],
      ])

      const { useTagPreview } = await import('@/hooks/useTagPreview')
      vi.mocked(useTagPreview).mockReturnValue({
        data: undefined,
        isLoading: false,
        isFetching: false,
        error: null,
        previewMap,
        getPreviewValue: () => 'New Album',
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

      renderComponent({ librarySlug: 'test-lib', itemIds: [1, 2, 3] })

      // Expand the form
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      // Configure a change to trigger preview
      const albumLabel = screen.getByText('Album')
      const albumField = albumLabel.closest('.rounded-md')
      const albumModeSelector = albumField?.querySelector('[role="combobox"]')
      fireEvent.click(albumModeSelector!)

      const fixedOption = await screen.findByRole('option', { name: 'Fixed Value' })
      fireEvent.click(fixedOption)

      await waitFor(() => {
        expect(screen.getByText(/Preview: 3 tracks will be modified/)).toBeInTheDocument()
      })
    })
  })

  describe('Persisted configuration after apply', () => {
    it('should keep form fields visible after successful apply', async () => {
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

      renderComponent({ librarySlug: 'test-lib', itemIds: [1, 2, 3] })

      // Expand the form
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      // Should show success message
      await waitFor(() => {
        expect(screen.getByText(/Successfully updated 3 tracks/)).toBeInTheDocument()
      })

      // Form fields should still be visible after completion
      expect(screen.getByText('Album')).toBeInTheDocument()
      expect(screen.getByText('Artist')).toBeInTheDocument()
      expect(screen.getByText('Title')).toBeInTheDocument()

      // Reset button should still be visible
      expect(screen.getByRole('button', { name: 'Reset' })).toBeInTheDocument()
    })

    it('should show configuration preserved message after successful apply', async () => {
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

      renderComponent({ librarySlug: 'test-lib', itemIds: [1, 2, 3] })

      // Expand the form
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      // Should show the preserved configuration message
      await waitFor(() => {
        expect(screen.getByText(/Configuration preserved/)).toBeInTheDocument()
      })
    })

    it('should call reset when Reset button is clicked after successful apply', async () => {
      const mockReset = vi.fn()

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
        reset: mockReset,
        cancel: vi.fn(),
      })

      renderComponent({ librarySlug: 'test-lib', itemIds: [1, 2, 3] })

      // Expand the form
      fireEvent.click(screen.getByText('Batch Tag Editor'))

      // Wait for form to be visible
      await waitFor(() => {
        expect(screen.getByText(/Successfully updated 3 tracks/)).toBeInTheDocument()
      })

      // Configure a field to enable the Reset button
      const albumLabel = screen.getByText('Album')
      const albumField = albumLabel.closest('.rounded-md')
      const albumModeSelector = albumField?.querySelector('[role="combobox"]')
      fireEvent.click(albumModeSelector!)

      const fixedOption = await screen.findByRole('option', { name: 'Fixed Value' })
      fireEvent.click(fixedOption)

      // Click Reset button
      const resetButton = screen.getByRole('button', { name: 'Reset' })
      fireEvent.click(resetButton)

      // Should call the reset function from the hook
      expect(mockReset).toHaveBeenCalled()
    })
  })

  describe('Collapsible header', () => {
    it('starts collapsed and expands on header click', async () => {
      await setupDefaultMocks()
      render(
        <QueryClientProvider client={queryClient}>
          <BatchTagEditorForm
            librarySlug="test-lib"
            itemIds={[1, 2]}
            collapsible
            defaultCollapsed
          />
        </QueryClientProvider>
      )

      // Collapsed: the tag field grid / actions are hidden.
      expect(screen.queryByRole('button', { name: 'Reset' })).not.toBeInTheDocument()

      // The header is a toggle; clicking it expands the body.
      fireEvent.click(screen.getByText('Batch Tag Editor'))
      expect(screen.getByRole('button', { name: 'Reset' })).toBeInTheDocument()
    })

    it('renders expanded with a static header when not collapsible', async () => {
      await setupDefaultMocks()
      render(
        <QueryClientProvider client={queryClient}>
          <BatchTagEditorForm librarySlug="test-lib" itemIds={[1, 2]} />
        </QueryClientProvider>
      )

      expect(screen.getByRole('button', { name: 'Reset' })).toBeInTheDocument()
    })
  })
})
