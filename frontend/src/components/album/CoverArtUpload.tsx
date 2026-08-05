import { useState, useRef, useCallback, type DragEvent, type ChangeEvent } from 'react'
import { Upload, Link as LinkIcon, Search, X, Check, Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'

import {
  useUploadCoverArt,
  useDownloadCoverArtFromUrl,
  useSearchCoverArt,
} from '@/hooks/useAlbums'

// ============================================================================
// Constants
// ============================================================================

const ACCEPTED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
const ACCEPTED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10 MB

// ============================================================================
// Helper Functions
// ============================================================================

function isValidImageType(file: File): boolean {
  return ACCEPTED_IMAGE_TYPES.includes(file.type)
}

function isValidFileSize(file: File): boolean {
  return file.size <= MAX_FILE_SIZE
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// ============================================================================
// CoverArtUpload Component
// ============================================================================

export interface CoverArtUploadProps {
  /** The library slug */
  slug: string
  /** The album ID */
  albumId: number
  /** Whether the upload dialog is open */
  isOpen: boolean
  /** Callback to close the dialog */
  onClose: () => void
  /** Callback when upload is successful */
  onSuccess?: () => void
  /** Which tab to open on. Defaults to 'upload'. */
  defaultMode?: 'search' | 'upload' | 'url'
}

export function CoverArtUpload({
  slug,
  albumId,
  isOpen,
  onClose,
  onSuccess,
  defaultMode = 'upload',
}: CoverArtUploadProps) {
  // State for file upload
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [isDragOver, setIsDragOver] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Active tab. 'search' looks up cover art online; 'upload' / 'url' unchanged.
  const [mode, setMode] = useState<'search' | 'upload' | 'url'>(defaultMode)
  const [urlInput, setUrlInput] = useState('')

  const fileInputRef = useRef<HTMLInputElement>(null)

  // Mutations
  const uploadMutation = useUploadCoverArt()
  const urlMutation = useDownloadCoverArtFromUrl()

  // Online cover-art search only fires while its tab is open.
  const {
    data: searchData,
    isLoading: searchLoading,
    isError: searchIsError,
    error: searchError,
  } = useSearchCoverArt(slug, albumId, isOpen && mode === 'search')

  const isLoading = uploadMutation.isPending || urlMutation.isPending

  // ============================================================================
  // File Selection Handlers
  // ============================================================================

  const validateAndSetFile = useCallback((file: File) => {
    setError(null)

    if (!isValidImageType(file)) {
      setError(`Invalid file type. Accepted formats: ${ACCEPTED_EXTENSIONS.join(', ')}`)
      return false
    }

    if (!isValidFileSize(file)) {
      setError(`File too large. Maximum size: ${formatFileSize(MAX_FILE_SIZE)}`)
      return false
    }

    setSelectedFile(file)

    // Create preview URL
    const url = URL.createObjectURL(file)
    setPreviewUrl(url)

    return true
  }, [])

  const handleFileSelect = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0]
      if (file) {
        validateAndSetFile(file)
      }
    },
    [validateAndSetFile]
  )

  const handleDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setIsDragOver(true)
  }, [])

  const handleDragLeave = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setIsDragOver(false)
  }, [])

  const handleDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault()
      setIsDragOver(false)

      const file = event.dataTransfer.files?.[0]
      if (file) {
        validateAndSetFile(file)
      }
    },
    [validateAndSetFile]
  )

  const handleBrowseClick = useCallback(() => {
    fileInputRef.current?.click()
  }, [])

  // ============================================================================
  // Upload Handlers
  // ============================================================================

  const handleUpload = useCallback(async () => {
    if (!selectedFile) return

    try {
      await uploadMutation.mutateAsync({
        slug,
        albumId,
        file: selectedFile,
      })
      onSuccess?.()
      handleReset()
      onClose()
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to upload cover art'
      )
    }
  }, [selectedFile, slug, albumId, uploadMutation, onSuccess, onClose])

  const handleUrlSubmit = useCallback(async () => {
    if (!urlInput.trim()) {
      setError('Please enter a URL')
      return
    }

    // Basic URL validation
    try {
      new URL(urlInput)
    } catch {
      setError('Invalid URL format')
      return
    }

    try {
      await urlMutation.mutateAsync({
        slug,
        albumId,
        url: urlInput.trim(),
      })
      onSuccess?.()
      handleReset()
      onClose()
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to download cover art from URL'
      )
    }
  }, [urlInput, slug, albumId, urlMutation, onSuccess, onClose])

  // Apply a search result by reusing the (SSRF-guarded) download-from-URL path.
  const handleSelectCandidate = useCallback(
    async (url: string) => {
      try {
        await urlMutation.mutateAsync({ slug, albumId, url })
        onSuccess?.()
        handleReset()
        onClose()
      } catch (err) {
        setError(
          err instanceof Error ? err.message : 'Failed to apply cover art'
        )
      }
    },
    // handleReset is intentionally omitted, matching handleUpload/handleUrlSubmit.
    [slug, albumId, urlMutation, onSuccess, onClose]
  )

  const handleReset = useCallback(() => {
    setSelectedFile(null)
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
    }
    setPreviewUrl(null)
    setError(null)
    setUrlInput('')
    setMode(defaultMode)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }, [previewUrl, defaultMode])

  const handleClose = useCallback(() => {
    handleReset()
    onClose()
  }, [handleReset, onClose])

  // ============================================================================
  // Render
  // ============================================================================

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && handleClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Update Cover Art</DialogTitle>
        </DialogHeader>

        {/* Mode Tabs */}
        <div className="flex border-b">
          <button
            type="button"
            className={`flex-1 py-2 px-4 text-sm font-medium transition-colors ${
              mode === 'search'
                ? 'border-b-2 border-primary text-primary'
                : 'text-muted-foreground hover:text-foreground'
            }`}
            onClick={() => {
              setMode('search')
              setError(null)
            }}
          >
            <Search className="h-4 w-4 inline-block mr-1" />
            Search online
          </button>
          <button
            type="button"
            className={`flex-1 py-2 px-4 text-sm font-medium transition-colors ${
              mode === 'upload'
                ? 'border-b-2 border-primary text-primary'
                : 'text-muted-foreground hover:text-foreground'
            }`}
            onClick={() => {
              setMode('upload')
              setError(null)
            }}
          >
            <Upload className="h-4 w-4 inline-block mr-1" />
            Upload
          </button>
          <button
            type="button"
            className={`flex-1 py-2 px-4 text-sm font-medium transition-colors ${
              mode === 'url'
                ? 'border-b-2 border-primary text-primary'
                : 'text-muted-foreground hover:text-foreground'
            }`}
            onClick={() => {
              setMode('url')
              setError(null)
            }}
          >
            <LinkIcon className="h-4 w-4 inline-block mr-1" />
            From URL
          </button>
        </div>

        <div className="space-y-4 py-2">
          {mode === 'search' ? (
            /* Online Search Mode */
            <div className="space-y-3">
              {searchLoading ? (
                <div className="py-8 text-center text-sm text-muted-foreground">
                  <Loader2 className="h-6 w-6 mx-auto animate-spin mb-2" />
                  Searching iTunes, Deezer and Cover Art Archive…
                </div>
              ) : searchIsError ? (
                <div className="text-sm text-destructive bg-destructive/10 p-3 rounded-md">
                  {searchError instanceof Error
                    ? searchError.message
                    : 'Search failed'}
                </div>
              ) : !searchData || searchData.results.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  No cover art found online for this album.
                </p>
              ) : (
                <div className="grid grid-cols-3 gap-3 max-h-[320px] overflow-y-auto">
                  {searchData.results.map((result) => (
                    <button
                      key={result.url}
                      type="button"
                      disabled={isLoading}
                      onClick={() => handleSelectCandidate(result.url)}
                      className="group relative rounded-md overflow-hidden border hover:border-primary focus:border-primary focus:outline-none disabled:opacity-50"
                      title={`${result.width && result.height ? `${result.width}×${result.height}` : 'unknown size'} · ${result.source}`}
                    >
                      <img
                        src={result.url}
                        alt="Cover art candidate"
                        loading="lazy"
                        className="w-full aspect-square object-cover"
                      />
                      <span className="block px-1 py-0.5 text-[10px] leading-tight text-muted-foreground truncate text-left">
                        {result.width && result.height
                          ? `${result.width}×${result.height}`
                          : 'unknown'}{' '}
                        · {result.source}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : mode === 'upload' ? (
            <>
              {/* Drop Zone */}
              {!previewUrl ? (
                <div
                  className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
                    isDragOver
                      ? 'border-primary bg-primary/5'
                      : 'border-muted-foreground/25 hover:border-muted-foreground/50'
                  }`}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                >
                  <Upload className="h-10 w-10 mx-auto text-muted-foreground mb-3" />
                  <p className="text-sm text-muted-foreground mb-2">
                    Drag and drop an image here, or
                  </p>
                  <Button variant="outline" onClick={handleBrowseClick}>
                    Browse Files
                  </Button>
                  <p className="text-xs text-muted-foreground mt-3">
                    Accepted formats: JPEG, PNG, GIF, WebP (max 10 MB)
                  </p>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept={ACCEPTED_IMAGE_TYPES.join(',')}
                    onChange={handleFileSelect}
                    className="hidden"
                  />
                </div>
              ) : (
                /* Preview */
                <div className="space-y-3">
                  <div className="relative aspect-square max-w-[200px] mx-auto">
                    <img
                      src={previewUrl}
                      alt="Cover art preview"
                      className="w-full h-full object-cover rounded-lg"
                    />
                    <Button
                      variant="destructive"
                      size="icon"
                      className="absolute -top-2 -right-2 h-6 w-6"
                      onClick={handleReset}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                  {selectedFile && (
                    <p className="text-sm text-center text-muted-foreground">
                      {selectedFile.name} ({formatFileSize(selectedFile.size)})
                    </p>
                  )}
                </div>
              )}
            </>
          ) : (
            /* URL Input Mode */
            <div className="space-y-3">
              <div className="space-y-2">
                <label htmlFor="cover-url" className="text-sm font-medium">
                  Image URL
                </label>
                <Input
                  id="cover-url"
                  type="url"
                  placeholder="https://example.com/album-cover.jpg"
                  value={urlInput}
                  onChange={(e) => {
                    setUrlInput(e.target.value)
                    setError(null)
                  }}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Enter a direct link to an image file (JPEG, PNG, GIF, or WebP)
              </p>
            </div>
          )}

          {/* Error Message */}
          {error && (
            <div className="text-sm text-destructive bg-destructive/10 p-3 rounded-md">
              {error}
            </div>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={handleClose} disabled={isLoading}>
            Cancel
          </Button>
          {mode === 'upload' ? (
            <Button
              onClick={handleUpload}
              disabled={!selectedFile || isLoading}
            >
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Uploading...
                </>
              ) : (
                <>
                  <Check className="h-4 w-4 mr-2" />
                  Apply
                </>
              )}
            </Button>
          ) : mode === 'url' ? (
            <Button
              onClick={handleUrlSubmit}
              disabled={!urlInput.trim() || isLoading}
            >
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Downloading...
                </>
              ) : (
                <>
                  <Check className="h-4 w-4 mr-2" />
                  Download
                </>
              )}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default CoverArtUpload
