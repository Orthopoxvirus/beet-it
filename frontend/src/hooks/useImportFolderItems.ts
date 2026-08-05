import { useQuery } from '@tanstack/react-query'
import { fetchImportItems } from '@/api/scan'
import { scanKeys } from './useScanStatus'

// ============================================================================
// Query Hooks
// ============================================================================

/**
 * Hook for fetching import items for a specific folder path.
 * Uses path_prefix to get all items recursively under the folder.
 *
 * @param slug - Library slug
 * @param path - Folder path to fetch items for
 * @param options - Additional query options
 */
export function useImportFolderItems(
  slug: string | undefined,
  path: string | null | undefined,
  options?: {
    enabled?: boolean
    limit?: number
  }
) {
  const limit = options?.limit ?? 500 // Higher limit for folder contents

  return useQuery({
    queryKey: scanKeys.importItemsBySlug(slug || '', {
      pathPrefix: path,
      itemType: 'file',
      limit,
    }),
    queryFn: () =>
      fetchImportItems(slug!, {
        pathPrefix: path,
        itemType: 'file',
        limit,
      }),
    enabled: !!slug && !!path && (options?.enabled ?? true),
  })
}
