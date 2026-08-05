import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { useFileUpload } from './useFileUpload'

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
  simulateAbort: () => void
  simulateTimeout: () => void
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
    const listeners = this.listeners.get('abort') || []
    listeners.forEach((listener) => listener(new Event('abort')))
  }

  // Test helpers
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

  simulateAbort() {
    const listeners = this.listeners.get('abort') || []
    listeners.forEach((listener) => listener(new Event('abort')))
  }

  simulateTimeout() {
    const listeners = this.listeners.get('timeout') || []
    listeners.forEach((listener) => listener(new Event('timeout')))
  }
}

// Replace global XMLHttpRequest
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
    return React.createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

function createMockFile(name: string, size: number, type = 'audio/flac'): File {
  const content = new ArrayBuffer(size)
  return new File([content], name, { type })
}

function createMockFolderFile(name: string, relativePath: string, size = 1000): File {
  const content = new ArrayBuffer(size)
  const file = new File([content], name, { type: 'audio/flac' })
  Object.defineProperty(file, 'webkitRelativePath', {
    value: relativePath,
    writable: false,
  })
  return file
}

// ============================================================================
// Tests
// ============================================================================

describe('useFileUpload', () => {
  describe('initial state', () => {
    it('should return idle state initially', () => {
      const { result } = renderHook(() => useFileUpload(), {
        wrapper: createWrapper(),
      })

      expect(result.current.state).toEqual({
        status: 'idle',
        totalBytes: 0,
        uploadedBytes: 0,
        progress: 0,
        fileCount: 0,
        error: null,
      })
    })
  })

  describe('upload function', () => {
    it('should set error state when no files provided', () => {
      const onError = vi.fn()
      const { result } = renderHook(() => useFileUpload({ onError }), {
        wrapper: createWrapper(),
      })

      act(() => {
        result.current.upload('my-library', [])
      })

      expect(result.current.state.status).toBe('error')
      expect(result.current.state.error).toBe('No files selected')
      expect(onError).toHaveBeenCalledWith('No files selected')
    })

    it('should initiate upload with correct URL', () => {
      const { result } = renderHook(() => useFileUpload(), {
        wrapper: createWrapper(),
      })

      const file = createMockFile('track.flac', 1000)

      act(() => {
        result.current.upload('my-library', [file])
      })

      const xhr = MockXMLHttpRequest.getLastInstance()
      expect(xhr).toBeDefined()
      expect(xhr!.method).toBe('POST')
      expect(xhr!.url).toBe('/api/v1/libraries/my-library/upload')
    })

    it('should set uploading state and calculate total bytes', () => {
      const onStart = vi.fn()
      const { result } = renderHook(() => useFileUpload({ onStart }), {
        wrapper: createWrapper(),
      })

      const file1 = createMockFile('track1.flac', 1000)
      const file2 = createMockFile('track2.flac', 2000)

      act(() => {
        result.current.upload('my-library', [file1, file2])
      })

      expect(result.current.state.status).toBe('uploading')
      expect(result.current.state.totalBytes).toBe(3000)
      expect(result.current.state.fileCount).toBe(2)
      expect(result.current.state.uploadedBytes).toBe(0)
      expect(result.current.state.progress).toBe(0)
      expect(onStart).toHaveBeenCalled()
    })

    it('should send FormData with files and paths', () => {
      const { result } = renderHook(() => useFileUpload(), {
        wrapper: createWrapper(),
      })

      const file1 = createMockFolderFile('track1.flac', 'Album/track1.flac')
      const file2 = createMockFolderFile('track2.flac', 'Album/track2.flac')

      act(() => {
        result.current.upload('my-library', [file1, file2])
      })

      const xhr = MockXMLHttpRequest.getLastInstance()
      expect(xhr).toBeDefined()
      expect(xhr!.sentBody).toBeInstanceOf(FormData)

      // Check FormData contents
      const formData = xhr!.sentBody as FormData
      const files = formData.getAll('files')
      const pathsJson = formData.get('paths') as string

      expect(files).toHaveLength(2)
      expect(pathsJson).toBe(JSON.stringify(['Album/track1.flac', 'Album/track2.flac']))
    })

    it('should use filename as path when webkitRelativePath is empty', () => {
      const { result } = renderHook(() => useFileUpload(), {
        wrapper: createWrapper(),
      })

      const file = createMockFile('track.flac', 1000)

      act(() => {
        result.current.upload('my-library', [file])
      })

      const xhr = MockXMLHttpRequest.getLastInstance()
      const formData = xhr!.sentBody as FormData
      const pathsJson = formData.get('paths') as string

      expect(pathsJson).toBe(JSON.stringify(['track.flac']))
    })

    it('should set 10 minute timeout', () => {
      const { result } = renderHook(() => useFileUpload(), {
        wrapper: createWrapper(),
      })

      const file = createMockFile('track.flac', 1000)

      act(() => {
        result.current.upload('my-library', [file])
      })

      const xhr = MockXMLHttpRequest.getLastInstance()
      expect(xhr!.timeout).toBe(600000)
    })
  })

  describe('progress tracking', () => {
    it('should update progress on upload progress events', () => {
      const onProgress = vi.fn()
      const { result } = renderHook(() => useFileUpload({ onProgress }), {
        wrapper: createWrapper(),
      })

      const file = createMockFile('track.flac', 1000)

      act(() => {
        result.current.upload('my-library', [file])
      })

      const xhr = MockXMLHttpRequest.getLastInstance()

      act(() => {
        xhr!.simulateProgress(500, 1000)
      })

      expect(result.current.state.uploadedBytes).toBe(500)
      expect(result.current.state.progress).toBe(50)
      expect(onProgress).toHaveBeenCalledWith(50)
    })

    it('should update progress to 100% on completion', () => {
      const { result } = renderHook(() => useFileUpload(), {
        wrapper: createWrapper(),
      })

      const file = createMockFile('track.flac', 1000)

      act(() => {
        result.current.upload('my-library', [file])
      })

      const xhr = MockXMLHttpRequest.getLastInstance()

      act(() => {
        xhr!.simulateProgress(1000, 1000)
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

      expect(result.current.state.status).toBe('success')
      expect(result.current.state.progress).toBe(100)
    })
  })

  describe('success handling', () => {
    it('should set success state and call onSuccess callback', () => {
      const onSuccess = vi.fn()
      const { result } = renderHook(() => useFileUpload({ onSuccess }), {
        wrapper: createWrapper(),
      })

      const file = createMockFile('track.flac', 1000)

      act(() => {
        result.current.upload('my-library', [file])
      })

      const xhr = MockXMLHttpRequest.getLastInstance()

      act(() => {
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

      expect(result.current.state.status).toBe('success')
      expect(onSuccess).toHaveBeenCalledWith({
        status: 'success',
        message: 'Successfully uploaded 1 file',
        filesUploaded: 1,
        files: [{ filename: 'track.flac', path: 'track.flac', sizeBytes: 1000 }],
      })
    })

    it('should transform snake_case API response to camelCase', () => {
      const onSuccess = vi.fn()
      const { result } = renderHook(() => useFileUpload({ onSuccess }), {
        wrapper: createWrapper(),
      })

      const file = createMockFile('track.flac', 35621984)

      act(() => {
        result.current.upload('my-library', [file])
      })

      const xhr = MockXMLHttpRequest.getLastInstance()

      act(() => {
        xhr!.simulateLoad(
          200,
          JSON.stringify({
            status: 'success',
            message: 'Successfully uploaded 1 file',
            files_uploaded: 1,
            files: [
              { filename: 'track.flac', path: 'Album/track.flac', size_bytes: 35621984 },
            ],
          })
        )
      })

      expect(onSuccess).toHaveBeenCalledWith({
        status: 'success',
        message: 'Successfully uploaded 1 file',
        filesUploaded: 1,
        files: [{ filename: 'track.flac', path: 'Album/track.flac', sizeBytes: 35621984 }],
      })
    })
  })

  describe('error handling', () => {
    it('should set error state on HTTP error response', () => {
      const onError = vi.fn()
      const { result } = renderHook(() => useFileUpload({ onError }), {
        wrapper: createWrapper(),
      })

      const file = createMockFile('track.flac', 1000)

      act(() => {
        result.current.upload('my-library', [file])
      })

      const xhr = MockXMLHttpRequest.getLastInstance()

      act(() => {
        xhr!.simulateLoad(
          400,
          JSON.stringify({
            detail: {
              code: 'EMPTY_REQUEST',
              message: 'No files provided in the upload request',
            },
          })
        )
      })

      expect(result.current.state.status).toBe('error')
      expect(result.current.state.error).toBe('No files provided in the upload request')
      expect(onError).toHaveBeenCalledWith('No files provided in the upload request')
    })

    it('should handle string error detail', () => {
      const onError = vi.fn()
      const { result } = renderHook(() => useFileUpload({ onError }), {
        wrapper: createWrapper(),
      })

      const file = createMockFile('track.flac', 1000)

      act(() => {
        result.current.upload('my-library', [file])
      })

      const xhr = MockXMLHttpRequest.getLastInstance()

      act(() => {
        xhr!.simulateLoad(404, JSON.stringify({ detail: 'Library not found' }))
      })

      expect(result.current.state.status).toBe('error')
      expect(result.current.state.error).toBe('Library not found')
    })

    it('should handle file conflict errors (409)', () => {
      const onError = vi.fn()
      const { result } = renderHook(() => useFileUpload({ onError }), {
        wrapper: createWrapper(),
      })

      const file = createMockFile('track.flac', 1000)

      act(() => {
        result.current.upload('my-library', [file])
      })

      const xhr = MockXMLHttpRequest.getLastInstance()

      act(() => {
        xhr!.simulateLoad(
          409,
          JSON.stringify({
            detail: {
              code: 'FILE_EXISTS',
              message: 'One or more files already exist at the destination',
              conflicts: [{ filename: 'track.flac', path: 'track.flac' }],
            },
          })
        )
      })

      expect(result.current.state.status).toBe('error')
      expect(result.current.state.error).toBe(
        'One or more files already exist at the destination'
      )
    })

    it('should set error state on network error', () => {
      const onError = vi.fn()
      const { result } = renderHook(() => useFileUpload({ onError }), {
        wrapper: createWrapper(),
      })

      const file = createMockFile('track.flac', 1000)

      act(() => {
        result.current.upload('my-library', [file])
      })

      const xhr = MockXMLHttpRequest.getLastInstance()

      act(() => {
        xhr!.simulateError()
      })

      expect(result.current.state.status).toBe('error')
      expect(result.current.state.error).toBe('Network error occurred during upload')
      expect(onError).toHaveBeenCalledWith('Network error occurred during upload')
    })

    it('should set error state on timeout', () => {
      const onError = vi.fn()
      const { result } = renderHook(() => useFileUpload({ onError }), {
        wrapper: createWrapper(),
      })

      const file = createMockFile('track.flac', 1000)

      act(() => {
        result.current.upload('my-library', [file])
      })

      const xhr = MockXMLHttpRequest.getLastInstance()

      act(() => {
        xhr!.simulateTimeout()
      })

      expect(result.current.state.status).toBe('error')
      expect(result.current.state.error).toBe('Upload timed out')
      expect(onError).toHaveBeenCalledWith('Upload timed out')
    })

    it('should handle invalid JSON response', () => {
      const onError = vi.fn()
      const { result } = renderHook(() => useFileUpload({ onError }), {
        wrapper: createWrapper(),
      })

      const file = createMockFile('track.flac', 1000)

      act(() => {
        result.current.upload('my-library', [file])
      })

      const xhr = MockXMLHttpRequest.getLastInstance()

      act(() => {
        xhr!.simulateLoad(200, 'not valid json')
      })

      expect(result.current.state.status).toBe('error')
      expect(result.current.state.error).toBe('Failed to parse upload response')
    })
  })

  describe('cancel function', () => {
    it('should abort upload and set error state', () => {
      const { result } = renderHook(() => useFileUpload(), {
        wrapper: createWrapper(),
      })

      const file = createMockFile('track.flac', 1000)

      act(() => {
        result.current.upload('my-library', [file])
      })

      expect(result.current.state.status).toBe('uploading')

      act(() => {
        result.current.cancel()
      })

      expect(result.current.state.status).toBe('error')
      expect(result.current.state.error).toBe('Upload cancelled')
    })
  })

  describe('reset function', () => {
    it('should reset state to initial values', () => {
      const { result } = renderHook(() => useFileUpload(), {
        wrapper: createWrapper(),
      })

      const file = createMockFile('track.flac', 1000)

      act(() => {
        result.current.upload('my-library', [file])
      })

      const xhr = MockXMLHttpRequest.getLastInstance()

      act(() => {
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

      expect(result.current.state.status).toBe('success')

      act(() => {
        result.current.reset()
      })

      expect(result.current.state).toEqual({
        status: 'idle',
        totalBytes: 0,
        uploadedBytes: 0,
        progress: 0,
        fileCount: 0,
        error: null,
      })
    })

    it('should abort ongoing upload when reset is called', () => {
      const { result } = renderHook(() => useFileUpload(), {
        wrapper: createWrapper(),
      })

      const file = createMockFile('track.flac', 1000)

      act(() => {
        result.current.upload('my-library', [file])
      })

      expect(result.current.state.status).toBe('uploading')

      act(() => {
        result.current.reset()
      })

      expect(result.current.state.status).toBe('idle')
    })
  })

  describe('cleanup on unmount', () => {
    it('should abort upload on unmount', () => {
      const { result, unmount } = renderHook(() => useFileUpload(), {
        wrapper: createWrapper(),
      })

      const file = createMockFile('track.flac', 1000)

      act(() => {
        result.current.upload('my-library', [file])
      })

      const xhr = MockXMLHttpRequest.getLastInstance()
      expect(xhr).toBeDefined()

      unmount()

      // XHR should be aborted
      expect(xhr!.readyState).toBe(0) // UNSENT after abort
    })
  })

  describe('multiple uploads', () => {
    it('should cancel previous upload when starting new one', () => {
      const { result } = renderHook(() => useFileUpload(), {
        wrapper: createWrapper(),
      })

      const file1 = createMockFile('track1.flac', 1000)
      const file2 = createMockFile('track2.flac', 2000)

      act(() => {
        result.current.upload('my-library', [file1])
      })

      const firstXhr = MockXMLHttpRequest.getLastInstance()
      expect(firstXhr).toBeDefined()
      expect(result.current.state.totalBytes).toBe(1000)

      act(() => {
        result.current.upload('my-library', [file2])
      })

      const secondXhr = MockXMLHttpRequest.getLastInstance()
      expect(secondXhr).toBeDefined()
      expect(secondXhr).not.toBe(firstXhr)
      expect(result.current.state.totalBytes).toBe(2000)

      // First XHR should be aborted
      expect(firstXhr!.readyState).toBe(0)
    })
  })
})
