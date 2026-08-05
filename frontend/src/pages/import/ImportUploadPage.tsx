import { useCallback, useRef } from 'react'
import { useOutletContext } from 'react-router-dom'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScanProgressSection } from '@/components/scan/ScanProgressSection'
import { FileDropZone, ImportDragOverlay, type FileDropZoneHandle } from '@/components/upload'
import { ImportFolderTree, ImportItemsList } from '@/components/import'

import type { ImportDetailContext } from '../ImportDetailLayout'

/**
 * Upload page: everything about getting files INTO the import folder.
 * Top to bottom: Upload Files (drop zone), Import Folder (tree with
 * per-folder delete), Discovered Items (last scan's findings).
 */
export default function ImportUploadPage() {
  const {
    slug,
    library,
    statusData,
    progressState,
    handleTriggerScan,
    isTriggeringScan,
    handleUploadSuccess,
    selectedPath,
    setSelectedPath,
    handleFolderDeleted,
  } = useOutletContext<ImportDetailContext>()

  // Route full-page drops into the same upload pipeline as the inline drop zone.
  const dropZoneRef = useRef<FileDropZoneHandle>(null)
  const handleOverlayFiles = useCallback((files: File[]) => {
    dropZoneRef.current?.uploadFiles(files)
  }, [])

  return (
    <div className="space-y-6">
      {/* Upload card — shows the running upload (incl. full-page drops). */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">Upload Files</CardTitle>
          <p className="text-sm text-muted-foreground">
            Drag and drop files or folders anywhere on the page to upload them to
            the import folder. Supports large collections up to 4GB per upload.
          </p>
        </CardHeader>
        <CardContent>
          <FileDropZone
            ref={dropZoneRef}
            librarySlug={slug}
            onUploadSuccess={handleUploadSuccess}
          />
        </CardContent>
      </Card>

      {/* Import Folder — folder tree with per-folder delete. */}
      <ImportFolderTree
        librarySlug={slug}
        onFolderSelect={setSelectedPath}
        selectedPath={selectedPath}
        onFolderDeleted={handleFolderDeleted}
      />

      {/* Scanner — scans the import folder into Discovered Items. */}
      <ScanProgressSection
        progressState={progressState}
        statusData={statusData}
        libraryName={library.name}
        onTriggerScan={handleTriggerScan}
        isTriggeringScan={isTriggeringScan}
      />

      {/* Discovered items — collapsed by default. */}
      <ImportItemsList slug={slug} defaultCollapsed={true} />

      {/* Full-page drag-and-drop overlay. */}
      <ImportDragOverlay onFiles={handleOverlayFiles} />
    </div>
  )
}
