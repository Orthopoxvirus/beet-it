import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createRef } from 'react'
import FileDropZone, { type FileDropZoneHandle } from './FileDropZone'

// ============================================================================
// Mock XMLHttpRequest
// ============================================================================

interface MockXMLHttpRequestInstance {
  url: string
  method: string
  timeout: number
  readyState: number
  status: number
  responseText: string
  upload: {
    listeners: Map<string, ((event: ProgressEvent) => void)[]>
    addEventListener: (type: string, listener: (event: ProgressEvent) => void) => void
  }
  listeners: Map<string, ((event: Event) => void)[]>
  addEventListener: (type: string, listener: (event: Event) => void) => void
  open: (method: string, url: string) => void
  send: (body: FormData) => void
  abort: () => void
  sentBody: FormData | null
  simulateProgress: (loaded: number, total: number) => void
  simulateLoad: (status: number, responseText: string) => void
  simulateError: () => void
}

class MockXMLHttpRequest {
  static instances: MockXMLHttpRequestInstance[] = []
  static reset() {
    MockXMLHttpRequest.instances = []
  }
  static getLastInstance(): MockXMLHttpRequestInstance | undefined {
    return MockXMLHttpRequest.instances[MockXMLHttpRequest.instances.length - 1]
  }

  url = ''
  method = ''
  timeout = 0
  readyState = 0
  status = 0
  responseText = ''
  sentBody: FormData | null = null

  upload = {
    listeners: new Map<string, ((event: ProgressEvent) => void)[]>(),
    addEventListener(type: string, listener: (event: ProgressEvent) => void) {
      if (!this.listeners.has(type)) {
        this.listeners.set(type, [])
      }
      this.listeners.get(type)!.push(listener)
    },
  }

  listeners = new Map<string, ((event: Event) => void)[]>()

  constructor() {
    MockXMLHttpRequest.instances.push(this as unknown as MockXMLHttpRequestInstance)
  }

  addEventListener(type: string, listener: (event: Event) => void) {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, [])
    }
    this.listeners.get(type)!.push(listener)
  }

  open(method: string, url: string) {
    this.method = method
    this.url = url
    this.readyState = 1
  }

  send(body: FormData) {
    this.sentBody = body
    this.readyState = 2
  }

  abort() {
    this.readyState = 0
  }

  simulateProgress(loaded: number, total: number) {
    const event = new ProgressEvent('progress', {
      lengthComputable: true,
      loaded,
      total,
    })
    const listeners = this.upload.listeners.get('progress') || []
    listeners.forEach((listener) => listener(event))
  }

  simulateLoad(status: number, responseText: string) {
    this.status = status
    this.responseText = responseText
    this.readyState = 4
    const listeners = this.listeners.get('load') || []
    listeners.forEach((listener) => listener(new Event('load')))
  }

  simulateError() {
    const listeners = this.listeners.get('error') || []
    listeners.forEach((listener) => listener(new Event('error')))
  }
}

const originalXHR = global.XMLHttpRequest

beforeEach(() => {
  MockXMLHttpRequest.reset()
  ;(global as unknown as { XMLHttpRequest: typeof MockXMLHttpRequest }).XMLHttpRequest =
    MockXMLHttpRequest
})

afterEach(() => {
  global.XMLHttpRequest = originalXHR
})

// ============================================================================
// Test Helpers
// ============================================================================

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
}

function renderComponent(props: Partial<React.ComponentProps<typeof FileDropZone>> = {}) {
  const Wrapper = createWrapper()
  return render(
    <Wrapper>
      <FileDropZone librarySlug="test-library" {...props} />
    </Wrapper>
  )
}

function createMockFile(name: string, size: number, type = 'audio/flac'): File {
  const content = new ArrayBuffer(size)
  return new File([content], name, { type })
}

// ============================================================================
// Tests
// ============================================================================

