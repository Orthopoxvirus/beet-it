import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  startImport,
  getImportJobStatus,
  getBulkImportStatus,
} from '@/api/beets-import'
import type {
  ImportJobRequest,
  ImportJobResponse,
  ImportJobStatusResponse,
  BulkImportStatusResponse,
  Candidate,
  ImportCandidate,
  ImportCandidateTrack,
} from '@/types/beets-import'
import { BeetsImportApiError } from '@/api/beets-import'
import { importTreeKeys } from './useImportTree'
import { scanKeys } from './useScanStatus'

// ============================================================================
// Query Keys
// ============================================================================

export const beetsImportKeys = {
  all: ['beets-import'] as const,
  byLibrary: (slug: string) => [...beetsImportKeys.all, slug] as const,
  bulkStatus: (slug: string) => [...beetsImportKeys.byLibrary(slug), 'bulk-status'] as const,
  jobStatus: (slug: string, jobId: string) =>
    [...beetsImportKeys.byLibrary(slug), 'job', jobId] as const,
}

// ============================================================================
// Polling Interval
// ============================================================================

const IMPORT_POLL_INTERVAL_MS = 2000

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Convert a Candidate from analysis results to an ImportCandidate for import request.
 */
export function candidateToImportCandidate(candidate: Candidate): ImportCandidate {
  return {
    source: candidate.source,
    sourceId: candidate.sourceId ?? undefined,
    artist: candidate.artist,
    album: candidate.album,
    year: candidate.year ?? undefined,
    coverUrl: candidate.coverUrl ?? undefined,
    tracks: candidate.tracks.map((track): ImportCandidateTrack => ({
      index: track.index,
      title: track.title,
      length: track.length ?? undefined,
      disc: track.disc ?? undefined,
      // Forward the paired file path so the backend applies each track's
      // metadata to the right file — essential for multi-disc releases.
      localPath: track.localPath ?? undefined,
    })),
  }
}

// ============================================================================
// Import Job State Tracking
// ============================================================================

/**
 * State for tracking active import jobs and their statuses.
 */
export interface ImportJobState {
  jobId: string
  albumPath: string
  status: ImportJobStatusResponse['status']
  startedAt?: string
  completedAt?: string
  destinationPath?: string
  error?: { code: string; message: string }
}

// ============================================================================
// Hooks
// ============================================================================

/**
 * Hook for fetching bulk import status on page load.
 * Returns the current import state for all albums in the library.
 */
export function useBulkImportStatus(
  librarySlug: string,
  options?: { enabled?: boolean }
) {
  return useQuery<BulkImportStatusResponse, Error>({
    queryKey: beetsImportKeys.bulkStatus(librarySlug),
    queryFn: () => getBulkImportStatus(librarySlug),
    enabled: options?.enabled !== false,
    staleTime: 30 * 1000, // 30 seconds
    refetchOnWindowFocus: false,
  })
}

/**
 * Hook for managing import jobs with polling support.
 *
 * Provides:
 * - startImport mutation to trigger import for an album/candidate pair
 * - Active job tracking with automatic status polling
 * - Integration with bulk status for hydration
 */
