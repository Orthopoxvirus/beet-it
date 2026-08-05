import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchLibraries,
  fetchLibrary,
  createLibrary,
  updateLibrary,
  deleteLibrary,
  type LibraryCreate,
  type LibraryUpdate,
  type DeleteOptions,
} from '@/api/libraries'

// Query keys for cache management
export const libraryKeys = {
  all: ['libraries'] as const,
  lists: () => [...libraryKeys.all, 'list'] as const,
  list: (skip: number, limit: number) =>
    [...libraryKeys.lists(), { skip, limit }] as const,
  details: () => [...libraryKeys.all, 'detail'] as const,
  detail: (slug: string) => [...libraryKeys.details(), slug] as const,
}

// ============================================================================
// Query Hooks
// ============================================================================

export function useLibraries(skip = 0, limit = 100) {
  return useQuery({
    queryKey: libraryKeys.list(skip, limit),
    queryFn: () => fetchLibraries(skip, limit),
  })
}

export interface UseLibraryOptions {
  enabled?: boolean
}

export function useLibrary(slug: string, options: UseLibraryOptions = {}) {
  const { enabled = true } = options
  return useQuery({
    queryKey: libraryKeys.detail(slug),
    queryFn: () => fetchLibrary(slug),
    enabled: !!slug && enabled,
  })
}

// ============================================================================
// Mutation Hooks
// ============================================================================

export function useCreateLibrary() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: LibraryCreate) => createLibrary(data),
    onSuccess: () => {
      // Invalidate library list to refetch
      queryClient.invalidateQueries({ queryKey: libraryKeys.lists() })
    },
  })
}

export function useUpdateLibrary() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ slug, data }: { slug: string; data: LibraryUpdate }) =>
      updateLibrary(slug, data),
    onSuccess: (updatedLibrary) => {
      // Update the specific library in cache using new slug
      queryClient.setQueryData(
        libraryKeys.detail(updatedLibrary.slug),
        updatedLibrary
      )
      // Invalidate library list to refetch
      queryClient.invalidateQueries({ queryKey: libraryKeys.lists() })
    },
  })
}

export function useDeleteLibrary() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ slug, options }: { slug: string; options?: DeleteOptions }) =>
      deleteLibrary(slug, options),
    onSuccess: (_, { slug }) => {
      // Remove the specific library from cache
      queryClient.removeQueries({ queryKey: libraryKeys.detail(slug) })
      // Invalidate library list to refetch
      queryClient.invalidateQueries({ queryKey: libraryKeys.lists() })
    },
  })
}
