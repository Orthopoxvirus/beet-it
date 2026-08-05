import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  deleteDownload,
  fetchDownloads,
  queueDownload,
  type DownloadJob,
  type DownloadJobListResponse,
} from '@/api/downloads'

export const downloadKeys = {
  all: ['downloads'] as const,
  list: (slug: string) => [...downloadKeys.all, 'list', slug] as const,
}

/** Live list of a library's download jobs. Refetches while any job is active. */
export function useDownloads(slug: string | undefined) {
  return useQuery<DownloadJobListResponse>({
    queryKey: downloadKeys.list(slug || ''),
    queryFn: () => fetchDownloads(slug as string),
    enabled: !!slug,
    // Poll as a safety net while packing, in case an SSE event is missed.
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? []
      const active = items.some(
        (j: DownloadJob) => j.status === 'pending' || j.status === 'packing'
      )
      return active ? 3000 : false
    },
  })
}

export function useQueueDownload() {
  const queryClient = useQueryClient()
  return useMutation<
    DownloadJob,
    Error,
    { slug: string; albumIds: number[]; trackIds?: number[] }
  >({
    mutationFn: ({ slug, albumIds, trackIds }) =>
      queueDownload(slug, albumIds, trackIds ?? []),
    onSuccess: (_job, { slug }) => {
      queryClient.invalidateQueries({ queryKey: downloadKeys.list(slug) })
    },
  })
}

export function useDeleteDownload() {
  const queryClient = useQueryClient()
  return useMutation<void, Error, { slug: string; jobId: number }>({
    mutationFn: ({ slug, jobId }) => deleteDownload(slug, jobId),
    onSuccess: (_void, { slug }) => {
      queryClient.invalidateQueries({ queryKey: downloadKeys.list(slug) })
    },
  })
}
