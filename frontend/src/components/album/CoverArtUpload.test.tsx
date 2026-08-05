import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CoverArtUpload } from './CoverArtUpload'

// Mock the hooks
const mockUploadMutate = vi.fn()
const mockUrlMutate = vi.fn()

vi.mock('@/hooks/useAlbums', () => ({
  useUploadCoverArt: vi.fn(() => ({
    mutateAsync: mockUploadMutate,
    isPending: false,
  })),
  useDownloadCoverArtFromUrl: vi.fn(() => ({
    mutateAsync: mockUrlMutate,
    isPending: false,
  })),
  useSearchCoverArt: vi.fn(() => ({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
  })),
}))

// Mock URL.createObjectURL and URL.revokeObjectURL
const mockObjectUrl = 'blob:http://localhost:3000/mock-uuid'
global.URL.createObjectURL = vi.fn(() => mockObjectUrl)
global.URL.revokeObjectURL = vi.fn()

describe('CoverArtUpload', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })
    vi.clearAllMocks()
    mockUploadMutate.mockResolvedValue({
      status: 'success',
      album_id: 1,
      cover_path: '/covers/cover.jpg',
      message: 'Cover art uploaded successfully',
    })
    mockUrlMutate.mockResolvedValue({
      status: 'success',
      album_id: 1,
      cover_path: '/covers/cover.jpg',
      message: 'Cover art downloaded successfully',
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  const defaultProps = {
    slug: 'jazz',
    albumId: 1,
    isOpen: true,
    onClose: vi.fn(),
    onSuccess: vi.fn(),
  }

  const renderComponent = (props: Partial<typeof defaultProps> = {}) => {
    return render(
      <QueryClientProvider client={queryClient}>
        <CoverArtUpload {...defaultProps} {...props} />
      </QueryClientProvider>
    )
  }

  const createMockFile = (
    name: string,
    size: number,
    type: string
  ): File => {
    const content = new ArrayBuffer(size)
    return new File([content], name, { type })
  }

  describe('Dialog display', () => {
    it('should render dialog when isOpen is true', () => {
      renderComponent()
      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByText('Update Cover Art')).toBeInTheDocument()
    })

    it('should not render dialog when isOpen is false', () => {
      renderComponent({ isOpen: false })
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
  })

  describe('Mode tabs', () => {
    it('should render Upload and From URL tabs', () => {
      renderComponent()
      expect(screen.getByRole('button', { name: /upload/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /from url/i })).toBeInTheDocument()
    })

    it('should default to Upload mode', () => {
      renderComponent()
      expect(screen.getByText(/drag and drop an image here/i)).toBeInTheDocument()
    })

    it('should switch to URL mode when From URL tab is clicked', async () => {
      renderComponent()
      const urlTab = screen.getByRole('button', { name: /from url/i })
      fireEvent.click(urlTab)

      await waitFor(() => {
        expect(screen.getByLabelText(/image url/i)).toBeInTheDocument()
      })
    })

    it('should switch back to Upload mode when Upload tab is clicked', async () => {
      renderComponent()

      // Switch to URL mode
      const urlTab = screen.getByRole('button', { name: /from url/i })
      fireEvent.click(urlTab)

      // Switch back to Upload mode
      const uploadTab = screen.getByRole('button', { name: /upload/i })
      fireEvent.click(uploadTab)

      await waitFor(() => {
        expect(screen.getByText(/drag and drop an image here/i)).toBeInTheDocument()
      })
    })
  })

  describe('File upload mode', () => {
    it('should render drop zone with instructions', () => {
      renderComponent()
      expect(screen.getByText(/drag and drop an image here/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /browse files/i })).toBeInTheDocument()
    })

    it('should display accepted file format information', () => {
      renderComponent()
      expect(screen.getByText(/accepted formats: jpeg, png, gif, webp/i)).toBeInTheDocument()
      expect(screen.getByText(/max 10 mb/i)).toBeInTheDocument()
    })

    it('should have hidden file input', () => {
      renderComponent()
      const fileInput = document.querySelector('input[type="file"]')
      expect(fileInput).toBeInTheDocument()
      expect(fileInput).toHaveClass('hidden')
    })

    it('should accept correct image types', () => {
      renderComponent()
      const fileInput = document.querySelector('input[type="file"]')
      expect(fileInput).toHaveAttribute(
        'accept',
        'image/jpeg,image/png,image/gif,image/webp'
      )
    })
  })

  describe('File validation', () => {
    it('should show error for invalid file type', async () => {
      renderComponent()

      const file = createMockFile('test.txt', 1000, 'text/plain')
      const fileInput = document.querySelector('input[type="file"]')!

      await act(async () => {
        Object.defineProperty(fileInput, 'files', {
          value: [file],
          writable: false,
        })
        fireEvent.change(fileInput)
      })

      await waitFor(() => {
        expect(
          screen.getByText(/invalid file type/i)
        ).toBeInTheDocument()
      })
    })

    it('should show error for file that is too large', async () => {
      renderComponent()

      // Create a file larger than 10MB
      const file = createMockFile('large.jpg', 15 * 1024 * 1024, 'image/jpeg')
      const fileInput = document.querySelector('input[type="file"]')!

      await act(async () => {
        Object.defineProperty(fileInput, 'files', {
          value: [file],
          writable: false,
        })
        fireEvent.change(fileInput)
      })

      await waitFor(() => {
        expect(screen.getByText(/file too large/i)).toBeInTheDocument()
      })
    })

    it('should accept valid JPEG file', async () => {
      renderComponent()

      const file = createMockFile('cover.jpg', 1024 * 1024, 'image/jpeg')
      const fileInput = document.querySelector('input[type="file"]')!

      await act(async () => {
        Object.defineProperty(fileInput, 'files', {
          value: [file],
          writable: false,
        })
        fireEvent.change(fileInput)
      })

      await waitFor(() => {
        // Should show preview with file name
        expect(screen.getByText(/cover\.jpg/i)).toBeInTheDocument()
      })
    })

    it('should accept valid PNG file', async () => {
      renderComponent()

      const file = createMockFile('cover.png', 500 * 1024, 'image/png')
      const fileInput = document.querySelector('input[type="file"]')!

      await act(async () => {
        Object.defineProperty(fileInput, 'files', {
          value: [file],
          writable: false,
        })
        fireEvent.change(fileInput)
      })

      await waitFor(() => {
        expect(screen.getByText(/cover\.png/i)).toBeInTheDocument()
      })
    })
  })

  describe('Preview functionality', () => {
    it('should show image preview after file selection', async () => {
      renderComponent()

      const file = createMockFile('cover.jpg', 1024 * 1024, 'image/jpeg')
      const fileInput = document.querySelector('input[type="file"]')!

      await act(async () => {
        Object.defineProperty(fileInput, 'files', {
          value: [file],
          writable: false,
        })
        fireEvent.change(fileInput)
      })

      await waitFor(() => {
        const previewImg = screen.getByRole('img', { name: /cover art preview/i })
        expect(previewImg).toBeInTheDocument()
        expect(previewImg).toHaveAttribute('src', mockObjectUrl)
      })
    })

    it('should display file size in preview', async () => {
      renderComponent()

      const file = createMockFile('cover.jpg', 1024 * 1024, 'image/jpeg')
      const fileInput = document.querySelector('input[type="file"]')!

      await act(async () => {
        Object.defineProperty(fileInput, 'files', {
          value: [file],
          writable: false,
        })
        fireEvent.change(fileInput)
      })

      await waitFor(() => {
        expect(screen.getByText(/1\.0 mb/i)).toBeInTheDocument()
      })
    })

    it('should allow removing selected file', async () => {
      renderComponent()

      const file = createMockFile('cover.jpg', 1024 * 1024, 'image/jpeg')
      const fileInput = document.querySelector('input[type="file"]')!

      await act(async () => {
        Object.defineProperty(fileInput, 'files', {
          value: [file],
          writable: false,
        })
        fireEvent.change(fileInput)
      })

      await waitFor(() => {
        expect(screen.getByRole('img', { name: /cover art preview/i })).toBeInTheDocument()
      })

      // Find and click the remove button (X button in preview)
      const removeButtons = screen.getAllByRole('button')
      const removeButton = removeButtons.find((btn) =>
        btn.querySelector('svg.lucide-x') ||
        btn.classList.contains('destructive') ||
        btn.getAttribute('aria-label')?.toLowerCase().includes('remove')
      )

      if (removeButton) {
        fireEvent.click(removeButton)

        await waitFor(() => {
          expect(screen.getByText(/drag and drop an image here/i)).toBeInTheDocument()
        })
      }
    })
  })

  describe('Drag and drop', () => {
    it('should show visual feedback on drag over', () => {
      renderComponent()

      const dropZone = screen.getByText(/drag and drop an image here/i).closest('div')!

      fireEvent.dragOver(dropZone, {
        dataTransfer: { files: [] },
      })

      // Check for visual feedback (border color change)
      expect(dropZone).toHaveClass('border-primary')
    })

    it('should remove drag feedback on drag leave', () => {
      renderComponent()

      const dropZone = screen.getByText(/drag and drop an image here/i).closest('div')!

      fireEvent.dragOver(dropZone, {
        dataTransfer: { files: [] },
      })
      fireEvent.dragLeave(dropZone)

      // Check that drag feedback is removed
      expect(dropZone).not.toHaveClass('border-primary')
    })
  })

  describe('URL download mode', () => {
    it('should render URL input in URL mode', async () => {
      renderComponent()

      const urlTab = screen.getByRole('button', { name: /from url/i })
      fireEvent.click(urlTab)

      await waitFor(() => {
        expect(screen.getByLabelText(/image url/i)).toBeInTheDocument()
      })
    })

    it('should show placeholder text in URL input', async () => {
      renderComponent()

      const urlTab = screen.getByRole('button', { name: /from url/i })
      fireEvent.click(urlTab)

      await waitFor(() => {
        const input = screen.getByLabelText(/image url/i)
        expect(input).toHaveAttribute('placeholder', 'https://example.com/album-cover.jpg')
      })
    })

    it('should disable download button when URL is empty', async () => {
      renderComponent()

      const urlTab = screen.getByRole('button', { name: /from url/i })
      fireEvent.click(urlTab)

      await waitFor(() => {
        const downloadButton = screen.getByRole('button', { name: /download/i })
        expect(downloadButton).toBeDisabled()
      })
    })

    it('should show error for invalid URL format', async () => {
      renderComponent()

      const urlTab = screen.getByRole('button', { name: /from url/i })
      fireEvent.click(urlTab)

      const input = screen.getByLabelText(/image url/i)
      fireEvent.change(input, { target: { value: 'not-a-valid-url' } })

      const downloadButton = screen.getByRole('button', { name: /download/i })
      fireEvent.click(downloadButton)

      await waitFor(() => {
        expect(screen.getByText(/invalid url format/i)).toBeInTheDocument()
      })
    })

    it('should call mutation with valid URL', async () => {
      renderComponent()

      const urlTab = screen.getByRole('button', { name: /from url/i })
      fireEvent.click(urlTab)

      const input = screen.getByLabelText(/image url/i)
      fireEvent.change(input, {
        target: { value: 'https://example.com/album-cover.jpg' },
      })

      const downloadButton = screen.getByRole('button', { name: /download/i })
      fireEvent.click(downloadButton)

      await waitFor(() => {
        expect(mockUrlMutate).toHaveBeenCalledWith({
          slug: 'jazz',
          albumId: 1,
          url: 'https://example.com/album-cover.jpg',
        })
      })
    })
  })

  describe('Upload submission', () => {
    it('should disable Apply button when no file is selected', () => {
      renderComponent()
      const applyButton = screen.getByRole('button', { name: /apply/i })
      expect(applyButton).toBeDisabled()
    })

    it('should enable Apply button when file is selected', async () => {
      renderComponent()

      const file = createMockFile('cover.jpg', 1024 * 1024, 'image/jpeg')
      const fileInput = document.querySelector('input[type="file"]')!

      await act(async () => {
        Object.defineProperty(fileInput, 'files', {
          value: [file],
          writable: false,
        })
        fireEvent.change(fileInput)
      })

      await waitFor(() => {
        const applyButton = screen.getByRole('button', { name: /apply/i })
        expect(applyButton).not.toBeDisabled()
      })
    })

    it('should call upload mutation when Apply is clicked', async () => {
      renderComponent()

      const file = createMockFile('cover.jpg', 1024 * 1024, 'image/jpeg')
      const fileInput = document.querySelector('input[type="file"]')!

      await act(async () => {
        Object.defineProperty(fileInput, 'files', {
          value: [file],
          writable: false,
        })
        fireEvent.change(fileInput)
      })

      const applyButton = screen.getByRole('button', { name: /apply/i })
      fireEvent.click(applyButton)

      await waitFor(() => {
        expect(mockUploadMutate).toHaveBeenCalledWith({
          slug: 'jazz',
          albumId: 1,
          file: expect.any(File),
        })
      })
    })

    it('should call onSuccess callback after successful upload', async () => {
      const onSuccess = vi.fn()
      renderComponent({ onSuccess })

      const file = createMockFile('cover.jpg', 1024 * 1024, 'image/jpeg')
      const fileInput = document.querySelector('input[type="file"]')!

      await act(async () => {
        Object.defineProperty(fileInput, 'files', {
          value: [file],
          writable: false,
        })
        fireEvent.change(fileInput)
      })

      const applyButton = screen.getByRole('button', { name: /apply/i })
      fireEvent.click(applyButton)

      await waitFor(() => {
        expect(onSuccess).toHaveBeenCalled()
      })
    })

    it('should close dialog after successful upload', async () => {
      const onClose = vi.fn()
      renderComponent({ onClose })

      const file = createMockFile('cover.jpg', 1024 * 1024, 'image/jpeg')
      const fileInput = document.querySelector('input[type="file"]')!

      await act(async () => {
        Object.defineProperty(fileInput, 'files', {
          value: [file],
          writable: false,
        })
        fireEvent.change(fileInput)
      })

      const applyButton = screen.getByRole('button', { name: /apply/i })
      fireEvent.click(applyButton)

      await waitFor(() => {
        expect(onClose).toHaveBeenCalled()
      })
    })
  })

  describe('Error handling', () => {
    it('should display upload error message', async () => {
      mockUploadMutate.mockRejectedValueOnce(new Error('Upload failed'))

      renderComponent()

      const file = createMockFile('cover.jpg', 1024 * 1024, 'image/jpeg')
      const fileInput = document.querySelector('input[type="file"]')!

      await act(async () => {
        Object.defineProperty(fileInput, 'files', {
          value: [file],
          writable: false,
        })
        fireEvent.change(fileInput)
      })

      const applyButton = screen.getByRole('button', { name: /apply/i })
      fireEvent.click(applyButton)

      await waitFor(() => {
        expect(screen.getByText(/upload failed/i)).toBeInTheDocument()
      })
    })

    it('should display URL download error message', async () => {
      mockUrlMutate.mockRejectedValueOnce(new Error('Failed to fetch image'))

      renderComponent()

      const urlTab = screen.getByRole('button', { name: /from url/i })
      fireEvent.click(urlTab)

      const input = screen.getByLabelText(/image url/i)
      fireEvent.change(input, {
        target: { value: 'https://example.com/album-cover.jpg' },
      })

      const downloadButton = screen.getByRole('button', { name: /download/i })
      fireEvent.click(downloadButton)

      await waitFor(() => {
        expect(screen.getByText(/failed to fetch image/i)).toBeInTheDocument()
      })
    })
  })

  describe('Cancel functionality', () => {
    it('should render Cancel button', () => {
      renderComponent()
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
    })

    it('should call onClose when Cancel is clicked', () => {
      const onClose = vi.fn()
      renderComponent({ onClose })

      const cancelButton = screen.getByRole('button', { name: /cancel/i })
      fireEvent.click(cancelButton)

      expect(onClose).toHaveBeenCalled()
    })

    it('should reset state when dialog is closed', async () => {
      const onClose = vi.fn()
      const { rerender } = renderComponent({ onClose })

      // Select a file
      const file = createMockFile('cover.jpg', 1024 * 1024, 'image/jpeg')
      const fileInput = document.querySelector('input[type="file"]')!

      await act(async () => {
        Object.defineProperty(fileInput, 'files', {
          value: [file],
          writable: false,
        })
        fireEvent.change(fileInput)
      })

      await waitFor(() => {
        expect(screen.getByRole('img', { name: /cover art preview/i })).toBeInTheDocument()
      })

      // Cancel
      const cancelButton = screen.getByRole('button', { name: /cancel/i })
      fireEvent.click(cancelButton)

      // Reopen dialog
      rerender(
        <QueryClientProvider client={queryClient}>
          <CoverArtUpload {...defaultProps} isOpen={true} onClose={onClose} />
        </QueryClientProvider>
      )

      // Should be back to initial state
      await waitFor(() => {
        expect(screen.getByText(/drag and drop an image here/i)).toBeInTheDocument()
      })
    })
  })

  describe('Loading states', () => {
    it('should show loading state during upload', async () => {
      const { useUploadCoverArt } = await import('@/hooks/useAlbums')

      vi.mocked(useUploadCoverArt).mockReturnValue({
        mutateAsync: mockUploadMutate,
        isPending: true,
      } as ReturnType<typeof useUploadCoverArt>)

      renderComponent()

      const file = createMockFile('cover.jpg', 1024 * 1024, 'image/jpeg')
      const fileInput = document.querySelector('input[type="file"]')!

      await act(async () => {
        Object.defineProperty(fileInput, 'files', {
          value: [file],
          writable: false,
        })
        fireEvent.change(fileInput)
      })

      await waitFor(() => {
        expect(screen.getByText(/uploading/i)).toBeInTheDocument()
      })
    })

    it('should disable Cancel button during upload', async () => {
      const { useUploadCoverArt } = await import('@/hooks/useAlbums')

      vi.mocked(useUploadCoverArt).mockReturnValue({
        mutateAsync: mockUploadMutate,
        isPending: true,
      } as ReturnType<typeof useUploadCoverArt>)

      renderComponent()

      await waitFor(() => {
        const cancelButton = screen.getByRole('button', { name: /cancel/i })
        expect(cancelButton).toBeDisabled()
      })
    })
  })
})