export function useBeetsImport(librarySlug: string) {
  const queryClient = useQueryClient()

  // Track active jobs being polled
  const [activeJobs, setActiveJobs] = useState<Map<string, ImportJobState>>(new Map())

  // Track polling intervals to clean up
  const pollingRefs = useRef<Map<string, NodeJS.Timeout>>(new Map())

  /**
   * Start polling for a job's status.
   */
  const startPolling = useCallback(
    (jobId: string, albumPath: string) => {
      // Don't start duplicate polling
      if (pollingRefs.current.has(jobId)) {
        return
      }

      console.log('[useBeetsImport] Starting polling for job:', jobId)

      const poll = async () => {
        try {
          const status = await getImportJobStatus(librarySlug, jobId)

          // Update job state
          setActiveJobs((prev) => {
            const updated = new Map(prev)
            updated.set(albumPath, {
              jobId,
              albumPath,
              status: status.status,
              startedAt: status.startedAt ?? undefined,
              completedAt: status.completedAt ?? undefined,
              destinationPath: status.destinationPath,
              error: status.error,
            })
            return updated
          })

          // Check for terminal state
          if (status.status === 'completed' || status.status === 'failed') {
            console.log('[useBeetsImport] Job reached terminal state:', status.status)

            // Stop polling
            const interval = pollingRefs.current.get(jobId)
            if (interval) {
              clearInterval(interval)
              pollingRefs.current.delete(jobId)
            }

            // Invalidate bulk status to refresh counts, and refetch the import
            // tree + import-items so the folder/file lists reconcile with
            // what's now on disk. A terminal import may have emptied the source
            // folder (move mode) or replaced it in place (upgrade); without
            // this, those lists go stale whenever the import doesn't change the
            // current selection — most visibly after an upgrade. See #126.
            queryClient.invalidateQueries({
              queryKey: beetsImportKeys.bulkStatus(librarySlug),
            })
            queryClient.invalidateQueries({
              queryKey: importTreeKeys.byLibrary(librarySlug),
            })
            queryClient.invalidateQueries({
              queryKey: [...scanKeys.importItems(), librarySlug],
            })
          }
        } catch (err) {
          console.error('[useBeetsImport] Polling error:', err)
          // Don't stop polling on transient errors
        }
      }

      // Run immediately then start interval
      poll()
      const interval = setInterval(poll, IMPORT_POLL_INTERVAL_MS)
      pollingRefs.current.set(jobId, interval)
    },
    [librarySlug, queryClient]
  )

  /**
   * Stop polling for a job.
   */
  const stopPolling = useCallback((jobId: string) => {
    const interval = pollingRefs.current.get(jobId)
    if (interval) {
      clearInterval(interval)
      pollingRefs.current.delete(jobId)
    }
  }, [])

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      pollingRefs.current.forEach((interval) => clearInterval(interval))
      pollingRefs.current.clear()
    }
  }, [])

  /**
   * Mutation for starting an import job.
   */
  const startImportMutation = useMutation<
    ImportJobResponse,
    Error,
    {
      albumPath: string
      candidate?: Candidate
      importAsIs?: boolean
      replaceExisting?: boolean
    }
  >({
    mutationFn: ({ albumPath, candidate, importAsIs, replaceExisting }) => {
      const request: ImportJobRequest = importAsIs
        ? { albumPath, importAsIs: true, replaceExisting }
        : {
            albumPath,
            candidate: candidateToImportCandidate(candidate!),
            replaceExisting,
          }
      return startImport(librarySlug, request)
    },
    onSuccess: (response, { albumPath }) => {
      console.log('[useBeetsImport] Import job created:', response)

      // Add to active jobs
      setActiveJobs((prev) => {
        const updated = new Map(prev)
        updated.set(albumPath, {
          jobId: response.jobId,
          albumPath: response.albumPath,
          status: 'pending',
        })
        return updated
      })

      // Start polling for status
      startPolling(response.jobId, albumPath)

      // Invalidate bulk status
      queryClient.invalidateQueries({
        queryKey: beetsImportKeys.bulkStatus(librarySlug),
      })
    },
  })

  /**
   * Check if an album has an active import job.
   */
  const getJobForAlbum = useCallback(
    (albumPath: string): ImportJobState | undefined => {
      return activeJobs.get(albumPath)
    },
    [activeJobs]
  )

  /**
   * Check if any import is currently in progress.
   */
  const hasActiveImports = Array.from(activeJobs.values()).some(
    (job) => job.status === 'pending' || job.status === 'in_progress'
  )

  /**
   * Resume polling for in-progress jobs from bulk status.
   */
  const resumePollingForInProgressJobs = useCallback(
    (bulkStatus: BulkImportStatusResponse) => {
      Object.entries(bulkStatus.albums).forEach(([albumPath, state]) => {
        if (state.state === 'in_progress' && state.jobId) {
          // Check if we're already tracking this job
          if (!activeJobs.has(albumPath)) {
            setActiveJobs((prev) => {
              const updated = new Map(prev)
              updated.set(albumPath, {
                jobId: state.jobId!,
                albumPath,
                status: 'in_progress',
                startedAt: state.startedAt,
              })
              return updated
            })
            startPolling(state.jobId, albumPath)
          }
        }
      })
    },
    [activeJobs, startPolling]
  )

  /**
   * Clear a completed/failed job from tracking.
   */
  const clearJob = useCallback((albumPath: string) => {
    setActiveJobs((prev) => {
      const updated = new Map(prev)
      const job = updated.get(albumPath)
      if (job) {
        stopPolling(job.jobId)
        updated.delete(albumPath)
      }
      return updated
    })
  }, [stopPolling])

  return {
    // Mutation
    startImport: startImportMutation.mutate,
    startImportAsync: startImportMutation.mutateAsync,
    isPending: startImportMutation.isPending,
    error: startImportMutation.error,
    isConflict: startImportMutation.error instanceof BeetsImportApiError &&
      startImportMutation.error.status === 409,

    // Job tracking
    activeJobs,
    getJobForAlbum,
    hasActiveImports,
    resumePollingForInProgressJobs,
    clearJob,

    // Reset
    reset: startImportMutation.reset,
  }
}
