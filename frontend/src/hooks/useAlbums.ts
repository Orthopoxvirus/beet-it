import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchLibraryAlbums,
  fetchAlbumLetters,
  fetchAlbumDetail,
  fetchAlbumTracks,
  uploadCoverArt,
  downloadCoverArtFromUrl,
  searchCoverArt,
  moveAlbumToLibrary,
  deleteAlbum,
  convertAlbumWav,
  type MoveAlbumResponse,
  type DeleteAlbumResponse,
  type DeleteAlbumMode,
} from '@/api/albums'
import { pollAudioOpStatus } from '@/api/beets-import'
import type { AudioOpResult } from '@/types/beets-import'
import { libraryTreeKeys } from './useLibraryTree'
import { libraryItemsKeys } from './useLibraryItems'

// Query keys for cache management
export const albumKeys = {
  all: ['albums'] as const,
  lists: () => [...albumKeys.all, 'list'] as const,
  list: (slug: string, skip: number, limit: number) =>
    [...albumKeys.lists(), { slug, skip, limit }] as const,
  letters: (slug: string) => [...albumKeys.all, 'letters', slug] as const,
  details: () => [...albumKeys.all, 'detail'] as const,
  detail: (slug: string, albumId: number) =>
    [...albumKeys.details(), { slug, albumId }] as const,
  tracks: (slug: string, albumId: number) =>
    [...albumKeys.all, 'tracks', { slug, albumId }] as const,
  coverSearch: (slug: string, albumId: number) =>
    [...albumKeys.all, 'cover-search', { slug, albumId }] as const,
}

/**
 * Search public sources for cover-art candidates. Only runs while `enabled`
 * (e.g. when the "Search online" tab is open) since it triggers network fetches.
 */
export function useSearchCoverArt(
  slug: string,
  albumId: number,
  enabled: boolean
) {
  return useQuery({
    queryKey: albumKeys.coverSearch(slug, albumId),
    queryFn: () => searchCoverArt(slug, albumId),
    enabled: enabled && !!slug && !!albumId,
    staleTime: 5 * 60 * 1000,
    retry: false,
  })
}

// ============================================================================
// Query Hooks
// ============================================================================

export interface UseLibraryAlbumsOptions {
  skip?: number
  limit?: number
}

export function useLibraryAlbums(
  slug: string,
  options: UseLibraryAlbumsOptions = {}
) {
  // Default to a high cap so the AlbumsTab grid + alphabet-nav can show
  // every album in libraries that exceed the legacy 50-page size (kids-audio
  // has ~1200; the previous default silently dropped K-Z entirely). The
  // backend caps at 5000 — switch to true infinite scroll if any library
  // grows past that.
  const { skip = 0, limit = 5000 } = options

  return useQuery({
    queryKey: albumKeys.list(slug, skip, limit),
    queryFn: () => fetchLibraryAlbums(slug, skip, limit),
    enabled: !!slug,
    retry: false,
  })
}

/**
 * Hook to fetch available album starting letters for a library.
 *
 * Returns the list of letters (A-Z and '#') that have at least one album.
 * Used by the AlphabetNav component to determine which letters are available.
 *
 * @param librarySlug - The library's slug identifier
 * @returns Query result with letters array
 */
export function useAlbumLetters(librarySlug: string | undefined) {
  return useQuery({
    queryKey: albumKeys.letters(librarySlug || ''),
    queryFn: () => fetchAlbumLetters(librarySlug!),
    enabled: !!librarySlug,
    staleTime: 5 * 60 * 1000, // 5 minutes - letters rarely change
    retry: false,
  })
}

// ============================================================================
// Album Detail Hooks
// ============================================================================

/**
 * Hook to fetch detailed album metadata.
 *
 * @param slug - The library's slug identifier
 * @param albumId - The album's ID
 * @returns Query result with album detail
 */
export function useAlbumDetail(slug: string | undefined, albumId: number | undefined) {
  return useQuery({
    queryKey: albumKeys.detail(slug || '', albumId || 0),
    queryFn: () => fetchAlbumDetail(slug!, albumId!),
    enabled: !!slug && !!albumId,
    retry: false,
  })
}

/**
 * Hook to fetch all tracks for an album.
 *
 * @param slug - The library's slug identifier
 * @param albumId - The album's ID
 * @returns Query result with track list
 */
export function useAlbumTracks(slug: string | undefined, albumId: number | undefined) {
  return useQuery({
    queryKey: albumKeys.tracks(slug || '', albumId || 0),
    queryFn: () => fetchAlbumTracks(slug!, albumId!),
    enabled: !!slug && !!albumId,
    retry: false,
  })
}

// ============================================================================
// Cover Art Mutation Hooks
// ============================================================================

/**
 * Hook to upload cover art for an album.
 *
 * @returns Mutation for uploading cover art
 */
