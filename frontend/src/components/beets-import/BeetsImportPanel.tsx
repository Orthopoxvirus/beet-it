import { useState, useCallback, useMemo, useEffect, useRef, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import AlbumListCard from './AlbumListCard'
import CandidateDetailsCard from './CandidateDetailsCard'
import { useAudioOpJobs } from './AudioOpJobsProvider'
import InProgressBox, { type InProgressAlbum } from './InProgressBox'
import DoneBox, { type DoneAlbum } from './DoneBox'
import { UpgradeComparison } from "./UpgradeComparison"
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { useImportTree, useDeleteImportFolder, importTreeKeys } from '@/hooks/useImportTree'
import { scanKeys } from '@/hooks/useScanStatus'
import {
  useAnalyzeAlbum,
  useBeetsAnalysisCache,
  useCacheStatus,
  useAddManualCandidate,
  useAnalysisQueue,
  useAnalyzeFolder,
  beetsAnalysisKeys,
} from '@/hooks/useBeetsAnalysis'
import { useBeetsImport, useBulkImportStatus } from '@/hooks/useBeetsImport'
import { useLibraryConfigBySlug, getImportMode } from '@/hooks/useConfig'
import {
  BeetsImportApiError,
  convertAudio,
  removeDuplicateWavs,
} from '@/api/beets-import'
import type {
  AlbumListItem,
  AlbumStage,
  AnalyzeAlbumResponse,
  AudioOpActiveStatus,
  Candidate,
  ConvertAudioParams,
  ExistingAlbumInfo,
  IncomingAlbumInfo,
} from '@/types/beets-import'
import type { ImportFolderNode } from '@/types/import-tree'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

// ============================================================================
// Types
// ============================================================================

interface BeetsImportPanelProps {
  /** Library slug to fetch and analyze albums for */
  librarySlug: string
  /** Optional CSS class name */
  className?: string
  /**
   * Controlled selected album path (absolute). When provided, the panel does
   * not own selection state and reports changes via {@link onSelectPath}.
   * Omit for the standalone /beets page, which keeps selection internal.
   */
  selectedPath?: string | null
  /** Notified whenever the selected album changes (controlled or not). */
  onSelectPath?: (path: string | null) => void
  /**
   * Extra content rendered between the album list and the candidate details
   * card. The combined import view slots its batch editor and local-album
   * cards here so the on-page order matches the design.
   */
  middleSlot?: ReactNode
  /**
   * Controlled selected folder (relative to import root). When a folder is
   * selected, the combined view batch-shows every album inside it. The panel
   * itself only forwards this to the album list; the parent owns the state.
   */
  selectedFolder?: string | null
  /** Notified when a folder group is selected from the album list. */
  onSelectFolder?: (folder: string) => void
  /**
   * Notified whenever the displayed analysis result changes, so a parent can
   * render the local-album summary in its own card (combined import view).
   */
  onAnalysisChange?: (analysis: AnalyzeAlbumResponse | null) => void
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Extract album folders from the import tree.
 * Recursively collects all leaf nodes (albums) from the tree structure.
 */
function extractAlbumFolders(nodes: ImportFolderNode[]): ImportFolderNode[] {
  const albums: ImportFolderNode[] = []

  function collectAlbums(nodeList: ImportFolderNode[]) {
    for (const node of nodeList) {
      if (node.isAlbum || node.isMultiDiscParent) {
        albums.push(node)
      }
      // Also recurse into children to find nested albums
      if (node.children.length > 0) {
        collectAlbums(node.children)
      }
    }
  }

  collectAlbums(nodes)
  return albums
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * Main panel for the Beets Import tab.
 * Displays album list and candidate details in a responsive layout.
 */
export default function BeetsImportPanel({
  librarySlug,
  className,
  selectedPath: controlledSelectedPath,
  onSelectPath,
  middleSlot,
  selectedFolder = null,
  onSelectFolder,
  onAnalysisChange,
}: BeetsImportPanelProps) {
  // -------------------------------------------------------------------------
  // State
  // -------------------------------------------------------------------------

  // Selection can be controlled by a parent (combined import view) or owned
  // internally (standalone /beets page). Refs keep the setter identity stable
  // so the existing handlers don't need it in their dependency lists.
  const [internalSelectedPath, setInternalSelectedPath] = useState<string | null>(null)
  const isControlled = controlledSelectedPath !== undefined
  const isControlledRef = useRef(isControlled)
  const onSelectPathRef = useRef(onSelectPath)
  useEffect(() => {
    isControlledRef.current = isControlled
    onSelectPathRef.current = onSelectPath
  }, [isControlled, onSelectPath])

  const selectedPath = isControlled ? controlledSelectedPath : internalSelectedPath
  const setSelectedPath = useCallback((path: string | null) => {
    onSelectPathRef.current?.(path)
    if (!isControlledRef.current) setInternalSelectedPath(path)
  }, [])

  // Keep the analysis-change callback identity-stable so the notifying effect
  // below doesn't refire when the parent re-renders.
  const onAnalysisChangeRef = useRef(onAnalysisChange)
  useEffect(() => {
    onAnalysisChangeRef.current = onAnalysisChange
  }, [onAnalysisChange])

  // Path currently being analyzed (to track loading state per-album)
  const [analyzingPath, setAnalyzingPath] = useState<string | null>(null)

  // Albums dispatched by a folder-level analyze, shown with an optimistic
  // spinner the instant the folder action is clicked. The analysis queue poll
  // only re-activates once it observes server-side activity, so without this
  // the rows would sit inert until a manual reload. Each path clears when its
  // mutation settles, at which point its cached result flips the row to
  // "analyzed".
  const [folderAnalyzingPaths, setFolderAnalyzingPaths] = useState<Set<string>>(
    new Set()
  )

  // Current analysis result to display
  const [currentAnalysis, setCurrentAnalysis] = useState<AnalyzeAlbumResponse | null>(null)

  // Surface the displayed analysis to a parent (combined view renders the
  // local-album summary in its own card).
  useEffect(() => {
    onAnalysisChangeRef.current?.(currentAnalysis)
  }, [currentAnalysis])

  // Analysis error
  const [analysisError, setAnalysisError] = useState<string | null>(null)

  // WAV→FLAC convert / duplicate-WAV cleanup running on the selected album.
  // When the combined import view mounts the shared registry (sharedJobs), it
  // owns the job lifecycle (background polling + toasts, per-album state) and
  // these locals are only the fallback for the standalone /beets page.
  const sharedJobs = useAudioOpJobs()
  const [isAudioOpRunning, setIsAudioOpRunning] = useState(false)
  const [audioOpError, setAudioOpError] = useState<string | null>(null)

  // Track which candidate index was chosen for import (for highlighting)
  const [chosenCandidateIndex, setChosenCandidateIndex] = useState<number | null>(null)

  // Pending duplicate-album confirmation: populated when POST /import returns
  // 409 ALBUM_ALREADY_EXISTS so we can ask the user whether to upgrade the
  // existing entry or cancel.
  const [duplicatePrompt, setDuplicatePrompt] = useState<
    | {
        candidate: Candidate
        albumPath: string
        existing: ExistingAlbumInfo
        incoming: IncomingAlbumInfo | null
      }
    | null
  >(null)

  // Error surfaced inside the duplicate dialog when "Delete Incoming" fails.
  const [deleteIncomingError, setDeleteIncomingError] = useState<string | null>(
    null
  )

  // -------------------------------------------------------------------------
  // Data Fetching
  // -------------------------------------------------------------------------

  // Fetch the import folder tree to get album list
  const {
    data: importTree,
    isLoading: isLoadingTree,
    error: treeError,
  } = useImportTree(librarySlug)

  // Mutation for analyzing albums
  const analyzeAlbum = useAnalyzeAlbum(librarySlug)

  // Mutation for deleting album folders from the import area
  const deleteFolder = useDeleteImportFolder(librarySlug)

  // Mutation for adding manual candidates
  const addManualCandidate = useAddManualCandidate(librarySlug, selectedPath ?? '')

  // Cache utilities for quick access to previous results
  const analysisCache = useBeetsAnalysisCache(librarySlug)

  // Analysis queue status
  const { data: queueData } = useAnalysisQueue(librarySlug, {
    // Only poll when there are items in the queue
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data) return 3000
      return data.queueDepth > 0 || data.activeCount > 0 ? 3000 : false
    },
  })

  // Mutation for bulk analysis
  const analyzeFolder = useAnalyzeFolder(librarySlug)

  // Track analyze-all feedback message
  const [analyzeFolderMessage, setAnalyzeFolderMessage] = useState<string | null>(null)

  // Import functionality
  const beetsImport = useBeetsImport(librarySlug)

  // Fetch bulk import status on mount
  const { data: bulkImportStatus } = useBulkImportStatus(librarySlug)

  // Fetch library config to determine import mode
  const { data: libraryConfig } = useLibraryConfigBySlug(librarySlug)
  const importMode = getImportMode(libraryConfig)

  // Resume polling for in-progress jobs on mount
  useEffect(() => {
    if (bulkImportStatus) {
      beetsImport.resumePollingForInProgressJobs(bulkImportStatus)
    }
  }, [bulkImportStatus, beetsImport.resumePollingForInProgressJobs])

  // -------------------------------------------------------------------------
  // Derived Data
  // -------------------------------------------------------------------------

  // Base import path (absolute, no trailing slash) for computing absolute album paths.
  // The import tree returns relative node paths; bulk import status uses absolute paths.
  // We normalise everything to absolute paths so all Map lookups are consistent.
  const importBasePath = (importTree?.importPath ?? '').replace(/\/$/, '')

  // Extract album paths for cache status check (absolute)
  const albumPaths: string[] = useMemo(() => {
    if (!importTree?.children) return []
    const albumNodes = extractAlbumFolders(importTree.children)
    return albumNodes.map((node) => `${importBasePath}/${node.path}`)
  }, [importTree?.children, importBasePath])

  // Fetch backend cache status for all albums
  // This tells us which albums have cached analysis results on the server
  const { data: cacheStatusData } = useCacheStatus(librarySlug, albumPaths, {
    enabled: albumPaths.length > 0,
  })

  // When an album leaves the active-analysis set (i.e. the queue finished
  // processing it) its result has just been written to the backend cache.
  // Invalidate cacheStatus so the UI re-fetches and the album flips to the
  // analyzed state without requiring a manual refresh.
  const queryClient = useQueryClient()
  const prevActiveAndQueuedRef = useRef<Set<string>>(new Set())
  useEffect(() => {
    const current = new Set<string>()
    if (queueData?.activeItems) {
      for (const item of queueData.activeItems) current.add(item.albumPath)
    }
    if (queueData?.queuedItems) {
      for (const item of queueData.queuedItems) current.add(item.albumPath)
    }
    const prev = prevActiveAndQueuedRef.current
    const completed: string[] = []
    for (const path of prev) {
      if (!current.has(path)) completed.push(path)
    }
    prevActiveAndQueuedRef.current = current
    if (completed.length > 0) {
      queryClient.invalidateQueries({
        queryKey: beetsAnalysisKeys.cacheStatus(librarySlug),
      })
    }
  }, [queueData?.activeItems, queueData?.queuedItems, queryClient, librarySlug])

  // Map of album path to backend cache status (defaults to false if API fails)
  const backendCacheStatus: Record<string, boolean> = useMemo(
    () => cacheStatusData?.cacheStatus ?? {},
    [cacheStatusData?.cacheStatus]
  )

  // Build queue status map (album path -> queue position)
  const queueStatus: Record<string, number> = useMemo(() => {
    if (!queueData?.queuedItems) return {}
    const status: Record<string, number> = {}
    for (const item of queueData.queuedItems) {
      status[item.albumPath] = item.position
    }
    return status
  }, [queueData?.queuedItems])

  // Track which albums are actively being analyzed
  const activeAnalysisPaths: Set<string> = useMemo(() => {
    if (!queueData?.activeItems) return new Set()
    return new Set(queueData.activeItems.map((item) => item.albumPath))
  }, [queueData?.activeItems])

  // Get album metadata from import tree nodes (keyed by absolute path)
  const albumMetadataMap = useMemo(() => {
    const map: Record<string, { name: string; artist: string | null; album: string | null }> = {}
    if (!importTree?.children) return map

    const albumNodes = extractAlbumFolders(importTree.children)
    for (const node of albumNodes) {
      const absPath = `${importBasePath}/${node.path}`
      const cached = analysisCache.getCached(absPath)
      map[absPath] = {
        name: node.name,
        artist: cached?.localAlbum.artist || null,
        album: cached?.localAlbum.album || null,
      }
    }
    return map
  }, [importTree?.children, analysisCache, importBasePath])

  // Determine import state for each album (pending, in_progress, done).
  // Both activeJobs (keyed by absolute path) and bulkImportStatus (keyed by absolute path)
  // use the same path format, so lookups are consistent.
  const albumImportStates = useMemo(() => {
    const states: Record<string, 'pending' | 'in_progress' | 'done'> = {}

    // From active jobs being tracked locally (keys are absolute paths)
    beetsImport.activeJobs.forEach((job, albumPath) => {
      if (job.status === 'completed') {
        states[albumPath] = 'done'
      } else if (job.status === 'pending' || job.status === 'in_progress') {
        states[albumPath] = 'in_progress'
      }
    })

    // From bulk status response (for albums not yet tracked locally)
    if (bulkImportStatus?.albums) {
      Object.entries(bulkImportStatus.albums).forEach(([path, state]) => {
        if (!states[path]) {
          if (state.state === 'in_progress') {
            states[path] = 'in_progress'
          } else if (state.state === 'done') {
            states[path] = 'done'
          }
        }
      })
    }

    return states
  }, [beetsImport.activeJobs, bulkImportStatus?.albums])

  // Convert import tree nodes to album list items (pending only).
  // Use absolute paths so that lookups against activeJobs and bulkImportStatus match.
  const albumItems: AlbumListItem[] = useMemo(() => {
    if (!importTree?.children) return []

    const albumNodes = extractAlbumFolders(importTree.children)

    return albumNodes
      .filter((node) => {
        const absPath = `${importBasePath}/${node.path}`
        // Exclude albums that are in progress or done
        const importState = albumImportStates[absPath]
        return !importState || importState === 'pending'
      })
      .map((node) => {
        const absPath = `${importBasePath}/${node.path}`
        const cached = analysisCache.getCached(absPath)
        // Check if currently analyzing: locally tracked (single disc), from the
        // queue poll, or optimistically marked by a folder-level analyze.
        const isCurrentlyAnalyzing =
          analyzingPath === absPath ||
          activeAnalysisPaths.has(absPath) ||
          folderAnalyzingPaths.has(absPath)

        // Determine stage based on analysis and import state.
        // An album counts as analyzed when results are in the local TanStack
        // cache OR cached on the backend — the local cache is in-memory and
        // lost on navigation/reload, while the backend cache persists.
        let stage: AlbumStage = 'none'
        const importState = albumImportStates[absPath]

        if (importState === 'done') {
          stage = 'imported'
        } else if (importState === 'in_progress') {
          stage = 'chosen'
        } else if (!!cached || backendCacheStatus[absPath]) {
          stage = 'analyzed'
        }

        // Parent folder the album lives in, relative to the import root.
        // node.path is import-root-relative (e.g. "Artist/Album"); the folder
        // is everything up to the last segment, or null for a top-level album.
        const slash = node.path.lastIndexOf('/')
        const folder = slash > 0 ? node.path.slice(0, slash) : null

        return {
          id: absPath,
          path: absPath, // absolute path — consistent with activeJobs and bulkImportStatus keys
          name: node.name,
          folder,
          // Extract metadata from cached analysis if available
          artist: cached?.localAlbum.artist || null,
          album: cached?.localAlbum.album || null,
          stage,
          isAnalyzing: isCurrentlyAnalyzing,
          isMultiDisc: node.isMultiDiscParent,
        }
      })
  }, [importTree?.children, analysisCache, analyzingPath, activeAnalysisPaths, folderAnalyzingPaths, albumImportStates, importBasePath, backendCacheStatus])

  // Albums in progress (for InProgressBox)
  const inProgressAlbums: InProgressAlbum[] = useMemo(() => {
    const albums: InProgressAlbum[] = []
    let queuePosition = 1

    // From active jobs being tracked locally
    beetsImport.activeJobs.forEach((job, albumPath) => {
      if (job.status === 'pending' || job.status === 'in_progress') {
        const metadata = albumMetadataMap[albumPath] || { name: albumPath.split('/').pop() || albumPath, artist: null, album: null }
        albums.push({
          path: albumPath,
          name: metadata.name,
          artist: metadata.artist,
          album: metadata.album,
          jobState: job,
          queuePosition: job.status === 'pending' ? queuePosition++ : undefined,
        })
      }
    })

    // From bulk status (for jobs not tracked locally yet)
    if (bulkImportStatus?.albums) {
      Object.entries(bulkImportStatus.albums).forEach(([path, state]) => {
        if (state.state === 'in_progress' && !beetsImport.activeJobs.has(path)) {
          const metadata = albumMetadataMap[path] || { name: path.split('/').pop() || path, artist: null, album: null }
          albums.push({
            path,
            name: metadata.name,
            artist: metadata.artist,
            album: metadata.album,
            jobState: {
              jobId: state.jobId || '',
              albumPath: path,
              status: 'in_progress',
              startedAt: state.startedAt,
            },
          })
        }
      })
    }

    return albums
  }, [beetsImport.activeJobs, bulkImportStatus?.albums, albumMetadataMap])

  // Done albums (for DoneBox) - only in copy mode
  const doneAlbums: DoneAlbum[] = useMemo(() => {
    const albums: DoneAlbum[] = []

    // From active jobs that completed
    beetsImport.activeJobs.forEach((job, albumPath) => {
      if (job.status === 'completed' && job.completedAt) {
        const metadata = albumMetadataMap[albumPath] || { name: albumPath.split('/').pop() || albumPath, artist: null, album: null }
        albums.push({
          path: albumPath,
          name: metadata.name,
          artist: metadata.artist,
          album: metadata.album,
          completedAt: job.completedAt,
          destinationPath: job.destinationPath,
        })
      }
    })

    // From bulk status
    if (bulkImportStatus?.albums) {
      Object.entries(bulkImportStatus.albums).forEach(([path, state]) => {
        if (state.state === 'done' && state.completedAt && !beetsImport.activeJobs.has(path)) {
          const metadata = albumMetadataMap[path] || { name: path.split('/').pop() || path, artist: null, album: null }
          albums.push({
            path,
            name: metadata.name,
            artist: metadata.artist,
            album: metadata.album,
            completedAt: state.completedAt,
            destinationPath: state.destinationPath,
          })
        }
      })
    }

    return albums
  }, [beetsImport.activeJobs, bulkImportStatus?.albums, albumMetadataMap])

  // -------------------------------------------------------------------------
  // Handlers
  // -------------------------------------------------------------------------

  /**
   * Handle album selection from the list.
   * If the album has cached results, display them immediately.
   */
  const handleAlbumSelect = useCallback(
    async (path: string) => {
      setSelectedPath(path)
      setAnalysisError(null)

      // Reset manual candidate mutation state when switching albums
      addManualCandidate.reset()

      // Check if we have cached results for this album in the local TanStack cache
      const cached = analysisCache.getCached(path)
      if (cached) {
        setCurrentAnalysis(cached)
      } else if (backendCacheStatus[path]) {
        // Backend has a cached result (e.g. from "Analyze All") — fetch it.
        // The analyze endpoint returns immediately on a cache hit, no polling needed.
        setAnalyzingPath(path)
        try {
          const result = await analyzeAlbum.mutateAsync({ albumPath: path, force: false })
          setCurrentAnalysis(result)
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Failed to load cached results'
          setAnalysisError(message)
        } finally {
          setAnalyzingPath(null)
        }
      } else {
        // No cached data anywhere — clear the display
        setCurrentAnalysis(null)
      }
    },
    [analysisCache, addManualCandidate, backendCacheStatus, analyzeAlbum]
  )

  // If the selected album finishes analyzing (via the bulk queue) while the
  // user is still sitting on it, pull in the freshly-cached result so the
  // candidate panel lights up without a manual click.
  useEffect(() => {
    if (!selectedPath) return
    if (currentAnalysis) return
    if (analyzingPath === selectedPath) return
    if (!backendCacheStatus[selectedPath]) return
    // Backend just reported a cached result — fetch it.
    let cancelled = false
    setAnalyzingPath(selectedPath)
    analyzeAlbum
      .mutateAsync({ albumPath: selectedPath, force: false })
      .then((result) => {
        if (!cancelled) setCurrentAnalysis(result)
      })
      .catch((err) => {
        if (!cancelled) {
          const message =
            err instanceof Error ? err.message : 'Failed to load cached results'
          setAnalysisError(message)
        }
      })
      .finally(() => {
        if (!cancelled) setAnalyzingPath(null)
      })
    return () => {
      cancelled = true
    }
  }, [
    selectedPath,
    backendCacheStatus,
    currentAnalysis,
    analyzingPath,
    analyzeAlbum,
  ])

  /**
   * Handle analysis trigger (clicking the disc icon).
   * For already-analyzed albums, this triggers re-analysis.
   */
  const handleAnalyzeClick = useCallback(
    async (path: string, forceReanalyze = false) => {
      // Don't allow multiple simultaneous analyses
      if (analyzingPath) return

      // Clear any previous error
      setAnalysisError(null)

      // Check before invalidating (invalidate clears the cache)
      const hadCachedResult = analysisCache.hasCached(path)

      // If this album was already analyzed, invalidate local cache for re-analysis
      if (hadCachedResult) {
        analysisCache.invalidate(path)
      }

      // Auto-select the album being analyzed
      setSelectedPath(path)
      setAnalyzingPath(path)
      setCurrentAnalysis(null)

      try {
        // Force a fresh backend analysis when re-analyzing explicitly, or when
        // a cached result was being shown (the user expects new results).
        const result = await analyzeAlbum.mutateAsync({
          albumPath: path,
          force: hadCachedResult || forceReanalyze,
        })
        setCurrentAnalysis(result)
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Analysis failed'
        setAnalysisError(message)
      } finally {
        setAnalyzingPath(null)
      }
    },
    [analyzingPath, analysisCache, analyzeAlbum]
  )

  /**
   * Refresh everything that depends on the album's on-disk files after a WAV
   * convert / dedup op: the file tree + import-item table (invalidate queries)
   * and the Local Album card (force a fresh analysis so the summary + buttons
   * reflect the new FLAC/WAV state).
   */
  const refreshAfterAudioOp = useCallback(async () => {
    queryClient.invalidateQueries({ queryKey: importTreeKeys.byLibrary(librarySlug) })
    queryClient.invalidateQueries({ queryKey: [...scanKeys.importItems(), librarySlug] })
    if (selectedPath) {
      analysisCache.invalidate(selectedPath)
      await handleAnalyzeClick(selectedPath, true)
    }
  }, [queryClient, librarySlug, selectedPath, analysisCache, handleAnalyzeClick])

  /**
   * Convert the selected album's WAV files to FLAC, optionally deleting the
   * originals, then refresh the card + file tree.
   */
  const handleConvertAudio = useCallback(
    async (params: ConvertAudioParams) => {
      if (!selectedPath) return
      // Shared registry: fire-and-forget background job (the provider polls it,
      // refreshes on completion, and toasts). Falls through to the local path
      // only on the standalone page where no provider is mounted.
      if (sharedJobs) {
        sharedJobs.startConvert(selectedPath, params)
        return
      }
      if (isAudioOpRunning) return
      const { sourceFormat, targetFormat, deleteOriginals } = params
      setAudioOpError(null)
      setIsAudioOpRunning(true)
      try {
        await convertAudio(
          librarySlug,
          selectedPath,
          sourceFormat,
          targetFormat,
          deleteOriginals
        )
        await refreshAfterAudioOp()
      } catch (err) {
        setAudioOpError(err instanceof Error ? err.message : 'Conversion failed')
      } finally {
        setIsAudioOpRunning(false)
      }
    },
    [selectedPath, sharedJobs, isAudioOpRunning, librarySlug, refreshAfterAudioOp]
  )

  /**
   * Remove the selected album's duplicate WAVs (those with a FLAC twin), then
   * refresh the card + file tree.
   */
  const handleRemoveDuplicateWavs = useCallback(async () => {
    if (!selectedPath) return
    if (sharedJobs) {
      sharedJobs.startDedupe(selectedPath)
      return
    }
    if (isAudioOpRunning) return
    setAudioOpError(null)
    setIsAudioOpRunning(true)
    try {
      await removeDuplicateWavs(librarySlug, selectedPath)
      await refreshAfterAudioOp()
    } catch (err) {
      setAudioOpError(err instanceof Error ? err.message : 'Cleanup failed')
    } finally {
      setIsAudioOpRunning(false)
    }
  }, [selectedPath, sharedJobs, isAudioOpRunning, librarySlug, refreshAfterAudioOp])

  // When the *selected* album's shared convert/dedup finishes, refresh its card
  // (re-analyze) so the Local Album summary + action buttons reflect the new
  // on-disk files. Non-selected albums are covered by the provider's query
  // invalidation; only the open candidate card needs this extra nudge.
  const prevSelectedConvertingRef = useRef(false)
  useEffect(() => {
    if (!sharedJobs || !selectedPath) {
      prevSelectedConvertingRef.current = false
      return
    }
    const active = sharedJobs.isActive(selectedPath)
    if (prevSelectedConvertingRef.current && !active) {
      refreshAfterAudioOp()
    }
    prevSelectedConvertingRef.current = active
  }, [sharedJobs, selectedPath, refreshAfterAudioOp])

  /**
   * Handle album deletion (trash icon, after confirmation).
   * The backend removes the folder from disk and purges its import items;
   * here we translate the absolute album path back to an import-root-relative
   * one, then clean up local caches and selection.
   */
  const handleDeleteAlbum = useCallback(
    async (absPath: string) => {
      const relPath = absPath.startsWith(`${importBasePath}/`)
        ? absPath.slice(importBasePath.length + 1)
        : absPath
      await deleteFolder.mutateAsync(relPath)

      // Drop the album's analysis result and refresh the backend cache map
      analysisCache.invalidate(absPath)
      queryClient.invalidateQueries({
        queryKey: beetsAnalysisKeys.cacheStatus(librarySlug),
      })

      // Clear the details panel if the deleted album was selected
      if (selectedPath === absPath) {
        setSelectedPath(null)
        setCurrentAnalysis(null)
        setAnalysisError(null)
        setChosenCandidateIndex(null)
      }
    },
    [importBasePath, deleteFolder, analysisCache, queryClient, librarySlug, selectedPath]
  )

  /**
   * Re-analyze every album inside a folder group. The backend has no
   * folder-scoped analyze endpoint, so we enqueue each album individually with
   * force=true (dropping any cached result first, mirroring the per-album
   * disc). Albums already analyzing or queued are skipped to avoid
   * double-enqueueing them.
   *
   * Each dispatched album is marked optimistically so its row shows the
   * analyzing spinner immediately — the queue poll alone can't be relied on for
   * feedback because it idles once it sees no activity. When a mutation settles
   * we drop the optimistic mark; its now-cached result flips the row to
   * "analyzed" without a reload. We also nudge the queue query so positions and
   * the active count surface while the batch runs.
   */
  const handleAnalyzeFolder = useCallback(
    (folder: string) => {
      const folderAlbums = albumItems.filter(
        (a) =>
          a.folder === folder &&
          !a.isAnalyzing &&
          queueStatus[a.path] === undefined
      )
      if (folderAlbums.length === 0) return

      // Optimistically mark every dispatched album as analyzing for instant feedback.
      setFolderAnalyzingPaths((prev) => {
        const next = new Set(prev)
        for (const album of folderAlbums) next.add(album.path)
        return next
      })
      const clearOptimistic = (path: string) =>
        setFolderAnalyzingPaths((prev) => {
          if (!prev.has(path)) return prev
          const next = new Set(prev)
          next.delete(path)
          return next
        })

      for (const album of folderAlbums) {
        // Force re-analysis of every album, including ones already analyzed —
        // invalidate the local cache first so a stale result doesn't linger.
        analysisCache.invalidate(album.path)
        analyzeAlbum
          .mutateAsync({ albumPath: album.path, force: true })
          .catch(() => {
            // One album failing shouldn't abort the batch; the queue surfaces
            // per-album state and the user can retry individually.
          })
          .finally(() => clearOptimistic(album.path))
      }

      // Wake the queue poll so active/queued positions surface while we work.
      queryClient.invalidateQueries({
        queryKey: beetsAnalysisKeys.analysisQueue(librarySlug),
      })
    },
    [albumItems, analyzeAlbum, analysisCache, queueStatus, queryClient, librarySlug]
  )

  /**
   * Delete a whole folder group recursively. The delete endpoint takes an
   * import-root-relative path, which is exactly the folder key, so no path
   * translation is needed. Clears the details panel if the selected album
   * lived inside the deleted folder.
   */
  const handleDeleteFolder = useCallback(
    async (folder: string) => {
      await deleteFolder.mutateAsync(folder)
      queryClient.invalidateQueries({
        queryKey: beetsAnalysisKeys.cacheStatus(librarySlug),
      })
      const folderPrefix = `${importBasePath}/${folder}/`
      if (selectedPath && selectedPath.startsWith(folderPrefix)) {
        setSelectedPath(null)
        setCurrentAnalysis(null)
        setAnalysisError(null)
        setChosenCandidateIndex(null)
      }
    },
    [deleteFolder, queryClient, librarySlug, importBasePath, selectedPath, setSelectedPath]
  )

  /**
   * Handle adding a manual candidate.
   * Calls the mutation and updates currentAnalysis on success.
   */
  const handleAddManualCandidate = useCallback(
    (link: string) => {
      addManualCandidate.mutate(link, {
        onSuccess: (data) => {
          // Update currentAnalysis with the new manual candidate
          setCurrentAnalysis((prev) => {
            if (!prev) return prev

            // Filter out existing manual candidate from same provider (deduplication)
            const filteredManual = (prev.manualCandidates ?? []).filter(
              (c: Candidate) => c.source.toLowerCase() !== data.provider
            )

            return {
              ...prev,
              manualCandidates: [...filteredManual, data.candidate],
            }
          })
        },
      })
    },
    [addManualCandidate]
  )

  /**
   * Handle "Analyze All" button click.
   * Triggers bulk analysis for all albums in the import folder.
   */
  const handleAnalyzeAll = useCallback(async () => {
    setAnalyzeFolderMessage(null)

    try {
      const result = await analyzeFolder.mutateAsync({ force: false })
      // Show feedback message
      setAnalyzeFolderMessage(result.message)
      // Clear the message after 5 seconds
      setTimeout(() => setAnalyzeFolderMessage(null), 5000)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to analyze folder'
      setAnalyzeFolderMessage(`Error: ${message}`)
      // Clear error message after 5 seconds
      setTimeout(() => setAnalyzeFolderMessage(null), 5000)
    }
  }, [analyzeFolder])

  /**
   * Advance to the next pending album after a successful import enqueue.
   */
  const advanceToNextAlbum = useCallback(
    (importedPath: string) => {
      const currentIndex = albumItems.findIndex((a) => a.path === importedPath)
      if (currentIndex < 0) return
      const remainingAlbums = albumItems.filter((a) => a.path !== importedPath)
      if (remainingAlbums.length === 0) {
        setSelectedPath(null)
        setCurrentAnalysis(null)
        setChosenCandidateIndex(null)
        return
      }
      const nextIndex =
        currentIndex >= remainingAlbums.length ? 0 : currentIndex
      const nextAlbum = remainingAlbums[nextIndex]
      if (nextAlbum) {
        handleAlbumSelect(nextAlbum.path)
        setChosenCandidateIndex(null)
      }
    },
    [albumItems, handleAlbumSelect]
  )

  /**
   * Fire the actual POST /import call. Shared between the initial click and
   * the "upgrade" confirmation path so duplicate handling stays consistent.
   */
  const dispatchImport = useCallback(
    (
      candidate: Candidate,
      albumPath: string,
      replaceExisting: boolean
    ) => {
      beetsImport.startImport(
        { albumPath, candidate, replaceExisting },
        {
          onSuccess: () => {
            advanceToNextAlbum(albumPath)
          },
          onError: (error) => {
            // Detect ALBUM_ALREADY_EXISTS so we can surface the upgrade dialog
            // instead of bubbling an opaque 409.
            if (
              error instanceof BeetsImportApiError &&
              error.status === 409 &&
              error.errorCode === 'ALBUM_ALREADY_EXISTS' &&
              error.data &&
              typeof error.data === 'object' &&
              'existing' in (error.data as Record<string, unknown>)
            ) {
              const data = error.data as {
                existing: ExistingAlbumInfo
                incoming?: IncomingAlbumInfo
              }
              setChosenCandidateIndex(null)
              setDuplicatePrompt({
                candidate,
                albumPath,
                existing: data.existing,
                incoming: data.incoming ?? null,
              })
              return
            }
            console.error('[BeetsImportPanel] Import failed:', error)
            setChosenCandidateIndex(null)
          },
        }
      )
    },
    [beetsImport, advanceToNextAlbum]
  )

  /**
   * Handle import button click on a candidate.
   * Triggers import and auto-advances to next album.
   */
  const handleImportClick = useCallback(
    (candidate: Candidate) => {
      if (!selectedPath || !currentAnalysis) return

      // Find the index of this candidate in the merged list
      const allCandidates = [
        ...(currentAnalysis.manualCandidates ?? []),
        ...currentAnalysis.candidates,
      ]
      const candidateIndex = allCandidates.findIndex(
        (c) =>
          c.source === candidate.source &&
          c.sourceId === candidate.sourceId &&
          c.artist === candidate.artist &&
          c.album === candidate.album
      )

      // Set the chosen candidate index for highlighting
      setChosenCandidateIndex(candidateIndex >= 0 ? candidateIndex : null)

      dispatchImport(candidate, selectedPath, false)
    },
    [selectedPath, currentAnalysis, dispatchImport]
  )

  /**
   * Import an album as-is: no candidate, keep the files' existing tags.
   * The backend skips the duplicate check in this mode, so there's no upgrade
   * prompt to handle here.
   */
  const handleImportAsIs = useCallback(
    (albumPath: string) => {
      beetsImport.startImport(
        { albumPath, importAsIs: true },
        {
          onSuccess: () => {
            advanceToNextAlbum(albumPath)
          },
          onError: (error) => {
            console.error('[BeetsImportPanel] Import-as-is failed:', error)
          },
        }
      )
    },
    [beetsImport, advanceToNextAlbum]
  )

  const handleConfirmUpgrade = useCallback(() => {
    if (!duplicatePrompt) return
    const { candidate, albumPath } = duplicatePrompt
    setDuplicatePrompt(null)
    dispatchImport(candidate, albumPath, true)
  }, [duplicatePrompt, dispatchImport])

  const handleCancelUpgrade = useCallback(() => {
    setDuplicatePrompt(null)
    setDeleteIncomingError(null)
    beetsImport.reset()
  }, [beetsImport])

  /**
   * Delete the incoming album from the import folder straight from the
   * duplicate dialog. Reuses handleDeleteAlbum (folder removal + cache and
   * selection cleanup), then closes the dialog and resets the import state.
   * On failure the dialog stays open and surfaces the error.
   */
  const handleDeleteIncoming = useCallback(async () => {
    if (!duplicatePrompt) return
    setDeleteIncomingError(null)
    try {
      await handleDeleteAlbum(duplicatePrompt.albumPath)
      setDuplicatePrompt(null)
      beetsImport.reset()
    } catch (err) {
      setDeleteIncomingError(
        err instanceof Error
          ? err.message
          : 'Failed to delete the incoming album. Please try again.'
      )
    }
  }, [duplicatePrompt, handleDeleteAlbum, beetsImport])

  // Check if current album has an import in progress
  const currentAlbumImportState = selectedPath ? albumImportStates[selectedPath] : null
  const isImportInProgress = currentAlbumImportState === 'in_progress'

  // Per-album convert/dedup state from the shared registry (keyed by absolute
  // path). The tree shows a spinner on every converting album; the candidate
  // card's button spins only for the selected album — so switching albums no
  // longer drags the spinner along (the core fix for this view).
  const convertStatus: Record<string, AudioOpActiveStatus> = useMemo(() => {
    if (!sharedJobs) return {}
    const out: Record<string, AudioOpActiveStatus> = {}
    for (const [path, job] of Object.entries(sharedJobs.activeJobs)) {
      out[path] = job.status
    }
    return out
  }, [sharedJobs])
  const selectedAudioOpRunning = sharedJobs
    ? !!selectedPath && sharedJobs.isActive(selectedPath)
    : isAudioOpRunning

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  // Compute error message for album list
  const albumListError = treeError
    ? treeError instanceof Error
      ? treeError.message
      : 'Failed to load albums'
    : null

  // Calculate queue depth for display
  const queueDepth = queueData?.queueDepth ?? 0
  const activeCount = queueData?.activeCount ?? 0

  return (
    <div className={className}>
      {/* Analyze-all feedback message */}
      {analyzeFolderMessage && (
        <Alert
          variant={analyzeFolderMessage.startsWith('Error') ? 'destructive' : 'default'}
          className="mb-4"
        >
          <AlertDescription>{analyzeFolderMessage}</AlertDescription>
        </Alert>
      )}

      {/* Single full-width column: Albums, Candidate Details, In Progress, Done — top to bottom */}
      <div className="space-y-4">
        {/* Pending Albums Box */}
        <AlbumListCard
          albums={albumItems}
          selectedPath={selectedPath}
          onAlbumSelect={handleAlbumSelect}
          onAnalyzeClick={handleAnalyzeClick}
          onDeleteAlbum={handleDeleteAlbum}
          onImportAsIs={handleImportAsIs}
          isImporting={beetsImport.isPending}
          isLoading={isLoadingTree}
          error={albumListError}
          queueStatus={queueStatus}
          convertStatus={convertStatus}
          onAnalyzeAll={handleAnalyzeAll}
          isAnalyzingAll={analyzeFolder.isPending}
          queueDepth={queueDepth}
          activeCount={activeCount}
          onAnalyzeFolder={handleAnalyzeFolder}
          onDeleteFolder={handleDeleteFolder}
          selectedFolder={selectedFolder}
          onFolderSelect={onSelectFolder}
        />

        {/* Optional injected content (combined view: batch editor + local album) */}
        {middleSlot}

        {/* Candidate Details */}
        <CandidateDetailsCard
          analysisData={currentAnalysis}
          isAnalyzing={!!analyzingPath}
          error={analysisError}
          librarySlug={librarySlug}
          onAddManualCandidate={selectedPath ? handleAddManualCandidate : undefined}
          onReanalyze={selectedPath ? () => handleAnalyzeClick(selectedPath, true) : undefined}
          onConvertAudio={selectedPath ? handleConvertAudio : undefined}
          onRemoveDuplicateWavs={selectedPath ? handleRemoveDuplicateWavs : undefined}
          isAudioOpRunning={selectedAudioOpRunning}
          audioOpError={audioOpError}
          isAddingManualCandidate={addManualCandidate.isPending}
          manualCandidateError={addManualCandidate.error?.message ?? null}
          onImportClick={selectedPath && currentAnalysis ? handleImportClick : undefined}
          isImporting={beetsImport.isPending}
          chosenCandidateIndex={chosenCandidateIndex}
          isImportInProgress={isImportInProgress}
        />

        {/* In Progress Box */}
        <InProgressBox albums={inProgressAlbums} />

        {/* Done Box - only in copy mode */}
        {importMode === 'copy' && <DoneBox albums={doneAlbums} />}
      </div>

      {/* Upgrade-existing confirmation dialog with side-by-side comparison */}
      <AlertDialog
        open={duplicatePrompt !== null}
        onOpenChange={(open) => {
          if (!open) handleCancelUpgrade()
        }}
      >
        <AlertDialogContent className="max-w-xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Album already in library</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-3">
                <p>
                  <span className="font-medium">
                    {duplicatePrompt?.existing.artist}
                  </span>{' '}
                  —{' '}
                  <span className="font-medium">
                    {duplicatePrompt?.existing.album}
                  </span>{' '}
                  is already in your beets library
                  {duplicatePrompt?.existing.matchReason === 'mb_albumid'
                    ? ' (matched by MusicBrainz ID)'
                    : ' (matched by artist + album name)'}
                  .
                </p>
                <UpgradeComparison
                  existing={duplicatePrompt?.existing.stats ?? null}
                  incoming={duplicatePrompt?.incoming?.stats ?? null}
                />
                <p className="text-xs">
                  Upgrade replaces the existing files and database entry with
                  this import. Delete Incoming permanently removes the import
                  folder from disk. Cancel to keep what's already there.
                </p>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          {deleteIncomingError && (
            <p className="text-sm text-destructive">{deleteIncomingError}</p>
          )}
          <AlertDialogFooter>
            <Button
              variant="destructive"
              onClick={handleDeleteIncoming}
              disabled={deleteFolder.isPending}
              className="sm:mr-auto"
              data-testid="upgrade-delete-incoming-button"
            >
              {deleteFolder.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Deleting…
                </>
              ) : (
                'Delete Incoming'
              )}
            </Button>
            <AlertDialogCancel
              onClick={handleCancelUpgrade}
              disabled={deleteFolder.isPending}
            >
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmUpgrade}
              disabled={deleteFolder.isPending}
            >
              Upgrade
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
