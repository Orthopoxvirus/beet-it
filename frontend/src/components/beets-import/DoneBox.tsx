import { CheckCircle, Music } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

// ============================================================================
// Types
// ============================================================================

interface DoneBoxProps {
  /** List of successfully imported albums */
  albums: DoneAlbum[]
  /** Optional CSS class */
  className?: string
}

export interface DoneAlbum {
  /** Album folder path (original source path) */
  path: string
  /** Album folder name */
  name: string
  /** Artist name (if known) */
  artist: string | null
  /** Album name (if known) */
  album: string | null
  /** ISO 8601 timestamp of completion */
  completedAt: string
  /** Destination path in beets library */
  destinationPath?: string
}

interface DoneItemRowProps {
  album: DoneAlbum
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Format completion time relative to now.
 */
function formatCompletionTime(isoString: string): string {
  const completed = new Date(isoString)
  const now = new Date()
  const diffMs = now.getTime() - completed.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)

  if (diffSec < 60) {
    return 'Just now'
  } else if (diffMin < 60) {
    return `${diffMin}m ago`
  } else if (diffHour < 24) {
    return `${diffHour}h ago`
  } else {
    return completed.toLocaleDateString()
  }
}

// ============================================================================
// Subcomponents
// ============================================================================

function DoneItemRow({ album }: DoneItemRowProps) {
  return (
    <div
      className="flex items-center gap-3 p-3 rounded-lg border bg-green-500/5 border-green-500/25 transition-colors"
      data-testid="done-item"
    >
      {/* Checkmark icon */}
      <CheckCircle className="h-5 w-5 text-green-500 flex-shrink-0" />

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

      {/* Completion time */}
      <span className="text-xs text-muted-foreground flex-shrink-0">
        {formatCompletionTime(album.completedAt)}
      </span>
    </div>
  )
}

function DoneEmpty() {
  return (
    <div className="flex flex-col items-center justify-center py-8 text-center px-4">
      <Music className="h-8 w-8 text-muted-foreground/50" />
      <p className="text-sm text-muted-foreground mt-2">
        No imports completed yet
      </p>
      <p className="text-xs text-muted-foreground mt-1">
        Successfully imported albums will appear here
      </p>
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * Box displaying successfully imported albums.
 * Only shown in copy mode (not move mode).
 */
export default function DoneBox({
  albums,
  className,
}: DoneBoxProps) {
  const albumCount = albums.length
  const isEmpty = albumCount === 0

  // Sort by completion time, most recent first
  const sortedAlbums = [...albums].sort((a, b) => {
    const timeA = new Date(a.completedAt).getTime()
    const timeB = new Date(b.completedAt).getTime()
    return timeB - timeA
  })

  return (
    <Card className={cn('flex flex-col', className)} data-testid="done-box">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            <CheckCircle className={cn('h-4 w-4', albumCount > 0 ? 'text-green-500' : 'text-muted-foreground')} />
            Done
            {albumCount > 0 && (
              <Badge variant="secondary" className="bg-green-500/20 text-green-700 dark:text-green-300">
                {albumCount}
              </Badge>
            )}
          </CardTitle>
        </div>
      </CardHeader>

      <CardContent className="flex-1 p-0">
        {isEmpty ? (
          <div className="px-6 pb-6">
            <DoneEmpty />
          </div>
        ) : (
          <div className="max-h-[200px] overflow-y-auto">
            <div className="space-y-1.5 p-3 pt-0">
              {sortedAlbums.map((album) => (
                <DoneItemRow key={album.path} album={album} />
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
