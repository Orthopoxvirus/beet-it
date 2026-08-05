import { useQuery } from '@tanstack/react-query'
import { getLibraryTree } from '@/api/libraryTree'

export const libraryTreeKeys = {
  all: ['library-tree'] as const,
  byLibrary: (slug: string) => [...libraryTreeKeys.all, slug] as const,
}

/**
 * Hook to fetch the library folder tree.
 *
 * Stays cached for 1 minute — the tree changes only when imports finish,
 * and the batch-edit flow doesn't benefit from sub-minute freshness.
 */
export function useLibraryTree(slug: string | undefined) {
  return useQuery({
    queryKey: libraryTreeKeys.byLibrary(slug || ''),
    queryFn: () => getLibraryTree(slug!),
    enabled: !!slug,
    staleTime: 60_000,
  })
}
