import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchLibraryConfig,
  updateLibraryConfig,
  testEmbyConnection,
  browseFilesystem,
  createDirectory,
  fetchPathStatus,
  initializeLibrary,
} from '@/api/config'
import type {
  BeetsConfig,
  EmbyTestRequest,
  FilesystemCreateRequest,
} from '@/types/beets-config'
import { useLibrary } from '@/hooks/useLibraries'

// Query keys for cache management
export const configKeys = {
  all: ['config'] as const,
  library: (libraryId: number) => [...configKeys.all, 'library', libraryId] as const,
  pathStatus: (libraryId: number) => [...configKeys.all, 'pathStatus', libraryId] as const,
}

export const filesystemKeys = {
  all: ['filesystem'] as const,
  browse: (path?: string) => [...filesystemKeys.all, 'browse', path] as const,
}

// ============================================================================
// Library Config Hooks
// ============================================================================

/**
 * Hook to fetch a library's beets configuration
 */
export function useLibraryConfig(libraryId: number) {
  return useQuery({
    queryKey: configKeys.library(libraryId),
    queryFn: () => fetchLibraryConfig(libraryId),
    enabled: libraryId > 0,
  })
}

/**
 * Hook to fetch a library's beets configuration by slug.
 * First fetches the library by slug to get its ID, then fetches the config.
 */
export function useLibraryConfigBySlug(slug: string) {
  // First fetch library by slug to get ID
  const {
    data: library,
    isLoading: isLoadingLibrary,
    error: libraryError,
  } = useLibrary(slug)

  // Then fetch config using the library ID
  const {
    data: config,
    isLoading: isLoadingConfig,
    error: configError,
  } = useLibraryConfig(library?.id ?? 0)

  return {
    data: config,
    isLoading: isLoadingLibrary || isLoadingConfig,
    error: libraryError || configError,
  }
}

// ============================================================================
// Import Mode Helper
// ============================================================================

export type ImportMode = 'copy' | 'move' | 'unknown'

/**
 * Determine the import mode from beets configuration.
 * In beets: if move=true, files are moved; otherwise copy is the default behavior.
 */
export function getImportMode(config: BeetsConfig | undefined): ImportMode {
  if (!config?.import) return 'unknown'

  // In beets: if move=true, files are moved; otherwise copy is the default behavior
  if (config.import.move === true) return 'move'
  if (config.import.copy === true) return 'copy'

  // Default beets behavior is copy
  return 'copy'
}

/**
 * Hook to update a library's beets configuration
 */
export function useUpdateLibraryConfig() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      libraryId,
      config,
    }: {
      libraryId: number
      config: BeetsConfig
    }) => updateLibraryConfig(libraryId, config),
    onSuccess: (updatedConfig, { libraryId }) => {
      // Update the config in cache
      queryClient.setQueryData(configKeys.library(libraryId), updatedConfig)
    },
  })
}

// ============================================================================
// Emby Connection Test Hook
// ============================================================================

/**
 * Hook to test Emby server connection
 */
export function useTestEmbyConnection() {
  return useMutation({
    mutationFn: ({
      libraryId,
      credentials,
    }: {
      libraryId: number
      credentials: EmbyTestRequest
    }) => testEmbyConnection(libraryId, credentials),
  })
}

// ============================================================================
// Filesystem Browse Hooks
// ============================================================================

/**
 * Hook to browse filesystem directories
 */
export function useFilesystemBrowse(path?: string) {
  return useQuery({
    queryKey: filesystemKeys.browse(path),
    queryFn: () => browseFilesystem(path),
  })
}

/**
 * Hook to create a new directory
 */
export function useCreateDirectory() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: FilesystemCreateRequest) => createDirectory(data),
    onSuccess: (_, variables) => {
      // Invalidate the parent directory's browse query to refresh the list
      queryClient.invalidateQueries({
        queryKey: filesystemKeys.browse(variables.path),
      })
    },
  })
}

// ============================================================================
// Library Path Status & Initialization Hooks
// ============================================================================

/**
 * Hook to fetch a library's path existence status by library ID.
 *
 * Returns whether the library directory and database file exist on disk.
 */
export function useLibraryPathStatus(libraryId: number | undefined) {
  return useQuery({
    queryKey: configKeys.pathStatus(libraryId ?? 0),
    queryFn: () => fetchPathStatus(libraryId!),
    enabled: libraryId !== undefined && libraryId > 0,
  })
}

/**
 * Hook to initialize library resources (directory and database).
 *
 * Creates the library directory if missing and initializes the beets database.
 * Invalidates the path status query on success.
 */
export function useInitializeLibrary() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (libraryId: number) => initializeLibrary(libraryId),
    onSuccess: (_, libraryId) => {
      // Invalidate path status to refresh UI
      queryClient.invalidateQueries({
        queryKey: configKeys.pathStatus(libraryId),
      })
    },
  })
}
