import {
  useState,
  useCallback,
  useRef,
  useEffect,
  forwardRef,
  useImperativeHandle,
} from 'react'
import { Upload, FolderUp, X, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'
import { useFileUpload } from '@/hooks/useFileUpload'
import type { UploadResponse } from '@/types/upload'

// ============================================================================
// Constants
// ============================================================================

/** Human-readable upload size limit, shared with the full-page drag overlay. */
export const MAX_UPLOAD_SIZE_LABEL = '4GB per request'

// ============================================================================
// Types
// ============================================================================

export interface FileDropZoneProps {
  /** Library slug for upload endpoint */
  librarySlug: string
  /** Optional CSS class name */
  className?: string
  /** Callback when upload succeeds */
  onUploadSuccess?: (response: UploadResponse) => void
  /** Callback when upload fails */
  onUploadError?: (error: string) => void
}

/**
 * Imperative handle exposed via ref so an external drop target (e.g. the
 * full-page drag overlay) can push files through the same upload pipeline,
 * keeping a single source of upload progress in this card.
 */
export interface FileDropZoneHandle {
  /** Upload a set of already-extracted files. No-op while an upload is running. */
  uploadFiles: (files: File[]) => void
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Format bytes to human-readable string.
 */
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

/**
 * Extract files from DataTransfer for drag-and-drop.
 * Handles both files and directory entries.
 */
export async function extractFilesFromDataTransfer(dataTransfer: DataTransfer): Promise<File[]> {
  const files: File[] = []
  const items = Array.from(dataTransfer.items)

  for (const item of items) {
    if (item.kind !== 'file') continue

    // Try to get as file system entry for directory support
    const entry = item.webkitGetAsEntry?.()

    if (entry) {
      const entryFiles = await readEntry(entry)
      files.push(...entryFiles)
    } else {
      // Fallback to regular file
      const file = item.getAsFile()
      if (file) {
        files.push(file)
      }
    }
  }

  return files
}

/**
 * Recursively read a FileSystemEntry.
 */
async function readEntry(entry: FileSystemEntry): Promise<File[]> {
  if (entry.isFile) {
    const fileEntry = entry as FileSystemFileEntry
    return new Promise((resolve) => {
      fileEntry.file(
        (file) => {
          // Create a new file with the full path
          const fileWithPath = new File([file], file.name, {
            type: file.type,
            lastModified: file.lastModified,
          })
          // Attach the webkitRelativePath manually
          Object.defineProperty(fileWithPath, 'webkitRelativePath', {
            value: entry.fullPath.replace(/^\//, ''),
            writable: false,
          })
          resolve([fileWithPath])
        },
        () => resolve([])
      )
    })
  } else if (entry.isDirectory) {
    const dirEntry = entry as FileSystemDirectoryEntry
    const reader = dirEntry.createReader()
    const entries: FileSystemEntry[] = []

    // Read all entries from the directory
    await new Promise<void>((resolve) => {
      const readEntries = () => {
        reader.readEntries(
          (results) => {
            if (results.length === 0) {
              resolve()
            } else {
              entries.push(...results)
              readEntries() // Continue reading if there are more
            }
          },
          () => resolve()
        )
      }
      readEntries()
    })

    // Recursively process all entries
    const files: File[] = []
    for (const subEntry of entries) {
      const subFiles = await readEntry(subEntry)
      files.push(...subFiles)
    }
    return files
  }

  return []
}

// ============================================================================
// Notification Component
// ============================================================================

interface NotificationProps {
  type: 'success' | 'error'
  message: string
  onDismiss: () => void
}

function Notification({ type, message, onDismiss }: NotificationProps) {
  // Auto-dismiss after 5 seconds
  useEffect(() => {
    const timer = setTimeout(onDismiss, 5000)
    return () => clearTimeout(timer)
  }, [onDismiss])

  return (
    <div
      className={cn(
        'flex items-center gap-3 px-4 py-3 rounded-md text-sm',
        type === 'success'
          ? 'bg-green-50 text-green-800 dark:bg-green-900/30 dark:text-green-300'
          : 'bg-red-50 text-red-800 dark:bg-red-900/30 dark:text-red-300'
      )}
    >
      {type === 'success' ? (
        <CheckCircle2 className="h-5 w-5 shrink-0" />
      ) : (
        <AlertCircle className="h-5 w-5 shrink-0" />
      )}
      <span className="flex-1">{message}</span>
      <button
        type="button"
        onClick={onDismiss}
        className="p-1 hover:bg-black/10 dark:hover:bg-white/10 rounded"
        aria-label="Dismiss"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

const FileDropZone = forwardRef<FileDropZoneHandle, FileDropZoneProps>(function FileDropZone(
  { librarySlug, className, onUploadSuccess, onUploadError }: FileDropZoneProps,
  ref
) {
  // Drag state - using simple boolean with timeout to avoid child element flickering
  const [isDragOver, setIsDragOver] = useState(false)
  const dragTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const dropZoneRef = useRef<HTMLDivElement>(null)

  // Notification state
  const [notification, setNotification] = useState<{
    type: 'success' | 'error'
    message: string
  } | null>(null)

  // File input refs
  const fileInputRef = useRef<HTMLInputElement>(null)
  const folderInputRef = useRef<HTMLInputElement>(null)

  // Upload hook
  const { state, upload, reset } = useFileUpload({
    onSuccess: (response) => {
      setNotification({
        type: 'success',
        message: `Successfully uploaded ${response.filesUploaded} file${response.filesUploaded === 1 ? '' : 's'}`,
      })
      onUploadSuccess?.(response)
    },
    onError: (error) => {
      setNotification({
        type: 'error',
        message: error,
      })
      onUploadError?.(error)
    },
  })

  // Push an already-extracted set of files through the upload pipeline.
  // Shared by the in-card drop handler and the external imperative handle.
  const uploadFiles = useCallback(
    (files: File[]) => {
      if (state.status === 'uploading') return
      if (files.length === 0) return
      reset()
      upload(librarySlug, files)
    },
    [librarySlug, state.status, upload, reset]
  )

  // Expose uploadFiles so a full-page overlay can route drops here, keeping the
  // running-upload progress visible in this single card.
  useImperativeHandle(ref, () => ({ uploadFiles }), [uploadFiles])

  // Handle drag enter
  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()

    // Clear any pending timeout
    if (dragTimeoutRef.current) {
      clearTimeout(dragTimeoutRef.current)
      dragTimeoutRef.current = null
    }

    // Only set drag state if we have files
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDragOver(true)
    }
  }, [])

  // Handle drag leave
  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()

    // Use a timeout to debounce drag leave events from child elements
    // This prevents flickering when dragging over child elements
    if (dragTimeoutRef.current) {
      clearTimeout(dragTimeoutRef.current)
    }

    dragTimeoutRef.current = setTimeout(() => {
      setIsDragOver(false)
      dragTimeoutRef.current = null
    }, 50) // 50ms delay to absorb rapid enter/leave events
  }, [])

  // Handle drag over (required to allow drop)
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }, [])

  // Handle drop
  const handleDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()

      // Clear any pending timeouts and drag state
      if (dragTimeoutRef.current) {
        clearTimeout(dragTimeoutRef.current)
        dragTimeoutRef.current = null
      }
      setIsDragOver(false)

      if (state.status === 'uploading') return

      const files = await extractFilesFromDataTransfer(e.dataTransfer)
      uploadFiles(files)
    },
    [state.status, uploadFiles]
  )

  // Handle file input change (for click-to-browse)
  const handleFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files
      if (!files || files.length === 0) return

      if (state.status === 'uploading') return

      reset()
      upload(librarySlug, Array.from(files))

      // Reset input value to allow selecting the same files again
      e.target.value = ''
    },
    [librarySlug, state.status, upload, reset]
  )

  // Handle click on drop zone to open file dialog
  const handleClickFiles = useCallback(() => {
    if (state.status === 'uploading') return
    fileInputRef.current?.click()
  }, [state.status])

  // Handle click to browse folders
  const handleClickFolders = useCallback(() => {
    if (state.status === 'uploading') return
    folderInputRef.current?.click()
  }, [state.status])

  // Dismiss notification
  const dismissNotification = useCallback(() => {
    setNotification(null)
  }, [])

  const isUploading = state.status === 'uploading'

  return (
    <div className={cn('space-y-3', className)}>
      {/* Notification */}
      {notification && (
        <Notification
          type={notification.type}
          message={notification.message}
          onDismiss={dismissNotification}
        />
      )}

      {/* Drop Zone */}
      <div
        ref={dropZoneRef}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        className={cn(
          'relative border-2 border-dashed rounded-lg p-8 transition-all duration-200',
          'flex flex-col items-center justify-center gap-4',
          isDragOver
            ? 'border-primary bg-primary/5 ring-2 ring-primary/20'
            : 'border-muted-foreground/25 hover:border-muted-foreground/50',
          isUploading && 'pointer-events-none opacity-75'
        )}
      >
        {/* Hidden file inputs */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={handleFileInputChange}
          aria-label="Select files"
        />
        <input
          ref={folderInputRef}
          type="file"
          multiple
          // @ts-expect-error - webkitdirectory is not in the type definition
          webkitdirectory=""
          className="hidden"
          onChange={handleFileInputChange}
          aria-label="Select folder"
        />

        {/* Icon and text */}
        {isUploading ? (
          <>
            <Loader2 className="h-12 w-12 text-primary animate-spin" />
            <div className="text-center">
              <p className="text-sm font-medium">
                Uploading {state.fileCount} file{state.fileCount === 1 ? '' : 's'}...
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                {formatBytes(state.uploadedBytes)} / {formatBytes(state.totalBytes)}
              </p>
            </div>
            {/* Progress bar */}
            <div className="w-full max-w-xs">
              <Progress value={state.progress} className="h-2" />
              <p className="text-xs text-muted-foreground text-center mt-1">
                {state.progress}%
              </p>
            </div>
          </>
        ) : isDragOver ? (
          <>
            <Upload className="h-12 w-12 text-primary" />
            <p className="text-lg font-medium text-primary">Drop files here</p>
          </>
        ) : (
          <>
            <div className="flex gap-2">
              <Upload className="h-10 w-10 text-muted-foreground" />
              <FolderUp className="h-10 w-10 text-muted-foreground" />
            </div>
            <div className="text-center">
              <p className="text-sm font-medium">
                Drag and drop files or folders here
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                or click to browse
              </p>
              <p className="text-xs text-muted-foreground/70 mt-2">
                Max upload size: 4GB per request
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleClickFiles}
              >
                <Upload className="h-4 w-4 mr-2" />
                Select Files
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleClickFolders}
              >
                <FolderUp className="h-4 w-4 mr-2" />
                Select Folder
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  )
})

export default FileDropZone
