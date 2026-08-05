import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  analyzeAlbum,
  getCacheStatus,
  addManualCandidate,
  getAnalyzeQueue,
  analyzeFolder,
  getAutoAnalyzeSetting,
  setAutoAnalyzeSetting,
} from '@/api/beets-import'
import type {
  AnalyzeAlbumResponse,
  CacheStatusResponse,
  ManualCandidateRequest,
  ManualCandidateResponse,
  AnalyzeQueueResponse,
  AnalyzeFolderResponse,
  AutoAnalyzeSettingResponse,
} from '@/types/beets-import'

// ============================================================================
// Query Keys
// ============================================================================

export const beetsAnalysisKeys = {
  all: ['beets-analysis'] as const,
  byLibrary: (slug: string) => [...beetsAnalysisKeys.all, slug] as const,
  byAlbum: (slug: string, albumPath: string) =>
    [...beetsAnalysisKeys.byLibrary(slug), albumPath] as const,
  cacheStatus: (slug: string) => [...beetsAnalysisKeys.byLibrary(slug), 'cache-status'] as const,
  analysisQueue: (slug: string) => [...beetsAnalysisKeys.byLibrary(slug), 'analysis-queue'] as const,
  autoAnalyzeSetting: (slug: string) => [...beetsAnalysisKeys.byLibrary(slug), 'auto-analyze-setting'] as const,
}

// ============================================================================
// Mutation Hooks
// ============================================================================

/**
 * Hook for triggering beets analysis on an album.
 *
 * Uses a mutation because analysis is a POST operation that triggers
 * server-side processing. Results are cached in React Query for quick
 * re-access when switching between albums.
 *
 * @param librarySlug - The library slug to analyze albums in
 * @returns TanStack Query mutation object
 */
interface AnalyzeAlbumVariables {
  albumPath: string
  force?: boolean
}

export function useAnalyzeAlbum(librarySlug: string) {
  const queryClient = useQueryClient()

  return useMutation<AnalyzeAlbumResponse, Error, AnalyzeAlbumVariables>({
    mutationFn: ({ albumPath, force }) => analyzeAlbum(librarySlug, albumPath, force ?? false),
    onSuccess: (data, { albumPath }) => {
      // Cache the result for quick re-access
      queryClient.setQueryData(
        beetsAnalysisKeys.byAlbum(librarySlug, albumPath),
        data
      )
    },
  })
}

// ============================================================================
// Cache Utilities
// ============================================================================

/**
 * Hook for managing beets analysis cache.
 *
 * @param librarySlug - The library slug
 * @returns Object with cache utility functions
 */
export function useBeetsAnalysisCache(librarySlug: string) {
  const queryClient = useQueryClient()

  return {
    /**
     * Get cached analysis result for an album.
     * Returns undefined if not cached.
     */
    getCached: (albumPath: string): AnalyzeAlbumResponse | undefined => {
      return queryClient.getQueryData<AnalyzeAlbumResponse>(
        beetsAnalysisKeys.byAlbum(librarySlug, albumPath)
      )
    },

    /**
     * Check if an album has cached analysis results.
     */
    hasCached: (albumPath: string): boolean => {
      return !!queryClient.getQueryData(
        beetsAnalysisKeys.byAlbum(librarySlug, albumPath)
      )
    },

    /**
     * Invalidate (clear) cached results for an album.
     * Use this when triggering re-analysis.
     */
    invalidate: (albumPath: string) => {
      queryClient.removeQueries({
        queryKey: beetsAnalysisKeys.byAlbum(librarySlug, albumPath),
      })
    },

    /**
     * Invalidate all cached analysis results for the library.
     */
    invalidateAll: () => {
      queryClient.removeQueries({
        queryKey: beetsAnalysisKeys.byLibrary(librarySlug),
      })
    },
  }
}

// ============================================================================
// Cache Status Query Hook
// ============================================================================

/**
 * Hook for fetching cache status for multiple albums.
 *
 * Uses TanStack Query to fetch and cache the backend cache status response.
 * This allows the UI to display amber disc icons for albums with cached results.
 *
 * @param librarySlug - The library slug
 * @param albumPaths - Array of album paths to check cache status for
 * @param options - Optional query options
 * @returns TanStack Query result with cache status data
 */
export function useCacheStatus(
  librarySlug: string,
  albumPaths: string[],
  options?: { enabled?: boolean }
) {
  return useQuery<CacheStatusResponse, Error>({
    queryKey: [...beetsAnalysisKeys.cacheStatus(librarySlug), albumPaths],
    queryFn: () => getCacheStatus(librarySlug, albumPaths),
    // Only fetch when we have album paths
    enabled: options?.enabled !== false && albumPaths.length > 0,
    // Cache status doesn't change frequently, so we can use a longer stale time
    staleTime: 5 * 60 * 1000, // 5 minutes
    // But always refetch on mount: the analyzed-stage display is derived from
    // this map, and returning to the page must show the authoritative state
    refetchOnMount: 'always',
    // Retry once on failure
    retry: 1,
    // Don't refetch on window focus for this query
    refetchOnWindowFocus: false,
  })
}