describe('FileDropZone', () => {
  describe('initial render', () => {
    it('should render drop zone with default text', () => {
      renderComponent()

      expect(screen.getByText('Drag and drop files or folders here')).toBeInTheDocument()
      expect(screen.getByText('or click to browse')).toBeInTheDocument()
    })

    it('should render file and folder selection buttons', () => {
      renderComponent()

      expect(screen.getByRole('button', { name: /select files/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /select folder/i })).toBeInTheDocument()
    })

    it('should render hidden file inputs', () => {
      renderComponent()

      const fileInput = screen.getByLabelText('Select files')
      const folderInput = screen.getByLabelText('Select folder')

      expect(fileInput).toHaveClass('hidden')
      expect(folderInput).toHaveClass('hidden')
      expect(folderInput).toHaveAttribute('webkitdirectory')
    })
  })

  describe('drag state tracking', () => {
    it('should show drag-over state when files are dragged over', () => {
      renderComponent()

      const dropZone = screen
        .getByText('Drag and drop files or folders here')
        .closest('div[class*="border-dashed"]')
      expect(dropZone).toBeDefined()

      // Simulate drag enter with a simple event
      fireEvent.dragEnter(dropZone!, {
        dataTransfer: { items: [{ kind: 'file' }] },
      })

      expect(screen.getByText('Drop files here')).toBeInTheDocument()
    })

    it('should remove drag-over state when drag leaves', async () => {
      renderComponent()

      const dropZone = screen
        .getByText('Drag and drop files or folders here')
        .closest('div[class*="border-dashed"]')

      // Simulate drag enter
      fireEvent.dragEnter(dropZone!, {
        dataTransfer: { items: [{ kind: 'file' }] },
      })
      expect(screen.getByText('Drop files here')).toBeInTheDocument()

      // Simulate drag leave — the component debounces leave by 50ms to absorb
      // enter/leave flickers when dragging across child elements, so wait for it.
      fireEvent.dragLeave(dropZone!)

      await waitFor(() => {
        expect(
          screen.getByText('Drag and drop files or folders here')
        ).toBeInTheDocument()
      })
    })
  })

  describe('click-to-browse behavior', () => {
    it('should trigger file input when Select Files button is clicked', () => {
      renderComponent()

      const fileInput = screen.getByLabelText('Select files') as HTMLInputElement
      const clickSpy = vi.spyOn(fileInput, 'click')

      const selectFilesButton = screen.getByRole('button', { name: /select files/i })
      fireEvent.click(selectFilesButton)

      expect(clickSpy).toHaveBeenCalled()
    })

    it('should trigger folder input when Select Folder button is clicked', () => {
      renderComponent()

      const folderInput = screen.getByLabelText('Select folder') as HTMLInputElement
      const clickSpy = vi.spyOn(folderInput, 'click')

      const selectFolderButton = screen.getByRole('button', { name: /select folder/i })
      fireEvent.click(selectFolderButton)

      expect(clickSpy).toHaveBeenCalled()
    })

    it('should start upload when files are selected via input', async () => {
      renderComponent()

      const fileInput = screen.getByLabelText('Select files')
      const file = createMockFile('track.flac', 1000)

      // Create a new FileList-like object
      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })

      await act(async () => {
        fireEvent.change(fileInput)
      })

      // Upload should start
      expect(screen.getByText(/uploading 1 file/i)).toBeInTheDocument()

      const xhr = MockXMLHttpRequest.getLastInstance()
      expect(xhr).toBeDefined()
      expect(xhr!.url).toContain('/api/v1/libraries/test-library/upload')
    })
  })

  describe('upload progress display', () => {
    it('should show uploading state with progress', async () => {
      renderComponent()

      const fileInput = screen.getByLabelText('Select files')
      const file = createMockFile('track.flac', 1000)

      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })

      await act(async () => {
        fireEvent.change(fileInput)
      })

      expect(screen.getByText(/uploading 1 file/i)).toBeInTheDocument()

      const xhr = MockXMLHttpRequest.getLastInstance()

      // Simulate progress
      await act(async () => {
        xhr!.simulateProgress(500, 1000)
      })

      expect(screen.getByText('50%')).toBeInTheDocument()
    })

    it('should show progress bar during upload', async () => {
      renderComponent()

      const fileInput = screen.getByLabelText('Select files')
      const file = createMockFile('track.flac', 1000)

      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })

      await act(async () => {
        fireEvent.change(fileInput)
      })

      const progressBar = screen.getByRole('progressbar')
      expect(progressBar).toBeInTheDocument()
    })

    it('should show file size information during upload', async () => {
      renderComponent()

      const fileInput = screen.getByLabelText('Select files')
      const file = createMockFile('track.flac', 1024 * 1024) // 1 MB

      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })

      await act(async () => {
        fireEvent.change(fileInput)
      })

      // Should show formatted byte sizes
      expect(screen.getByText(/1(\.\d)?\s*MB/i)).toBeInTheDocument()
    })
  })

  describe('success notification', () => {
    it('should show success notification on successful upload', async () => {
      const onUploadSuccess = vi.fn()
      renderComponent({ onUploadSuccess })

      const fileInput = screen.getByLabelText('Select files')
      const file = createMockFile('track.flac', 1000)

      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })

      await act(async () => {
        fireEvent.change(fileInput)
      })

      const xhr = MockXMLHttpRequest.getLastInstance()

      // Simulate successful upload
      await act(async () => {
        xhr!.simulateLoad(
          200,
          JSON.stringify({
            status: 'success',
            message: 'Successfully uploaded 1 file',
            files_uploaded: 1,
            files: [{ filename: 'track.flac', path: 'track.flac', size_bytes: 1000 }],
          })
        )
      })

      expect(screen.getByText('Successfully uploaded 1 file')).toBeInTheDocument()
      expect(onUploadSuccess).toHaveBeenCalled()
    })

    it('should auto-dismiss success notification after timeout', async () => {
      vi.useFakeTimers()
      renderComponent()

      const fileInput = screen.getByLabelText('Select files')
      const file = createMockFile('track.flac', 1000)

      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })

      await act(async () => {
        fireEvent.change(fileInput)
      })

      const xhr = MockXMLHttpRequest.getLastInstance()

      await act(async () => {
        xhr!.simulateLoad(
          200,
          JSON.stringify({
            status: 'success',
            message: 'Successfully uploaded 1 file',
            files_uploaded: 1,
            files: [{ filename: 'track.flac', path: 'track.flac', size_bytes: 1000 }],
          })
        )
      })

      expect(screen.getByText('Successfully uploaded 1 file')).toBeInTheDocument()

      // Advance timers
      await act(async () => {
        vi.advanceTimersByTime(5000)
      })

      expect(screen.queryByText('Successfully uploaded 1 file')).not.toBeInTheDocument()
      vi.useRealTimers()
    })
  })

  describe('error notification', () => {
    it('should show error notification on upload failure', async () => {
      const onUploadError = vi.fn()
      renderComponent({ onUploadError })

      const fileInput = screen.getByLabelText('Select files')
      const file = createMockFile('track.flac', 1000)

      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })

      await act(async () => {
        fireEvent.change(fileInput)
      })

      const xhr = MockXMLHttpRequest.getLastInstance()

      // Simulate error
      await act(async () => {
        xhr!.simulateLoad(
          409,
          JSON.stringify({
            detail: {
              code: 'FILE_EXISTS',
              message: 'One or more files already exist at the destination',
            },
          })
        )
      })

      expect(
        screen.getByText('One or more files already exist at the destination')
      ).toBeInTheDocument()

      expect(onUploadError).toHaveBeenCalledWith(
        'One or more files already exist at the destination'
      )
    })

    it('should allow dismissing error notification', async () => {
      renderComponent()

      const fileInput = screen.getByLabelText('Select files')
      const file = createMockFile('track.flac', 1000)

      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })

      await act(async () => {
        fireEvent.change(fileInput)
      })

      const xhr = MockXMLHttpRequest.getLastInstance()

      await act(async () => {
        xhr!.simulateError()
      })

      expect(screen.getByText('Network error occurred during upload')).toBeInTheDocument()

      // Click dismiss button
      const dismissButton = screen.getByRole('button', { name: /dismiss/i })

      await act(async () => {
        fireEvent.click(dismissButton)
      })

      expect(screen.queryByText('Network error occurred during upload')).not.toBeInTheDocument()
    })
  })

  describe('multiple file upload', () => {
    it('should show correct file count for multiple files', async () => {
      renderComponent()

      const fileInput = screen.getByLabelText('Select files')
      const files = [
        createMockFile('track1.flac', 1000),
        createMockFile('track2.flac', 1000),
        createMockFile('track3.flac', 1000),
      ]

      Object.defineProperty(fileInput, 'files', {
        value: files,
        writable: false,
      })

      await act(async () => {
        fireEvent.change(fileInput)
      })

      expect(screen.getByText(/uploading 3 files/i)).toBeInTheDocument()
    })
  })

  describe('imperative uploadFiles handle', () => {
    it('uploads files pushed through the ref (e.g. from the full-page overlay)', async () => {
      const ref = createRef<FileDropZoneHandle>()
      const Wrapper = createWrapper()
      render(
        <Wrapper>
          <FileDropZone ref={ref} librarySlug="test-library" />
        </Wrapper>
      )

      const file = createMockFile('dropped.flac', 1000)
      await act(async () => {
        ref.current!.uploadFiles([file])
      })

      // Routing through the shared pipeline shows the in-card uploading state…
      expect(screen.getByText(/uploading 1 file/i)).toBeInTheDocument()
      // …and actually dispatches the request.
      const xhr = MockXMLHttpRequest.getLastInstance()
      expect(xhr?.sentBody).not.toBeNull()
    })

    it('ignores an empty file list', async () => {
      const ref = createRef<FileDropZoneHandle>()
      const Wrapper = createWrapper()
      render(
        <Wrapper>
          <FileDropZone ref={ref} librarySlug="test-library" />
        </Wrapper>
      )

      await act(async () => {
        ref.current!.uploadFiles([])
      })

      expect(screen.queryByText(/uploading/i)).not.toBeInTheDocument()
      expect(MockXMLHttpRequest.getLastInstance()).toBeUndefined()
    })
  })
})
