import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { previewTagTransformations } from '@/api/batch-tag-editor'
import type {
  TransformationRule,
  BatchPreviewResponse,
  ItemPreview,
  TagName,
} from '@/types/batch-tag-editor'

// ============================================================================
// Query Keys
// ============================================================================

export const tagPreviewKeys = {
  all: ['tagPreview'] as const,
  preview: () => [...tagPreviewKeys.all, 'preview'] as const,
  previewBySlug: (slug: string, itemIds: number[], rules: TransformationRule[]) =>
    [...tagPreviewKeys.preview(), slug, { itemIds, rules }] as const,
}

// ============================================================================
// Types
// ============================================================================

export interface UseTagPreviewOptions {
  /**
   * Whether the preview query is enabled
   * @default true
   */
  enabled?: boolean
  /**
   * Debounce delay in ms before fetching preview
   * Note: Debouncing should be handled by the caller using useDebouncedValue
   */
}

export interface UseTagPreviewResult {
  /**
   * Raw preview response data
   */
  data: BatchPreviewResponse | undefined
  /**
   * Whether the preview is currently loading
   */
  isLoading: boolean
  /**
   * Whether the preview is currently fetching (includes background refetch)
   */
  isFetching: boolean
  /**
   * Error if the preview request failed
   */
  error: Error | null
  /**
   * Map of item ID to preview changes for easy lookup
   */
  previewMap: Map<number, ItemPreview>
  /**
   * Get preview value for a specific item and tag
   */
  getPreviewValue: (itemId: number, tag: TagName) => string | undefined
  /**
   * Check if any preview value differs from original
   */
  hasChanges: boolean
}

// ============================================================================
// Hook
// ============================================================================

/**
 * Hook for fetching tag transformation previews.
 *
 * Uses TanStack Query with automatic caching and deduplication.
 * Callers should debounce the rules input before passing to this hook.
 *
 * @param slug - Library slug
 * @param itemIds - List of item IDs to preview
 * @param rules - Transformation rules to apply
 * @param options - Additional options
 */
export function useTagPreview(
  slug: string | undefined,
  itemIds: number[],
  rules: TransformationRule[],
  options: UseTagPreviewOptions = {}
): UseTagPreviewResult {
  const { enabled = true } = options

  // Only fetch if we have valid inputs
  const shouldFetch = Boolean(
    slug &&
    itemIds.length > 0 &&
    rules.length > 0 &&
    enabled
  )

  const query = useQuery({
    queryKey: tagPreviewKeys.previewBySlug(slug || '', itemIds, rules),
    queryFn: () => previewTagTransformations(slug!, itemIds, rules),
    enabled: shouldFetch,
    // Keep previous data while fetching new preview
    placeholderData: (previousData) => previousData,
    // Preview data is relatively short-lived
    staleTime: 30000, // 30 seconds
    gcTime: 60000, // 1 minute (formerly cacheTime)
    // Don't retry on error - user should fix input
    retry: false,
  })

  // Create a map for efficient lookups.
  // When shouldFetch is false (e.g. after Reset clears all rules) we return an empty map
  // so stale previews from a prior query do not leak into the UI.
  const previewMap = useMemo(() => {
    const map = new Map<number, ItemPreview>()
    if (shouldFetch && query.data?.previews) {
      for (const preview of query.data.previews) {
        map.set(preview.itemId, preview)
      }
    }
    return map
  }, [shouldFetch, query.data?.previews])

  // Helper function to get preview value for a specific item and tag
  const getPreviewValue = (itemId: number, tag: TagName): string | undefined => {
    const preview = previewMap.get(itemId)
    return preview?.changes[tag]
  }

  // Check if there are any changes
  const hasChanges = useMemo(() => {
    if (!shouldFetch || !query.data?.previews) return false
    return query.data.previews.some(
      (preview) => Object.keys(preview.changes).length > 0
    )
  }, [shouldFetch, query.data?.previews])

  return {
    data: query.data,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    error: query.error as Error | null,
    previewMap,
    getPreviewValue,
    hasChanges,
  }
}

// ============================================================================
// Utility Hook: Debounced Value
// ============================================================================

import { useState, useEffect } from 'react'

/**
 * Hook that debounces a value by the specified delay.
 *
 * @param value - Value to debounce
 * @param delay - Debounce delay in milliseconds
 * @returns Debounced value
 */
export function useDebouncedValue<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value)
    }, delay)

    return () => {
      clearTimeout(timer)
    }
  }, [value, delay])

  return debouncedValue
}