// ============================================================================
// Manual Candidate Mutation Hook
// ============================================================================

/**
 * Hook for adding a manual candidate to an album's analysis results.
 *
 * Resolves an external service link (Deezer, Spotify, Discogs, MusicBrainz)
 * to candidate metadata and merges it with existing candidates.
 *
 * Implements provider deduplication: adding a new candidate from the same
 * provider replaces the existing one.
 *
 * @param librarySlug - The library slug
 * @param albumPath - The album path to add the manual candidate to
 * @returns TanStack Query mutation object
 */
export function useAddManualCandidate(librarySlug: string, albumPath: string) {
  const queryClient = useQueryClient()

  return useMutation<ManualCandidateResponse, Error, string>({
    mutationFn: (link: string) =>
      addManualCandidate(librarySlug, { albumPath, link } as ManualCandidateRequest),
    onSuccess: (data) => {
      // Update cached analysis results with new manual candidate
      queryClient.setQueryData<AnalyzeAlbumResponse>(
        beetsAnalysisKeys.byAlbum(librarySlug, albumPath),
        (old) => {
          if (!old) return old

          // Filter out existing manual candidate from same provider (deduplication)
          const filteredManual = (old.manualCandidates ?? []).filter(
            (c) => c.source.toLowerCase() !== data.provider
          )

          return {
            ...old,
            manualCandidates: [...filteredManual, data.candidate],
          }
        }
      )
    },
  })
}

// ============================================================================
// Analysis Queue Hooks
// ============================================================================

/**
 * Hook for fetching the analysis queue status for a library.
 *
 * Polls the queue status at a configurable interval when enabled.
 * Use this to display queue depth and monitor queue state.
 *
 * @param librarySlug - The library slug
 * @param options - Optional query options including polling interval
 * @returns TanStack Query result with queue status data
 */
export function useAnalysisQueue(
  librarySlug: string,
  options?: {
    enabled?: boolean
    /** Polling interval in ms. Default 3000 (3 seconds) when queue has items */
    refetchInterval?: number | false | ((query: any) => number | false)
  }
) {
  return useQuery<AnalyzeQueueResponse, Error>({
    queryKey: beetsAnalysisKeys.analysisQueue(librarySlug),
    queryFn: () => getAnalyzeQueue(librarySlug),
    enabled: options?.enabled !== false,
    // Poll every 3 seconds by default when queue has items
    refetchInterval: options?.refetchInterval ?? 3000,
    // Don't refetch on window focus - we have polling
    refetchOnWindowFocus: false,
    // Cache for a short time
    staleTime: 1000,
    retry: 1,
  })
}

/**
 * Hook for bulk analyzing all albums in an import folder.
 *
 * Calls the analyze-folder endpoint to enqueue analysis for all
 * unanalyzed albums in one action.
 *
 * @param librarySlug - The library slug
 * @returns TanStack Query mutation object
 */
export function useAnalyzeFolder(librarySlug: string) {
  const queryClient = useQueryClient()

  return useMutation<AnalyzeFolderResponse, Error, { force?: boolean }>({
    mutationFn: ({ force = false }) => analyzeFolder(librarySlug, force),
    onSuccess: () => {
      // Invalidate queue status to show new items
      queryClient.invalidateQueries({
        queryKey: beetsAnalysisKeys.analysisQueue(librarySlug),
      })
      // Invalidate cache status as albums will be analyzed
      queryClient.invalidateQueries({
        queryKey: beetsAnalysisKeys.cacheStatus(librarySlug),
      })
    },
  })
}

// ============================================================================
// Auto-Analyze Setting Hooks
// ============================================================================

/**
 * Hook for fetching the auto-analyze-after-scan setting for a library.
 *
 * @param librarySlug - The library slug
 * @param options - Optional query options
 * @returns TanStack Query result with auto-analyze setting
 */
export function useAutoAnalyzeSetting(
  librarySlug: string,
  options?: { enabled?: boolean }
) {
  return useQuery<AutoAnalyzeSettingResponse, Error>({
    queryKey: beetsAnalysisKeys.autoAnalyzeSetting(librarySlug),
    queryFn: () => getAutoAnalyzeSetting(librarySlug),
    enabled: options?.enabled !== false,
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchOnWindowFocus: false,
    retry: 1,
  })
}

/**
 * Hook for updating the auto-analyze-after-scan setting for a library.
 *
 * @param librarySlug - The library slug
 * @returns TanStack Query mutation object
 */
export function useSetAutoAnalyzeSetting(librarySlug: string) {
  const queryClient = useQueryClient()

  return useMutation<AutoAnalyzeSettingResponse, Error, boolean>({
    mutationFn: (enabled: boolean) => setAutoAnalyzeSetting(librarySlug, enabled),
    onSuccess: (data) => {
      // Update the cached setting
      queryClient.setQueryData(
        beetsAnalysisKeys.autoAnalyzeSetting(librarySlug),
        data
      )
    },
  })
}
