import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Download, X, Loader2, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { toast } from '@/components/ui/toast'
import { useDownloadGather, gatherEntryKind } from '@/contexts/DownloadGatherContext'
import { useQueueDownload } from '@/hooks/useDownloads'
import { formatBytes } from '@/lib/utils'

/**
 * App-wide floating bar showing albums marked for download. Sits bottom-center
 * once at least one album is gathered. Clicking the last-added album opens a
 * popup to review/remove the selection; "Pack & download" queues the archive
 * and routes to the library's Download Center.
 */
/** "2 albums · 13 titles" — only the kinds actually present. */
function selectionLabel(albumCount: number, trackCount: number): string {
  const parts: string[] = []
  if (albumCount) parts.push(`${albumCount} album${albumCount === 1 ? '' : 's'}`)
  if (trackCount) parts.push(`${trackCount} title${trackCount === 1 ? '' : 's'}`)
  return parts.join(' · ')
}

export default function GatheringBar() {
  const {
    slug, items, count, albumCount, trackCount, totalSize, lastAdded,
    removeAlbum, removeTrack, clear,
  } = useDownloadGather()
  const [reviewOpen, setReviewOpen] = useState(false)
  const navigate = useNavigate()
  const queueMutation = useQueueDownload()

  if (count === 0 || !slug) return null

  const handleComplete = async () => {
    try {
      await queueMutation.mutateAsync({
        slug,
        albumIds: items.filter((e) => gatherEntryKind(e) === 'album').map((e) => e.id),
        trackIds: items.filter((e) => gatherEntryKind(e) === 'track').map((e) => e.id),
      })
      const target = slug
      clear()
      setReviewOpen(false)
      toast.success({
        title: 'Download started',
        description: 'Packing your selection — track progress in the Download Center.',
      })
      navigate(`/libraries/${target}/downloads`)
    } catch (err) {
      toast.error({
        title: 'Could not start download',
        description: err instanceof Error ? err.message : 'Please try again.',
      })
    }
  }

  return (
    <>
      <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 px-4 w-full max-w-xl">
        <div className="flex items-center gap-3 rounded-lg border bg-background/95 p-3 shadow-lg backdrop-blur supports-[backdrop-filter]:bg-background/80">
          <Download className="h-5 w-5 shrink-0 text-primary" />
          <button
            type="button"
            onClick={() => setReviewOpen(true)}
            className="min-w-0 flex-1 text-left focus:outline-none focus:ring-2 focus:ring-ring rounded"
            title="Review gathered albums"
          >
            <div className="text-sm font-medium">
              {selectionLabel(albumCount, trackCount)}
              {totalSize > 0 ? ` · ${formatBytes(totalSize)}` : ''}
            </div>
            {lastAdded && (
              <div className="truncate text-xs text-muted-foreground">
                Last added: {lastAdded.title}
              </div>
            )}
          </button>
          <Button
            size="sm"
            onClick={handleComplete}
            disabled={queueMutation.isPending}
          >
            {queueMutation.isPending ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <Download className="mr-1.5 h-4 w-4" />
            )}
            Pack &amp; download
          </Button>
          <Button
            size="icon"
            variant="ghost"
            onClick={clear}
            title="Clear selection"
            aria-label="Clear selection"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <Dialog open={reviewOpen} onOpenChange={setReviewOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Selection to download</DialogTitle>
            <DialogDescription>
              {selectionLabel(albumCount, trackCount)}
              {totalSize > 0 ? ` · ${formatBytes(totalSize)}` : ''}
            </DialogDescription>
          </DialogHeader>
          <ul className="max-h-80 space-y-1 overflow-y-auto">
            {items.map((entry) => (
              <li
                key={`${gatherEntryKind(entry)}-${entry.id}`}
                className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted/50"
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium" title={entry.title}>
                    {entry.title}
                  </div>
                  <div className="truncate text-xs text-muted-foreground">
                    {gatherEntryKind(entry) === 'track' ? 'Title · ' : ''}
                    {entry.artist}
                    {entry.sizeBytes != null ? ` · ${formatBytes(entry.sizeBytes)}` : ''}
                  </div>
                </div>
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={() =>
                    gatherEntryKind(entry) === 'track'
                      ? removeTrack(entry.id)
                      : removeAlbum(entry.id)
                  }
                  title="Remove"
                  aria-label={`Remove ${entry.title}`}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
        </DialogContent>
      </Dialog>
    </>
  )
}
