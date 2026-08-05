import { useEffect, useRef, useState } from 'react'
import { UploadCloud } from 'lucide-react'

import { extractFilesFromDataTransfer, MAX_UPLOAD_SIZE_LABEL } from './FileDropZone'

// ============================================================================
// Types
// ============================================================================

interface ImportDragOverlayProps {
  /** Called with the extracted files when the user drops onto the page. */
  onFiles: (files: File[]) => void
  /** When true, the overlay never appears (e.g. while an upload is running). */
  disabled?: boolean
}

// ============================================================================
// Helpers
// ============================================================================

/**
 * Whether a drag operation carries OS files (as opposed to dragging text,
 * links, or page elements). Browsers expose this via the 'Files' type entry.
 */
function dragHasFiles(dataTransfer: DataTransfer | null): boolean {
  if (!dataTransfer) return false
  return Array.from(dataTransfer.types ?? []).includes('Files')
}

// ============================================================================
// Component
// ============================================================================

/**
 * Full-page drag-and-drop overlay. While files are dragged anywhere over the
 * window it shows a drop target spanning the viewport (with the upload size
 * limit), and on drop forwards the extracted files to {@link onFiles} — which
 * the page routes into the same upload pipeline as the inline drop zone.
 *
 * Drag events are tracked at the window level with an enter/leave depth counter
 * so dragging across nested child elements doesn't make the overlay flicker.
 */
export default function ImportDragOverlay({ onFiles, disabled = false }: ImportDragOverlayProps) {
  const [isDragging, setIsDragging] = useState(false)
  // Net dragenter/dragleave depth; the overlay hides only when it returns to 0.
  const depthRef = useRef(0)

  useEffect(() => {
    if (disabled) {
      depthRef.current = 0
      setIsDragging(false)
      return
    }

    const clear = () => {
      depthRef.current = 0
      setIsDragging(false)
    }

    const handleDragEnter = (e: DragEvent) => {
      if (!dragHasFiles(e.dataTransfer)) return
      e.preventDefault()
      depthRef.current += 1
      setIsDragging(true)
    }

    const handleDragOver = (e: DragEvent) => {
      if (!dragHasFiles(e.dataTransfer)) return
      // Required so the browser allows the drop and doesn't just open the file.
      e.preventDefault()
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
    }

    const handleDragLeave = (e: DragEvent) => {
      if (!dragHasFiles(e.dataTransfer)) return
      depthRef.current -= 1
      if (depthRef.current <= 0) clear()
    }

    const handleDrop = (e: DragEvent) => {
      if (!dragHasFiles(e.dataTransfer)) return
      e.preventDefault()
      clear()
      if (!e.dataTransfer) return
      void extractFilesFromDataTransfer(e.dataTransfer).then((files) => {
        if (files.length > 0) onFiles(files)
      })
    }

    window.addEventListener('dragenter', handleDragEnter)
    window.addEventListener('dragover', handleDragOver)
    window.addEventListener('dragleave', handleDragLeave)
    window.addEventListener('drop', handleDrop)
    return () => {
      window.removeEventListener('dragenter', handleDragEnter)
      window.removeEventListener('dragover', handleDragOver)
      window.removeEventListener('dragleave', handleDragLeave)
      window.removeEventListener('drop', handleDrop)
    }
  }, [onFiles, disabled])

  if (!isDragging) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-6 backdrop-blur-sm"
      data-testid="import-drag-overlay"
      aria-hidden="true"
    >
      <div className="pointer-events-none flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed border-primary bg-card/90 px-10 py-12 text-center shadow-lg ring-4 ring-primary/15">
        <UploadCloud className="h-16 w-16 text-primary" />
        <p className="text-xl font-semibold text-primary">
          Drop files or folders to upload
        </p>
        <p className="text-sm text-muted-foreground">
          They'll be added to this library's import folder.
        </p>
        <p className="text-xs text-muted-foreground/70">
          Max upload size: {MAX_UPLOAD_SIZE_LABEL}
        </p>
      </div>
    </div>
  )
}