export function useUploadCoverArt() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      slug,
      albumId,
      file,
    }: {
      slug: string
      albumId: number
      file: File
    }) => uploadCoverArt(slug, albumId, file),
    onSuccess: (_, { slug, albumId }) => {
      // Invalidate album detail to refresh cover art
      queryClient.invalidateQueries({ queryKey: albumKeys.detail(slug, albumId) })
      // Also invalidate the album list as cover art path may have changed
      queryClient.invalidateQueries({ queryKey: albumKeys.lists() })
    },
  })
}

/**
 * Hook to download and set cover art from a URL.
 *
 * @returns Mutation for downloading cover art from URL
 */
export function useDownloadCoverArtFromUrl() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      slug,
      albumId,
      url,
    }: {
      slug: string
      albumId: number
      url: string
    }) => downloadCoverArtFromUrl(slug, albumId, url),
    onSuccess: (_, { slug, albumId }) => {
      // Invalidate album detail to refresh cover art
      queryClient.invalidateQueries({ queryKey: albumKeys.detail(slug, albumId) })
      // Also invalidate the album list as cover art path may have changed
      queryClient.invalidateQueries({ queryKey: albumKeys.lists() })
    },
  })
}

// ============================================================================
// Move Album Mutation Hook
// ============================================================================

/**
 * Hook to queue a job that moves an album to a different library.
 *
 * The 202 response only confirms the job was queued — the file move and DB
 * sync run asynchronously in Celery. Listing/detail caches for both source
 * and target are invalidated so the UI reflects the in-flight move once the
 * worker writes the new rows.
 */
export function useMoveAlbumToLibrary() {
  const queryClient = useQueryClient()

  return useMutation<
    MoveAlbumResponse,
    Error,
    { slug: string; albumId: number; targetLibrarySlug: string }
  >({
    mutationFn: ({ slug, albumId, targetLibrarySlug }) =>
      moveAlbumToLibrary(slug, albumId, targetLibrarySlug),
    onSuccess: (_, { slug, albumId, targetLibrarySlug }) => {
      // Source: album detail will 404 once the move task completes; drop it
      // from the cache and refresh the album list.
      queryClient.removeQueries({ queryKey: albumKeys.detail(slug, albumId) })
      queryClient.removeQueries({ queryKey: albumKeys.tracks(slug, albumId) })
      queryClient.invalidateQueries({ queryKey: albumKeys.lists() })
      queryClient.invalidateQueries({ queryKey: albumKeys.letters(slug) })
      queryClient.invalidateQueries({
        queryKey: albumKeys.letters(targetLibrarySlug),
      })
    },
  })
}

/**
 * Hook to convert an imported album's WAV tracks to FLAC, in place.
 *
 * The mutation resolves only once the background job has finished (it starts
 * the job, then polls the audio-op status endpoint), so `isPending` covers the
 * whole conversion and the per-file result counts are available in `data`.
 * On success every view showing the album's format is refreshed.
 */
export function useConvertAlbumWav() {
  const queryClient = useQueryClient()

  return useMutation<
    AudioOpResult,
    Error,
    { slug: string; albumId: number; deleteOriginals: boolean }
  >({
    mutationFn: async ({ slug, albumId, deleteOriginals }) => {
      const job = await convertAlbumWav(slug, albumId, deleteOriginals)
      return pollAudioOpStatus(slug, job.job_id)
    },
    onSuccess: (_, { slug, albumId }) => {
      queryClient.invalidateQueries({ queryKey: albumKeys.detail(slug, albumId) })
      queryClient.invalidateQueries({ queryKey: albumKeys.tracks(slug, albumId) })
      queryClient.invalidateQueries({ queryKey: albumKeys.lists() })
      queryClient.invalidateQueries({ queryKey: libraryItemsKeys.lists() })
    },
  })
}

/**
 * Hook to delete a single album from a library.
 *
 * Runs synchronously server-side (a single album folder is small). On success
 * we drop the album's detail/tracks caches and invalidate every view that
 * lists it — the album grid, the batch-edit folder tree, and the library
 * items table — so the album disappears without a manual refresh.
 */
export function useDeleteAlbum() {
  const queryClient = useQueryClient()

  return useMutation<
    DeleteAlbumResponse,
    Error,
    { slug: string; albumId: number; mode: DeleteAlbumMode }
  >({
    mutationFn: ({ slug, albumId, mode }) => deleteAlbum(slug, albumId, mode),
    onSuccess: (_, { slug, albumId }) => {
      queryClient.removeQueries({ queryKey: albumKeys.detail(slug, albumId) })
      queryClient.removeQueries({ queryKey: albumKeys.tracks(slug, albumId) })
      queryClient.invalidateQueries({ queryKey: albumKeys.lists() })
      queryClient.invalidateQueries({ queryKey: albumKeys.letters(slug) })
      queryClient.invalidateQueries({ queryKey: libraryTreeKeys.byLibrary(slug) })
      queryClient.invalidateQueries({ queryKey: libraryItemsKeys.lists() })
    },
  })
}
