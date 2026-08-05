import { useState, useCallback, useEffect, useRef } from 'react'
import { useParams, useSearchParams, useNavigate, Outlet } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import { useLibrary } from '@/hooks/useLibraries'
import { useSyncActiveLibraryFromUrl } from '@/contexts/ActiveLibraryContext'
import { useScanProgress } from '@/hooks/useScanProgress'
import { useScanStatus, useTriggerScan, useInvalidateScanCache } from '@/hooks/useScanStatus'
import { useAnalyzeFolder } from '@/hooks/useBeetsAnalysis'
import { importTreeKeys } from '@/hooks/useImportTree'

import type { Library } from '@/api/libraries'

// ============================================================================
// Main Layout Component
// ============================================================================

export default function ImportDetailLayout() {
  const { slug } = useParams<{ slug: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // Sync active library context with URL slug
  useSyncActiveLibraryFromUrl(slug)

  // Selected folder path for the tree/table integration
  const [selectedPath, setSelectedPath] = useState<string | null>(null)

  // Handle a folder being deleted from the tree: if the deleted folder was the
  // current selection (or an ancestor of it), clear the selection so the table
  // doesn't keep showing tracks from a folder that no longer exists.
  const handleFolderDeleted = useCallback(
    (deletedPath: string) => {
      setSelectedPath((current) => {
        if (
          current &&
          (current === deletedPath || current.startsWith(`${deletedPath}/`))
        ) {
          return null
        }
        return current
      })
    },
    []
  )

  // Legacy tab URL redirect
  const tab = searchParams.get('tab')
  useEffect(() => {
    if (tab) {
      // Map legacy tab values to new routes
      const tabMap: Record<string, string> = {
        'files-folders': 'beets',
        files: 'beets',
        prepare: 'beets',
        'beets-import': 'beets',
        beets: 'beets',
        upload: 'upload',
      }
      const newPath = tabMap[tab] || 'beets'
      navigate(newPath, { replace: true })
    }
  }, [tab, navigate])

  // Fetch library details
  const { data: library, isLoading: isLoadingLibrary, error: libraryError } = useLibrary(slug || '')

  // Fetch initial scan status
  const { data: statusData, isLoading: isLoadingStatus } = useScanStatus(slug)

  // Flag: next scan completion should trigger an auto-analyze (set after upload).
  const analyzeAfterNextScanRef = useRef(false)

  // Analyze-folder mutation (used to kick off analysis after upload-triggered scan).
  const analyzeFolderMutation = useAnalyzeFolder(slug || '')

  // Subscribe to real-time scan progress
  const progressState = useScanProgress(slug, {
    enabled: !!slug,
    onScanCompleted: () => {
      // Invalidate caches when scan completes
      if (slug) {
        invalidateCache.invalidateAll(slug)
      }
      // If this scan was triggered by an upload, chain into analyze.
      if (analyzeAfterNextScanRef.current) {
        analyzeAfterNextScanRef.current = false
        analyzeFolderMutation.mutate({ force: false })
      }
    },
  })

  // Trigger scan mutation
  const triggerScanMutation = useTriggerScan()
  const invalidateCache = useInvalidateScanCache()

  // Handle manual scan trigger
  const handleTriggerScan = () => {
    if (slug) {
      triggerScanMutation.mutate(slug)
    }
  }

  // Handle upload success — invalidate import tree, kick off a scan, and
  // queue an analyze-folder once that scan completes.
  const handleUploadSuccess = useCallback(() => {
    if (!slug) return
    queryClient.invalidateQueries({
      queryKey: importTreeKeys.byLibrary(slug),
    })
    analyzeAfterNextScanRef.current = true
    triggerScanMutation.mutate(slug)
  }, [slug, queryClient, triggerScanMutation])

  // Update document title when library loads
  useEffect(() => {
    if (library) {
      document.title = `Beet Web Manager - Import: ${library.name}`
    }
    return () => {
      document.title = 'beet it'
    }
  }, [library])

  // Loading state
  if (isLoadingLibrary || isLoadingStatus) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  // Error state
  if (libraryError) {
    return (
      <div className="text-center py-12">
        <p className="text-destructive">Failed to load library</p>
        <p className="text-muted-foreground text-sm mt-2">
          {libraryError instanceof Error ? libraryError.message : 'Unknown error'}
        </p>
      </div>
    )
  }

  // No library found
  if (!library) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Library not found</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Nested route outlet - renders sub-pages */}
      <Outlet
        context={{
          slug: slug!,
          library,
          statusData,
          progressState,
          handleTriggerScan,
          isTriggeringScan: triggerScanMutation.isPending,
          handleUploadSuccess,
          selectedPath,
          setSelectedPath,
          handleFolderDeleted,
        }}
      />
    </div>
  )
}

// Export context type for child pages
export interface ImportDetailContext {
  slug: string
  library: Library
  statusData: ReturnType<typeof useScanStatus>['data']
  progressState: ReturnType<typeof useScanProgress>
  handleTriggerScan: () => void
  isTriggeringScan: boolean
  handleUploadSuccess: () => void
  selectedPath: string | null
  setSelectedPath: (path: string | null) => void
  handleFolderDeleted: (deletedPath: string) => void
}
