import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchScanStatus,
  triggerScan,
  fetchScanHistory,
  fetchImportItems,
  type FetchImportItemsOptions,
} from '@/api/scan'

// ============================================================================
// Query Keys
// ============================================================================

export const scanKeys = {
  all: ['scans'] as const,
  status: () => [...scanKeys.all, 'status'] as const,
  statusBySlug: (slug: string) => [...scanKeys.status(), slug] as const,
  history: () => [...scanKeys.all, 'history'] as const,
  historyBySlug: (slug: string, skip: number, limit: number) =>
    [...scanKeys.history(), slug, { skip, limit }] as const,
  importItems: () => [...scanKeys.all, 'importItems'] as const,
  importItemsBySlug: (slug: string, options: FetchImportItemsOptions) =>
    [...scanKeys.importItems(), slug, options] as const,
}

// ============================================================================
// Query Hooks
// ============================================================================

/**
 * Hook for fetching the current scan status of a library
 */
export function useScanStatus(slug: string | undefined, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: scanKeys.statusBySlug(slug || ''),
    queryFn: () => fetchScanStatus(slug!),
    enabled: !!slug && (options?.enabled ?? true),
    // Refresh status every 10 seconds when a scan might be active
    refetchInterval: (query) => {
      const data = query.state.data
      if (data?.currentScan || data?.queuedScans) {
        return 10000 // 10 seconds
      }
      return false // Don't refetch when no active scan
    },
    staleTime: 5000, // Consider data stale after 5 seconds
  })
}

/**
 * Hook for fetching scan history for a library
 */
export function useScanHistory(
  slug: string | undefined,
  skip = 0,
  limit = 20,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: scanKeys.historyBySlug(slug || '', skip, limit),
    queryFn: () => fetchScanHistory(slug!, skip, limit),
    enabled: !!slug && (options?.enabled ?? true),
  })
}

/**
 * Hook for fetching import items for a library
 */
export function useImportItems(
  slug: string | undefined,
  fetchOptions: FetchImportItemsOptions = {},
  queryOptions?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: scanKeys.importItemsBySlug(slug || '', fetchOptions),
    queryFn: () => fetchImportItems(slug!, fetchOptions),
    enabled: !!slug && (queryOptions?.enabled ?? true),
  })
}

// ============================================================================
// Mutation Hooks
// ============================================================================

/**
 * Hook for triggering a manual scan
 */
export function useTriggerScan() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (slug: string) => triggerScan(slug),
    onSuccess: (_, slug) => {
      // Invalidate scan status to refetch current state
      queryClient.invalidateQueries({ queryKey: scanKeys.statusBySlug(slug) })
    },
  })
}

// ============================================================================
// Cache Utilities
// ============================================================================

/**
 * Hook for invalidating scan-related caches
 */
export function useInvalidateScanCache() {
  const queryClient = useQueryClient()

  return {
    /**
     * Invalidate all scan status caches
     */
    invalidateAllStatus: () => {
      queryClient.invalidateQueries({ queryKey: scanKeys.status() })
    },

    /**
     * Invalidate scan status for a specific library
     */
    invalidateStatus: (slug: string) => {
      queryClient.invalidateQueries({ queryKey: scanKeys.statusBySlug(slug) })
    },

    /**
     * Invalidate scan history for a specific library
     */
    invalidateHistory: (slug: string) => {
      queryClient.invalidateQueries({ queryKey: scanKeys.historyBySlug(slug, 0, 20) })
    },

    /**
     * Invalidate import items for a specific library
     */
    invalidateImportItems: (slug: string) => {
      queryClient.invalidateQueries({
        queryKey: [...scanKeys.importItems(), slug],
        exact: false,
      })
    },

    /**
     * Invalidate all scan-related caches for a library
     */
    invalidateAll: (slug: string) => {
      queryClient.invalidateQueries({ queryKey: scanKeys.statusBySlug(slug) })
      queryClient.invalidateQueries({
        queryKey: [...scanKeys.history(), slug],
        exact: false,
      })
      queryClient.invalidateQueries({
        queryKey: [...scanKeys.importItems(), slug],
        exact: false,
      })
    },
  }
}
