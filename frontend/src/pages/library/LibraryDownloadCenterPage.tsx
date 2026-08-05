import { useOutletContext } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Download, Trash2, Loader2, AlertCircle, Package } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { toast } from '@/components/ui/toast'
import { useDownloads, useDeleteDownload, downloadKeys } from '@/hooks/useDownloads'
import { useActivityStream } from '@/hooks/useActivity'
import { getDownloadFileUrl, type DownloadJob } from '@/api/downloads'
import { formatBytes } from '@/lib/utils'
import type { LibraryDetailContext } from '../LibraryDetailLayout'

function StatusBadge({ status }: { status: DownloadJob['status'] }) {
  switch (status) {
    case 'completed':
      return <Badge variant="default">Ready</Badge>
    case 'failed':
      return <Badge variant="destructive">Failed</Badge>
    case 'packing':
      return (
        <Badge variant="secondary">
          <Loader2 className="mr-1 h-3 w-3 animate-spin" /> Packing
        </Badge>
      )
    default:
      return <Badge variant="secondary">Queued</Badge>
  }
}

function JobCard({ slug, job, onDelete }: {
  slug: string
  job: DownloadJob
  onDelete: (jobId: number) => void
}) {
  const active = job.status === 'pending' || job.status === 'packing'
  const percent = job.album_count
    ? Math.round((job.processed_count / job.album_count) * 100)
    : 0

  return (
    <div className="rounded-lg border p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Package className="h-4 w-4 text-muted-foreground" />
            <span className="font-medium">
              {job.album_count} item{job.album_count === 1 ? '' : 's'}
            </span>
            <StatusBadge status={job.status} />
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {new Date(job.created_at).toLocaleString()}
            {job.size_bytes != null ? ` · ${formatBytes(job.size_bytes)}` : ''}
            {job.expires_at ? ` · expires ${new Date(job.expires_at).toLocaleDateString()}` : ''}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {job.status === 'completed' && (
            <Button size="sm" asChild>
              <a href={getDownloadFileUrl(slug, job.id)} download>
                <Download className="mr-1.5 h-4 w-4" /> Download
              </a>
            </Button>
          )}
          <Button
            size="icon"
            variant="ghost"
            onClick={() => onDelete(job.id)}
            aria-label="Delete download"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {active && (
        <div className="space-y-1">
          <Progress value={percent} />
          <div className="text-xs text-muted-foreground">
            {job.processed_count} / {job.album_count} items packed
          </div>
        </div>
      )}

      {job.status === 'failed' && job.error && (
        <div className="flex items-start gap-2 rounded-md bg-destructive/10 p-2 text-xs text-destructive">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span className="break-words">{job.error}</span>
        </div>
      )}
    </div>
  )
}

export default function LibraryDownloadCenterPage() {
  const { library } = useOutletContext<LibraryDetailContext>()
  const slug = library.slug
  const queryClient = useQueryClient()
  const { data, isLoading, error } = useDownloads(slug)
  const deleteMutation = useDeleteDownload()

  // Live-refresh the job list when a download task reports progress / finishes.
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: downloadKeys.list(slug) })
  useActivityStream({
    onTaskProgress: (d) => { if (d.taskType === 'download') invalidate() },
    onTaskCompleted: (d) => { if (d.taskType === 'download') invalidate() },
    onTaskFailed: (d) => { if (d.taskType === 'download') invalidate() },
  })

  const handleDelete = async (jobId: number) => {
    try {
      await deleteMutation.mutateAsync({ slug, jobId })
    } catch (err) {
      toast.error({
        title: 'Could not delete download',
        description: err instanceof Error ? err.message : 'Please try again.',
      })
    }
  }

  const jobs = data?.items ?? []

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold">Download Center</h2>
        <p className="text-sm text-muted-foreground">
          Gather albums and titles across the library, then pack them into a single zip to download.
        </p>
      </div>

      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" /> Could not load downloads.
        </div>
      )}

      {!isLoading && !error && jobs.length === 0 && (
        <div className="rounded-lg border bg-muted/20 py-12 text-center">
          <Package className="mx-auto h-12 w-12 text-muted-foreground" />
          <h3 className="mt-4 text-lg font-medium">No downloads yet</h3>
          <p className="mt-2 text-sm text-muted-foreground">
            Add albums from the album grid or titles from the Titles page, then pack them from the bar at the bottom.
          </p>
        </div>
      )}

      {jobs.map((job) => (
        <JobCard key={job.id} slug={slug} job={job} onDelete={handleDelete} />
      ))}
    </div>
  )
}
