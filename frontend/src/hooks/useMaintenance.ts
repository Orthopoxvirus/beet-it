import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import {
  fetchMissingCover,
  fetchUnimported,
  enablePlugin,
  actOnStrays,
  useStrayAsCover as apiUseStrayAsCover,
  fetchBpmInfo,
  fetchBpmBackfillStatus,
  startBpmBackfill,
  cancelBpmBackfill,
  type StrayAction,
} from '@/api/maintenance'
import { albumKeys } from './useAlbums'

export const maintenanceKeys = {
  all: ['maintenance'] as const,
  missingCover: (slug: string) =>
    [...maintenanceKeys.all, 'missing-cover', slug] as const,
  unimported: (slug: string) =>
    [...maintenanceKeys.all, 'unimported', slug] as const,
  bpmInfo: (slug: string) => [...maintenanceKeys.all, 'bpm-info', slug] as const,
  bpmStatus: (slug: string) => [...maintenanceKeys.all, 'bpm-status', slug] as const,
}

export function useMissingCover(slug: string) {
  return useQuery({
    queryKey: maintenanceKeys.missingCover(slug),
    queryFn: () => fetchMissingCover(slug),
    enabled: !!slug,
    retry: false,
  })
}

export function useUnimported(slug: string) {
  return useQuery({
    queryKey: maintenanceKeys.unimported(slug),
    queryFn: () => fetchUnimported(slug),
    enabled: !!slug,
    retry: false,
  })
}

export function useEnablePlugin(slug: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (plugin: string) => enablePlugin(slug, plugin),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: maintenanceKeys.unimported(slug),
      })
    },
  })
}

export function useStrayAction(slug: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ paths, action }: { paths: string[]; action: StrayAction }) =>
      actOnStrays(slug, paths, action),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: maintenanceKeys.unimported(slug),
      })
      // Moving strays back to import changes the import tree; albums unaffected,
      // but invalidate album lists in case a stray was promoted/cleaned.
      queryClient.invalidateQueries({ queryKey: albumKeys.lists() })
    },
  })
}

export function useStrayAsCover(slug: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (path: string) => apiUseStrayAsCover(slug, path),
    onSuccess: (result) => {
      queryClient.invalidateQueries({
        queryKey: maintenanceKeys.unimported(slug),
      })
      // The album's cover changed — refresh its detail view and every list
      // rendering the cover (cover_version drives the cache-buster).
      queryClient.invalidateQueries({
        queryKey: albumKeys.detail(slug, result.album_id),
      })
      queryClient.invalidateQueries({ queryKey: albumKeys.lists() })
      queryClient.invalidateQueries({
        queryKey: maintenanceKeys.missingCover(slug),
      })
    },
  })
}

export function useBpmInfo(slug: string) {
  return useQuery({
    queryKey: maintenanceKeys.bpmInfo(slug),
    queryFn: () => fetchBpmInfo(slug),
    enabled: !!slug,
    retry: false,
  })
}

/** Poll the backfill status — fast while a job is active, parked otherwise. */
export function useBpmBackfillStatus(slug: string) {
  return useQuery({
    queryKey: maintenanceKeys.bpmStatus(slug),
    queryFn: () => fetchBpmBackfillStatus(slug),
    enabled: !!slug,
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'queued' || status === 'running' ? 2000 : false
    },
  })
}

export function useStartBpmBackfill(slug: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => startBpmBackfill(slug),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: maintenanceKeys.bpmStatus(slug) })
    },
  })
}

export function useCancelBpmBackfill(slug: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => cancelBpmBackfill(slug),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: maintenanceKeys.bpmStatus(slug) })
      queryClient.invalidateQueries({ queryKey: maintenanceKeys.bpmInfo(slug) })
    },
  })
}
