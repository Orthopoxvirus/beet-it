import { useEffect, useRef } from 'react'
import { CheckCircle, AlertCircle, Loader2, RefreshCw, Clock, X } from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

import { useBatchUpdateStatus } from '@/hooks/useLibraryItems'
import type { AlbumSyncStatus } from '@/api/libraryItems'

// ============================================================================
// Types
// ============================================================================

interface BatchUpdateStatusCardProps {
  /** Library slug */
  librarySlug: string
  /** Job ID to poll status for */
  jobId: string | null
  /** List of albums being synced (from the batch update response) */
  albumsToSync: string[]
  /** Fires once when the sync finishes (success or failure). */
  onComplete?: (allSucceeded: boolean) => void
  /** Fires when the user clicks the close button on the card. */
  onDismiss?: () => void
}

// ============================================================================
// Album Sync Status Item
// ============================================================================

interface AlbumStatusItemProps {
  album: string
  status: AlbumSyncStatus | undefined
}

function AlbumStatusItem({ album, status }: AlbumStatusItemProps) {
  const actualStatus = status?.status || 'pending'

  const getStatusIcon = () => {
    switch (actualStatus) {
      case 'pending':
        return <Clock className="h-4 w-4 text-muted-foreground" />
      case 'syncing':
        return <Loader2 className="h-4 w-4 animate-spin text-primary" />
      case 'success':
        return <CheckCircle className="h-4 w-4 text-green-500" />
      case 'failed':
        return <AlertCircle className="h-4 w-4 text-destructive" />
    }
  }

  const getStatusBadge = () => {
    switch (actualStatus) {
      case 'pending':
        return <Badge variant="outline" className="text-xs">Pending</Badge>
      case 'syncing':
        return <Badge variant="secondary" className="text-xs">Syncing</Badge>
      case 'success':
        return <Badge variant="default" className="text-xs bg-green-500">Synced</Badge>
      case 'failed':
        return <Badge variant="destructive" className="text-xs">Failed</Badge>
    }
  }

  return (
    <div className="flex items-center justify-between gap-2 py-2">
      <div className="flex items-center gap-2 min-w-0">
        {getStatusIcon()}
        <span className="text-sm truncate" title={album}>
          {album}
        </span>
      </div>
      {getStatusBadge()}
      {status?.error && (
        <span className="text-xs text-destructive ml-2" title={status.error}>
          {status.error}
        </span>
      )}
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export default function BatchUpdateStatusCard({
  librarySlug,
  jobId,
  albumsToSync,
  onComplete,
  onDismiss,
}: BatchUpdateStatusCardProps) {
  // Poll for status updates
  const { data: statusData } = useBatchUpdateStatus(
    librarySlug,
    jobId || undefined,
    {
      enabled: !!jobId,
      refetchInterval: 2000, // Poll every 2 seconds
    }
  )

  // Notify parent exactly once when the sync finishes. Calling onComplete
  // unconditionally during render fires it on every poll tick, which would
  // re-invalidate the items cache forever once the parent uses that hook.
  const hasNotifiedRef = useRef(false)
  useEffect(() => {
    if (hasNotifiedRef.current) return
    if (
      statusData?.status === 'completed' ||
      statusData?.status === 'partial' ||
      statusData?.status === 'failed'
    ) {
      hasNotifiedRef.current = true
      const succeeded =
        statusData.status === 'completed' &&
        (statusData.beets_updates ?? []).every((u) => u.status === 'success')
      onComplete?.(succeeded)
    }
  }, [statusData?.status, statusData?.beets_updates, onComplete])

  // Don't show if no job
  if (!jobId && albumsToSync.length === 0) {
    return null
  }

  // Calculate overall progress
  const beetsUpdates = statusData?.beets_updates || []
  const completedCount = beetsUpdates.filter(
    (u) => u.status === 'success' || u.status === 'failed'
  ).length
  const totalCount = albumsToSync.length || beetsUpdates.length
  const progress = totalCount > 0 ? (completedCount / totalCount) * 100 : 0

  // Get status label
  const getStatusLabel = () => {
    if (!statusData) return 'Queued'
    switch (statusData.status) {
      case 'pending':
        return 'Pending'
      case 'running':
        return 'Running'
      case 'completed':
        return 'Completed'
      case 'partial':
        return 'Partly failed'
      case 'failed':
        return 'Failed'
      default:
        return 'Unknown'
    }
  }

  const isComplete =
    statusData?.status === 'completed' ||
    statusData?.status === 'partial' ||
    statusData?.status === 'failed'
  const allSucceeded = beetsUpdates.every((u) => u.status === 'success')

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <RefreshCw className={`h-5 w-5 text-primary ${!isComplete ? 'animate-spin' : ''}`} />
            <CardTitle className="text-lg">Beets Database Sync</CardTitle>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Badge
              variant={
                statusData?.status === 'completed'
                  ? allSucceeded
                    ? 'default'
                    : 'destructive'
                  : statusData?.status === 'failed' ||
                      statusData?.status === 'partial'
                    ? 'destructive'
                    : 'secondary'
              }
            >
              {getStatusLabel()}
            </Badge>
            {/* Close button — only enabled once the sync has settled, so
                the user can't accidentally hide an in-flight job. */}
            {onDismiss && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={onDismiss}
                disabled={!isComplete}
                title={isComplete ? 'Dismiss' : 'Available once sync completes'}
                aria-label="Dismiss sync status"
              >
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Progress bar */}
        {!isComplete && (
          <div className="space-y-2">
            <Progress value={progress} className="h-2" />
            <p className="text-xs text-muted-foreground text-center">
              {completedCount} of {totalCount} albums synced
            </p>
          </div>
        )}

        {/* File write status */}
        {statusData?.file_writes && (
          <div className="text-sm space-y-1">
            <p className="font-medium">File Updates:</p>
            <div className="flex gap-4 text-muted-foreground">
              <span>{statusData.file_writes.succeeded} succeeded</span>
              {statusData.file_writes.failed > 0 && (
                <span className="text-destructive">{statusData.file_writes.failed} failed</span>
              )}
            </div>
          </div>
        )}

        {/* Per-album status list */}
        <div className="space-y-1">
          <p className="text-sm font-medium">Album Sync Status:</p>
          <div className="divide-y">
            {albumsToSync.map((album) => {
              const status = beetsUpdates.find((u) => u.album === album)
              return (
                <AlbumStatusItem
                  key={album}
                  album={album}
                  status={status}
                />
              )
            })}
          </div>
        </div>

        {/* Error message */}
        {statusData?.error && (
          <div className="text-sm text-destructive bg-destructive/10 p-2 rounded">
            {statusData.error}
          </div>
        )}

        {/* Completion message */}
        {isComplete && (
          <div className={`text-sm ${allSucceeded ? 'text-green-600' : 'text-amber-600'} bg-muted p-2 rounded`}>
            {allSucceeded
              ? 'All albums have been synced successfully. The beets database now reflects your changes.'
              : 'Some albums failed to sync. You may need to manually run `beet update` for the failed albums.'}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
