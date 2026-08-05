import { useState, useCallback, useRef, useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { importTreeKeys } from './useImportTree'
import type {
  UploadState,
  UploadResponse,
  UseFileUploadOptions,
  UseFileUploadResult,
  ApiErrorDetail,
} from '@/types/upload'

// ============================================================================
// Constants
// ============================================================================

const API_URL = import.meta.env.VITE_API_URL || '/api'

// ============================================================================
// Initial State
// ============================================================================

const initialState: UploadState = {
  status: 'idle',
  totalBytes: 0,
  uploadedBytes: 0,
  progress: 0,
  fileCount: 0,
  error: null,
}

// ============================================================================
// API Response Transformation
// ============================================================================

interface ApiUploadedFile {
  filename: string
  path: string
  size_bytes: number
}

interface ApiUploadResponse {
  status: 'success'
  message: string
  files_uploaded: number
  files: ApiUploadedFile[]
}

function transformResponse(apiResponse: ApiUploadResponse): UploadResponse {
  return {
    status: apiResponse.status,
    message: apiResponse.message,
    filesUploaded: apiResponse.files_uploaded,
    files: apiResponse.files.map((file) => ({
      filename: file.filename,
      path: file.path,
      sizeBytes: file.size_bytes,
    })),
  }
}

// ============================================================================
// Error Parsing
// ============================================================================

function parseErrorResponse(responseText: string): string {
  try {
    const errorData = JSON.parse(responseText)
    if (errorData.detail) {
      if (typeof errorData.detail === 'string') {
        return errorData.detail
      }
      const detail = errorData.detail as ApiErrorDetail
      if (detail.message) {
        return detail.message
      }
      if (detail.code) {
        return `Error: ${detail.code}`
      }
    }
    return 'Upload failed'
  } catch {
    return responseText || 'Upload failed'
  }
}

// ============================================================================
// Main Hook
// ============================================================================

/**
 * Hook for uploading files to a library's import folder with progress tracking.
 *
 * Uses XMLHttpRequest for upload progress events since fetch API doesn't support them.
 * Automatically invalidates the import-tree query on successful upload.
 *
 * @param options - Hook options including callbacks
 * @returns Upload state and control functions
 */
export function useFileUpload(options: UseFileUploadOptions = {}): UseFileUploadResult {
  const { onStart, onSuccess, onError, onProgress } = options

  const [state, setState] = useState<UploadState>(initialState)
  const queryClient = useQueryClient()

  // Refs for managing lifecycle
  const xhrRef = useRef<XMLHttpRequest | null>(null)
  const slugRef = useRef<string>('')

  // Stable callback refs
  const onStartRef = useRef(onStart)
  const onSuccessRef = useRef(onSuccess)
  const onErrorRef = useRef(onError)
  const onProgressRef = useRef(onProgress)

  useEffect(() => {
    onStartRef.current = onStart
    onSuccessRef.current = onSuccess
    onErrorRef.current = onError
    onProgressRef.current = onProgress
  }, [onStart, onSuccess, onError, onProgress])

  // Cleanup function
  const cleanup = useCallback(() => {
    if (xhrRef.current) {
      xhrRef.current.abort()
      xhrRef.current = null
    }
  }, [])

  // Reset state
  const reset = useCallback(() => {
    cleanup()
    setState(initialState)
  }, [cleanup])

  // Cancel upload
  const cancel = useCallback(() => {
    cleanup()
    setState((prev) => ({
      ...prev,
      status: 'error',
      error: 'Upload cancelled',
    }))
  }, [cleanup])

  // Upload files
  const upload = useCallback(
    (slug: string, files: File[]) => {
      if (files.length === 0) {
        setState((prev) => ({
          ...prev,
          status: 'error',
          error: 'No files selected',
        }))
        onErrorRef.current?.('No files selected')
        return
      }

      cleanup()
      slugRef.current = slug

      // Calculate total size
      const totalBytes = files.reduce((sum, file) => sum + file.size, 0)

      // Create FormData
      const formData = new FormData()

      // Collect relative paths from webkitRelativePath (for folder uploads)
      const paths: string[] = []

      files.forEach((file) => {
        formData.append('files', file)
        // Use webkitRelativePath if available (folder uploads), otherwise just filename
        const relativePath = (file as File & { webkitRelativePath?: string }).webkitRelativePath
        paths.push(relativePath || file.name)
      })

      // Add paths as JSON array
      formData.append('paths', JSON.stringify(paths))

      // Update state to uploading
      setState({
        status: 'uploading',
        totalBytes,
        uploadedBytes: 0,
        progress: 0,
        fileCount: files.length,
        error: null,
      })

      onStartRef.current?.()

      // Create XMLHttpRequest for progress tracking
      const xhr = new XMLHttpRequest()
      xhrRef.current = xhr

      // Handle upload progress
      xhr.upload.addEventListener('progress', (event) => {
        if (event.lengthComputable) {
          const progress = Math.round((event.loaded / event.total) * 100)
          setState((prev) => ({
            ...prev,
            uploadedBytes: event.loaded,
            progress,
          }))
          onProgressRef.current?.(progress)
        }
      })

      // Handle completion
      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const response = JSON.parse(xhr.responseText) as ApiUploadResponse
            const transformedResponse = transformResponse(response)

            setState((prev) => ({
              ...prev,
              status: 'success',
              progress: 100,
              uploadedBytes: prev.totalBytes,
            }))

            onSuccessRef.current?.(transformedResponse)

            // Invalidate import-tree query to refresh the folder tree
            queryClient.invalidateQueries({
              queryKey: importTreeKeys.byLibrary(slugRef.current),
            })
          } catch {
            const errorMessage = 'Failed to parse upload response'
            setState((prev) => ({
              ...prev,
              status: 'error',
              error: errorMessage,
            }))
            onErrorRef.current?.(errorMessage)
          }
        } else {
          const errorMessage = parseErrorResponse(xhr.responseText)
          setState((prev) => ({
            ...prev,
            status: 'error',
            error: errorMessage,
          }))
          onErrorRef.current?.(errorMessage)
        }

        xhrRef.current = null
      })

      // Handle network errors
      xhr.addEventListener('error', () => {
        const errorMessage = 'Network error occurred during upload'
        setState((prev) => ({
          ...prev,
          status: 'error',
          error: errorMessage,
        }))
        onErrorRef.current?.(errorMessage)
        xhrRef.current = null
      })

      // Handle abort
      xhr.addEventListener('abort', () => {
        // State already set by cancel function
        xhrRef.current = null
      })

      // Handle timeout
      xhr.addEventListener('timeout', () => {
        const errorMessage = 'Upload timed out'
        setState((prev) => ({
          ...prev,
          status: 'error',
          error: errorMessage,
        }))
        onErrorRef.current?.(errorMessage)
        xhrRef.current = null
      })

      // Send request
      xhr.open('POST', `${API_URL}/v1/libraries/${slug}/upload`)
      xhr.timeout = 600000 // 10 minutes
      xhr.send(formData)
    },
    [cleanup, queryClient]
  )

  // Cleanup on unmount
  useEffect(() => {
    return cleanup
  }, [cleanup])

  return {
    state,
    upload,
    reset,
    cancel,
  }
}

export default useFileUpload
