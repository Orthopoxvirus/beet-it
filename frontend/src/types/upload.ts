/**
 * Type definitions for file upload functionality.
 */

// ============================================================================
// Upload Status Types
// ============================================================================

/**
 * Possible states for the upload process.
 */
export type UploadStatus = 'idle' | 'uploading' | 'success' | 'error'

// ============================================================================
// File Upload State
// ============================================================================

/**
 * State for tracking individual file upload progress.
 */
export interface FileUploadProgress {
  /** File name */
  filename: string
  /** Relative path (for folder uploads) */
  path: string
  /** File size in bytes */
  size: number
  /** Bytes uploaded so far */
  uploaded: number
  /** Progress percentage (0-100) */
  progress: number
}

/**
 * Aggregate upload state.
 */
export interface UploadState {
  /** Current upload status */
  status: UploadStatus
  /** Total bytes to upload */
  totalBytes: number
  /** Bytes uploaded so far */
  uploadedBytes: number
  /** Aggregate progress percentage (0-100) */
  progress: number
  /** Number of files being uploaded */
  fileCount: number
  /** Error message if status is 'error' */
  error: string | null
}

// ============================================================================
// API Response Types
// ============================================================================

/**
 * Individual file upload result from API.
 */
export interface UploadedFile {
  /** Original filename */
  filename: string
  /** Relative path where file was saved */
  path: string
  /** File size in bytes */
  sizeBytes: number
}

/**
 * Successful upload API response.
 */
export interface UploadResponse {
  /** Upload status */
  status: 'success'
  /** Human-readable success message */
  message: string
  /** Number of files successfully uploaded */
  filesUploaded: number
  /** Details of uploaded files */
  files: UploadedFile[]
}

/**
 * File conflict details from API error response.
 */
export interface FileConflict {
  /** Original filename */
  filename: string
  /** Relative path that conflicts */
  path: string
}

/**
 * Error response for file conflicts (409).
 */
export interface ConflictError {
  /** Error code */
  code: 'FILE_EXISTS'
  /** Human-readable error message */
  message: string
  /** List of conflicting files */
  conflicts: FileConflict[]
}

/**
 * Generic API error detail structure.
 */
export interface ApiErrorDetail {
  /** Error code */
  code: string
  /** Human-readable error message */
  message: string
  /** Additional error details (varies by error type) */
  [key: string]: unknown
}

// ============================================================================
// Hook Options and Result Types
// ============================================================================

/**
 * Options for the useFileUpload hook.
 */
export interface UseFileUploadOptions {
  /**
   * Callback when upload starts.
   */
  onStart?: () => void
  /**
   * Callback when upload succeeds.
   */
  onSuccess?: (response: UploadResponse) => void
  /**
   * Callback when upload fails.
   */
  onError?: (error: string) => void
  /**
   * Callback for progress updates.
   */
  onProgress?: (progress: number) => void
}

/**
 * Result returned by the useFileUpload hook.
 */
export interface UseFileUploadResult {
  /** Current upload state */
  state: UploadState
  /** Upload files to the server */
  upload: (slug: string, files: File[]) => void
  /** Reset the upload state */
  reset: () => void
  /** Cancel the current upload */
  cancel: () => void
}
