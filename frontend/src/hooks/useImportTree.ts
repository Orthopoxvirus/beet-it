import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteImportFolder, fetchImportTree } from '@/api/import-tree'
import { scanKeys } from './useScanStatus'

// Query keys for cache management
export const importTreeKeys = {
  all: ['import-tree'] as const,
  byLibrary: (slug: string) => [...importTreeKeys.all, slug] as const,
}

// ============================================================================
// Query Hooks
// ============================================================================

/**
 * Hook to fetch the import folder tree for a specific library.
 * @param slug - The library's URL-safe slug
 * @returns TanStack Query result with import tree data
 */
export function useImportTree(slug: string) {
  return useQuery({
    queryKey: importTreeKeys.byLibrary(slug),
    queryFn: () => fetchImportTree(slug),
    enabled: !!slug,
  })
}

/**
 * Hook to delete a folder from the library's import area. On success it
 * invalidates the import tree (so the folder disappears) and the import-items
 * queries (so the track table drops the purged items).
 *
 * @param slug - The library's URL-safe slug
 */
export function useDeleteImportFolder(slug: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (path: string) => deleteImportFolder(slug, path),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: importTreeKeys.byLibrary(slug) })
      queryClient.invalidateQueries({ queryKey: [...scanKeys.importItems(), slug] })
    },
  })
}
