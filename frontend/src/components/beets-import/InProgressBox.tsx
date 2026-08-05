import { Loader2, ListOrdered, Music } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { ImportJobState } from '@/hooks/useBeetsImport'

// ============================================================================
// Types
// ============================================================================

interface InProgressBoxProps {
  /** List of albums with active import jobs */
  albums: InProgressAlbum[]
  /** Optional CSS class */
  className?: string
}

export interface InProgressAlbum {
  /** Album folder path */
  path: string
  /** Album folder name */
  name: string
  /** Artist name (if known) */
  artist: string | null
  /** Album name (if known) */
  album: string | null
  /** Import job state */
  jobState: ImportJobState
  /** Queue position (1-indexed, only for pending jobs) */
  queuePosition?: number
}

interface InProgressItemRowProps {
  album: InProgressAlbum
}

// ============================================================================
// Subcomponents
// ============================================================================

function InProgressItemRow({ album }: InProgressItemRowProps) {
  const isPending = album.jobState.status === 'pending'
  const isImporting = album.jobState.status === 'in_progress'

  return (
    <div
      className={cn(
        'flex items-center gap-3 p-3 rounded-lg border transition-colors',
        isImporting
          ? 'bg-blue-500/5 border-blue-500/25'
          : 'bg-amber-500/5 border-amber-500/25'
      )}
      data-testid="in-progress-item"
    >
      {/* Album icon */}
      <Music className="h-5 w-5 text-blue-500 flex-shrink-0" />

      {/* Album info */}
      <div className="flex-1 min-w-0">
        <div className="font-medium text-sm truncate" title={album.name}>
          {album.name}
        </div>
        {(album.artist || album.album) && (
          <div className="text-xs text-muted-foreground truncate mt-0.5">
            {album.artist && album.album
              ? `${album.artist} - ${album.album}`
              : album.artist || album.album}
          </div>
        )}
      </div>

      {/* Status badge */}
      {isImporting ? (
        <Badge
          variant="secondary"
          className="flex-shrink-0 bg-blue-500/20 text-blue-700 dark:text-blue-300 border-blue-500/30"
        >
          <Loader2 className="h-3 w-3 mr-1 animate-spin" />
          Importing...
        </Badge>
      ) : isPending && album.queuePosition !== undefined ? (
        <Badge
          variant="secondary"
          className="flex-shrink-0 bg-amber-500/20 text-amber-700 dark:text-amber-300 border-amber-500/30"
        >
          <ListOrdered className="h-3 w-3 mr-1" />
          Queued (#{album.queuePosition})
        </Badge>
      ) : (
        <Badge
          variant="secondary"
          className="flex-shrink-0 bg-amber-500/20 text-amber-700 dark:text-amber-300 border-amber-500/30"
        >
          <ListOrdered className="h-3 w-3 mr-1" />
          Queued
        </Badge>
      )}
    </div>
  )
}

function InProgressEmpty() {
  return (
    <div className="flex flex-col items-center justify-center py-8 text-center px-4">
      <p className="text-sm text-muted-foreground">
        No imports in progress
      </p>
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * Box displaying albums with active import jobs.
 * Shows queue position for pending jobs and spinner for active imports.
 */
export default function InProgressBox({
  albums,
  className,
}: InProgressBoxProps) {
  const albumCount = albums.length
  const isEmpty = albumCount === 0

  // Sort: in_progress first, then pending by queue position
  const sortedAlbums = [...albums].sort((a, b) => {
    if (a.jobState.status === 'in_progress' && b.jobState.status !== 'in_progress') return -1
    if (a.jobState.status !== 'in_progress' && b.jobState.status === 'in_progress') return 1
    // Both same status - sort by queue position if available
    const posA = a.queuePosition ?? Infinity
    const posB = b.queuePosition ?? Infinity
    return posA - posB
  })

  return (
    <Card className={cn('flex flex-col', className)} data-testid="in-progress-box">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            <Loader2 className={cn('h-4 w-4', albumCount > 0 && 'animate-spin text-blue-500')} />
            In Progress
            {albumCount > 0 && (
              <Badge variant="secondary">
                {albumCount}
              </Badge>
            )}
          </CardTitle>
        </div>
      </CardHeader>

      <CardContent className="flex-1">
        {isEmpty ? (
          <InProgressEmpty />
        ) : (
          <div className="max-h-[400px] overflow-y-auto">
            <div className="space-y-1.5">
              {sortedAlbums.map((album) => (
                <InProgressItemRow key={album.path} album={album} />
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
