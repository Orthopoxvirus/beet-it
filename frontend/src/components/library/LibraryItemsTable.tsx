import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Loader2,
  Music,
  AlertCircle,
  ArrowRight,
  Play,
  Pause,
  ListOrdered,
  GripVertical,
  ChevronUp,
  ChevronDown,
} from 'lucide-react'

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { getTrackStreamUrl } from '@/api/albums'
import type { LibraryItem } from '@/api/libraryItems'
import type { ItemPreview, TagName } from '@/types/batch-tag-editor'
import { partitionKey, nudge, moveWithinPartition } from '@/lib/reorder'

// ============================================================================
// Types
// ============================================================================

interface LibraryItemsTableProps {
  /** Library slug — used to build per-track audio stream URLs */
  librarySlug: string
  /** Library items to display */
  items: LibraryItem[]
  /** Whether data is loading */
  isLoading: boolean
  /** Error if any */
  error: Error | null
  /** Selected album name for display */
  selectedAlbum: string | null
  /** Total item count */
  total: number
  /** Optional CSS class name */
  className?: string
  /** Preview data from batch tag editor (map of item ID to preview) */
  previewData?: Map<number, ItemPreview>
  /**
   * Whether the Reorder control is offered. Gated upstream to single-album
   * selections with no active filters (reorder is "within album, within disc").
   */
  canReorder?: boolean
  /** Whether reorder mode is currently active. */
  reorderMode?: boolean
  /** Toggle reorder mode (the "Reorder" / "Done" button). */
  onToggleReorder?: () => void
  /** "Keep track titles" toggle — pins titles to their slot while tracks move. */
  keepTitles?: boolean
  /** Change the "Keep track titles" toggle. */
  onKeepTitlesChange?: (value: boolean) => void
  /** Working order of item ids while reordering. */
  order?: number[]
  /** Emit the next order after a drag or up/down move. */
  onReorder?: (next: number[]) => void
}

interface AlbumGroup {
  album: string
  tracks: LibraryItem[]
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Formats track number as "x/y" if both numbers available, otherwise just "x".
 */
function formatTrackNumber(trackNumber: number): string {
  return String(trackNumber)
}

/**
 * Builds the album-header summary parts shown floating right on each album
 * intertitle row: distinct container format(s), the average bitrate in kbps,
 * and the track count. Joined with middots by the caller.
 *
 * Bitrate is averaged across tracks (beets stores it in bits/s) and rounded
 * to kbps; formats are uppercased and de-duplicated so a mixed FLAC+MP3 album
 * reads "FLAC, MP3".
 */
function summarizeAlbumMeta(tracks: LibraryItem[]): string[] {
  const parts: string[] = []

  const formats = Array.from(
    new Set(
      tracks.map((t) => (t.format || '').trim().toUpperCase()).filter(Boolean)
    )
  ).sort()
  if (formats.length) parts.push(formats.join(', '))

  const bitrates = tracks
    .map((t) => t.bitrate)
    .filter((b): b is number => typeof b === 'number' && b > 0)
  if (bitrates.length) {
    const avg = bitrates.reduce((sum, b) => sum + b, 0) / bitrates.length
    parts.push(`${Math.round(avg / 1000)} kbps`)
  }

  parts.push(`${tracks.length} ${tracks.length === 1 ? 'track' : 'tracks'}`)
  return parts
}

/**
 * Groups tracks by album and sorts by track number within each group.
 */
function groupTracksByAlbum(items: LibraryItem[]): AlbumGroup[] {
  const groups = new Map<string, LibraryItem[]>()

  items.forEach((item) => {
    const album = item.album || 'Unknown Album'
    if (!groups.has(album)) {
      groups.set(album, [])
    }
    groups.get(album)!.push(item)
  })

  // Sort tracks within each album by disc then track number
  const result: AlbumGroup[] = []
  groups.forEach((tracks, album) => {
    tracks.sort((a, b) => {
      if (a.disc_number !== b.disc_number) {
        return a.disc_number - b.disc_number
      }
      return a.track_number - b.track_number
    })
    result.push({ album, tracks })
  })

  // Sort album groups alphabetically
  result.sort((a, b) => a.album.localeCompare(b.album))

  return result
}

// ============================================================================
// Sub-Components
// ============================================================================

function EmptyState({ message, icon: Icon }: { message: string; icon: React.ElementType }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center px-4">
      <Icon className="h-10 w-10 text-muted-foreground/50" />
      <p className="mt-3 text-sm text-muted-foreground">{message}</p>
    </div>
  )
}

function LoadingState() {
  return (
    <div className="flex items-center justify-center py-12">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      <span className="ml-2 text-sm text-muted-foreground">Loading tracks...</span>
    </div>
  )
}

function AlbumIntertitleRow({ group }: { group: AlbumGroup }) {
  const meta = summarizeAlbumMeta(group.tracks)
  return (
    <TableRow className="bg-muted/50 hover:bg-muted/50">
      <TableCell colSpan={7} className="py-2">
        <div className="flex items-center justify-between gap-4">
          <span className="font-semibold text-sm truncate">
            Album: {group.album}
          </span>
          <span className="text-xs text-muted-foreground whitespace-nowrap shrink-0">
            {meta.join(' · ')}
          </span>
        </div>
      </TableCell>
    </TableRow>
  )
}

// ============================================================================
// Play Button Cell
// ============================================================================

interface PlayButtonCellProps {
  isPlaying: boolean
  onToggle: () => void
  trackLabel: string
}

/**
 * Leading cell with a play/pause toggle for the track. Mirrors the import
 * folder table's audio card so the two surfaces behave identically.
 */
function PlayButtonCell({ isPlaying, onToggle, trackLabel }: PlayButtonCellProps) {
  return (
    <TableCell className="w-[44px] text-center">
      <button
        type="button"
        onClick={onToggle}
        className="inline-flex h-8 w-8 items-center justify-center rounded-full text-muted-foreground hover:text-primary hover:bg-primary/10"
        aria-label={isPlaying ? `Pause ${trackLabel}` : `Play ${trackLabel}`}
      >
        {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
      </button>
    </TableCell>
  )
}

// ============================================================================
// Preview Cell Component
// ============================================================================

interface PreviewCellProps {
  /** Original value */
  original: string | number | null | undefined
  /** Preview value (from batch editor) */
  preview: string | undefined
  /** Max width class */
  maxWidthClass?: string
  /** Whether to center text */
  center?: boolean
  /** Extra class names applied to the <TableCell> (e.g. responsive hide utilities) */
  className?: string
}

/**
 * Cell that shows original value and preview value (if different)
 */
function PreviewCell({ original, preview, maxWidthClass, center, className }: PreviewCellProps) {
  const originalStr = original != null ? String(original) : '-'
  const hasPreview = preview !== undefined && preview !== originalStr && preview !== String(original)

  return (
    <TableCell className={`${maxWidthClass || ''} ${center ? 'text-center' : ''} ${className || ''}`}>
      <div className="space-y-0.5">
        <div className={`truncate ${hasPreview ? 'text-muted-foreground line-through' : ''}`} title={originalStr}>
          {originalStr}
        </div>
        {hasPreview && (
          <div className="flex items-center gap-1 text-primary text-xs font-medium">
            <ArrowRight className="h-3 w-3 flex-shrink-0" />
            <span className="truncate" title={preview}>
              {preview}
            </span>
          </div>
        )}
      </div>
    </TableCell>
  )
}

// ============================================================================
// Track Row with Preview Support
// ============================================================================

interface TrackRowProps {
  item: LibraryItem
  preview?: ItemPreview
  isPlaying: boolean
  onTogglePlay: (item: LibraryItem) => void
}

function TrackRow({ item, preview, isPlaying, onTogglePlay }: TrackRowProps) {
  // Helper to get preview value for a tag
  const getPreview = (tag: TagName): string | undefined => {
    return preview?.changes[tag]
  }

  return (
    <TableRow>
      <PlayButtonCell
        isPlaying={isPlaying}
        onToggle={() => onTogglePlay(item)}
        trackLabel={item.title || 'track'}
      />
      <PreviewCell
        original={formatTrackNumber(item.track_number)}
        preview={getPreview('track_number')}
        maxWidthClass="w-[60px]"
        center
      />
      <PreviewCell
        original={item.title}
        preview={getPreview('title')}
        maxWidthClass="max-w-[200px]"
      />
      <PreviewCell
        original={item.artist}
        preview={getPreview('artist')}
        maxWidthClass="max-w-[150px]"
      />
      <PreviewCell
        original={item.album}
        preview={getPreview('album')}
        maxWidthClass="max-w-[150px]"
        className="hidden md:table-cell"
      />
      <PreviewCell
        original={item.album_artist}
        preview={getPreview('album_artist')}
        maxWidthClass="max-w-[150px]"
        className="hidden md:table-cell"
      />
      <PreviewCell
        original={item.genre}
        preview={getPreview('genre')}
        maxWidthClass="max-w-[100px]"
        className="hidden lg:table-cell"
      />
    </TableRow>
  )
}

// ============================================================================
// Reorder Row
// ============================================================================

interface ReorderRowProps {
  item: LibraryItem
  preview?: ItemPreview
  canUp: boolean
  canDown: boolean
  isDragging: boolean
  isDropTarget: boolean
  onMoveUp: () => void
  onMoveDown: () => void
  onDragStart: () => void
  onDragEnter: () => void
  onDrop: () => void
  onDragEnd: () => void
}

/**
 * A draggable track row shown in reorder mode. Carries a drag handle plus
 * up/down buttons (the accessible, testable path), and renders the Track # /
 * Title preview so the user sees exactly what "Apply Changes" will commit.
 */
function ReorderRow({
  item,
  preview,
  canUp,
  canDown,
  isDragging,
  isDropTarget,
  onMoveUp,
  onMoveDown,
  onDragStart,
  onDragEnter,
  onDrop,
  onDragEnd,
}: ReorderRowProps) {
  const getPreview = (tag: TagName): string | undefined => preview?.changes[tag]
  const label = item.title || 'track'

  return (
    <TableRow
      draggable
      onDragStart={onDragStart}
      onDragOver={(e) => e.preventDefault()}
      onDragEnter={onDragEnter}
      onDrop={(e) => {
        e.preventDefault()
        onDrop()
      }}
      onDragEnd={onDragEnd}
      className={[
        'cursor-grab select-none',
        isDragging ? 'opacity-50' : '',
        isDropTarget ? 'border-t-2 border-primary' : '',
      ].join(' ')}
      data-testid={`reorder-row-${item.id}`}
    >
      <TableCell className="w-[88px]">
        <div className="flex items-center gap-1">
          <GripVertical className="h-4 w-4 text-muted-foreground shrink-0" aria-hidden />
          <div className="flex flex-col">
            <button
              type="button"
              onClick={onMoveUp}
              disabled={!canUp}
              aria-label={`Move ${label} up`}
              className="text-muted-foreground hover:text-primary disabled:opacity-30 disabled:hover:text-muted-foreground"
            >
              <ChevronUp className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={onMoveDown}
              disabled={!canDown}
              aria-label={`Move ${label} down`}
              className="text-muted-foreground hover:text-primary disabled:opacity-30 disabled:hover:text-muted-foreground"
            >
              <ChevronDown className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </TableCell>
      <PreviewCell
        original={formatTrackNumber(item.track_number)}
        preview={getPreview('track_number')}
        maxWidthClass="w-[80px]"
        center
      />
      <PreviewCell
        original={item.title}
        preview={getPreview('title')}
        maxWidthClass="max-w-[280px]"
      />
      <TableCell className="max-w-[150px] hidden sm:table-cell">
        <span className="block truncate text-muted-foreground" title={item.artist || ''}>
          {item.artist || '-'}
        </span>
      </TableCell>
    </TableRow>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export default function LibraryItemsTable({
  librarySlug,
  items,
  isLoading,
  error,
  selectedAlbum,
  total,
  className,
  previewData,
  canReorder = false,
  reorderMode = false,
  onToggleReorder,
  keepTitles = false,
  onKeepTitlesChange,
  order,
  onReorder,
}: LibraryItemsTableProps) {
  // Shared audio player: a single <audio> element plays at most one track at a
  // time. `playingId` is the library item id currently playing (or null).
  // Streams via the existing GET /libraries/{slug}/tracks/{id}/stream endpoint.
  const audioRef = useRef<HTMLAudioElement>(null)
  const [playingId, setPlayingId] = useState<number | null>(null)

  const handleTogglePlay = useCallback(
    (item: LibraryItem) => {
      const audio = audioRef.current
      if (!audio) return
      if (playingId === item.id) {
        audio.pause()
        setPlayingId(null)
        return
      }
      audio.src = getTrackStreamUrl(librarySlug, item.id)
      audio.play().catch(() => setPlayingId(null))
      setPlayingId(item.id)
    },
    [librarySlug, playingId]
  )

  // Stop playback when the visible item set changes — switching folders or
  // applying a filter can drop the playing track out of view, and a hidden
  // track playing on is confusing. `items` is a fresh reference whenever the
  // selection or active filters change (memoized upstream), so keying on it
  // covers both cases without firing on unrelated re-renders (e.g. typing in
  // the batch editor, which only changes previewData).
  useEffect(() => {
    const audio = audioRef.current
    if (audio) {
      audio.pause()
      audio.removeAttribute('src')
    }
    setPlayingId(null)
  }, [items, reorderMode])

  // Group tracks by album
  const albumGroups = useMemo(() => {
    if (!items || items.length === 0) return []
    return groupTracksByAlbum(items)
  }, [items])

  // Header-card summary: format(s) · avg bitrate · track count across the
  // whole selection. For a single album this is the only place the quality
  // facts surface (no intertitle row is rendered for one group).
  const headerMeta = useMemo(
    () => (items && items.length ? summarizeAlbumMeta(items).join(' · ') : ''),
    [items]
  )

  // Determine if we should show album intertitles
  const showIntertitles = albumGroups.length > 1

  // --- Reorder mode -------------------------------------------------------
  const [draggedId, setDraggedId] = useState<number | null>(null)
  const [dragOverId, setDragOverId] = useState<number | null>(null)

  const itemsById = useMemo(
    () => new Map(items.map((i) => [i.id, i])),
    [items]
  )

  // The list rendered in reorder mode: the working `order` resolved to items,
  // falling back to the items' own order if the parent hasn't seeded one yet.
  const orderedItems = useMemo(() => {
    const ids = order && order.length ? order : items.map((i) => i.id)
    return ids
      .map((id) => itemsById.get(id))
      .filter((i): i is LibraryItem => i != null)
  }, [order, items, itemsById])

  const currentOrder = useMemo(
    () => orderedItems.map((i) => i.id),
    [orderedItems]
  )

  // Multiple discs in the selection get a "Disc N" divider so reorder
  // boundaries (numbering restarts per disc) are visible.
  const hasMultipleDiscs = useMemo(
    () => new Set(items.map((i) => i.disc_number)).size > 1,
    [items]
  )

  const handleMove = useCallback(
    (id: number, dir: -1 | 1) => {
      onReorder?.(nudge(currentOrder, items, id, dir))
    },
    [onReorder, currentOrder, items]
  )

  const handleDrop = useCallback(
    (targetId: number) => {
      if (draggedId != null) {
        onReorder?.(moveWithinPartition(currentOrder, items, draggedId, targetId))
      }
      setDraggedId(null)
      setDragOverId(null)
    },
    [draggedId, onReorder, currentOrder, items]
  )

  // No album selected
  if (!selectedAlbum) {
    return (
      <div className={`border rounded-md ${className || ''}`}>
        <EmptyState
          message="Select an album to view and edit tracks"
          icon={Music}
        />
      </div>
    )
  }

  // Loading state
  if (isLoading) {
    return (
      <div className={`border rounded-md ${className || ''}`}>
        <LoadingState />
      </div>
    )
  }

  // Error state
  if (error) {
    return (
      <div className={`border rounded-md ${className || ''}`}>
        <div className="flex flex-col items-center justify-center py-12 text-center px-4">
          <AlertCircle className="h-10 w-10 text-destructive/70" />
          <p className="mt-3 text-sm text-destructive">Failed to load tracks</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {error instanceof Error ? error.message : 'Unknown error'}
          </p>
        </div>
      </div>
    )
  }

  // No tracks found
  if (albumGroups.length === 0) {
    return (
      <div className={`border rounded-md ${className || ''}`}>
        <EmptyState
          message="No tracks found for this album"
          icon={Music}
        />
      </div>
    )
  }

  return (
    <div className={`border rounded-md ${className || ''}`}>
      {/* Header showing selected album */}
      <div className="p-3 border-b bg-muted/30 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">Selected album</p>
          <p className="text-sm font-medium truncate" title={selectedAlbum}>
            {selectedAlbum}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            {headerMeta || `${total} track${total !== 1 ? 's' : ''}`}
          </p>
        </div>

        {/* Reorder control — only offered for a single-album, unfiltered view. */}
        {(canReorder || reorderMode) && (
          <div className="flex flex-col items-end gap-2 shrink-0">
            <Button
              type="button"
              variant={reorderMode ? 'secondary' : 'outline'}
              size="sm"
              className="h-8"
              onClick={onToggleReorder}
            >
              <ListOrdered className="h-4 w-4 mr-1.5" />
              {reorderMode ? 'Done' : 'Reorder'}
            </Button>
            {reorderMode && (
              <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
                <span>Keep track titles</span>
                <Switch
                  checked={keepTitles}
                  onCheckedChange={(v) => onKeepTitlesChange?.(v)}
                  aria-label="Keep track titles"
                />
              </label>
            )}
          </div>
        )}
      </div>

      {reorderMode && (
        <div className="px-3 py-2 border-b bg-primary/5 text-xs text-muted-foreground">
          Drag tracks or use the arrows to reorder within the album.{' '}
          {keepTitles
            ? 'Titles stay in place; each track adopts the title of its new position.'
            : 'Each track keeps its title and is renumbered to its new position.'}{' '}
          Press <span className="font-medium text-foreground">Apply Changes</span> to commit.
        </div>
      )}

      {/* Table — wrapped in an x-scroll container so the table can keep all
          editable columns without forcing the whole page to scroll sideways
          on narrow viewports. Album / Album Artist / Genre are hidden below
          md because Title + Artist are the columns users actually scan in a
          batch edit. Duration is intentionally absent: it's a file-level
          fact the user can't change here. */}
      {/* Shared audio element: stops/resets playing state when a track ends or fails */}
      <audio
        ref={audioRef}
        className="hidden"
        onEnded={() => setPlayingId(null)}
        onError={() => setPlayingId(null)}
      />

      <div className="overflow-x-auto">
      {reorderMode ? (
        <Table className="min-w-[480px]">
          <TableHeader>
            <TableRow>
              <TableHead className="w-[88px]">
                <span className="sr-only">Reorder</span>
              </TableHead>
              <TableHead className="text-center w-[80px]">Track #</TableHead>
              <TableHead>Title</TableHead>
              <TableHead className="hidden sm:table-cell">Artist</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {orderedItems.map((item, index) => {
              const prev = orderedItems[index - 1]
              const next = orderedItems[index + 1]
              const key = partitionKey(item)
              const canUp = !!prev && partitionKey(prev) === key
              const canDown = !!next && partitionKey(next) === key
              const showDiscDivider =
                hasMultipleDiscs &&
                (!prev || prev.disc_number !== item.disc_number)

              return (
                <React.Fragment key={item.id}>
                  {showDiscDivider && (
                    <TableRow className="bg-muted/50 hover:bg-muted/50">
                      <TableCell colSpan={4} className="py-1.5 text-xs font-semibold">
                        Disc {item.disc_number}
                      </TableCell>
                    </TableRow>
                  )}
                  <ReorderRow
                    item={item}
                    preview={previewData?.get(item.id)}
                    canUp={canUp}
                    canDown={canDown}
                    isDragging={draggedId === item.id}
                    isDropTarget={dragOverId === item.id && draggedId !== item.id}
                    onMoveUp={() => handleMove(item.id, -1)}
                    onMoveDown={() => handleMove(item.id, 1)}
                    onDragStart={() => setDraggedId(item.id)}
                    onDragEnter={() => setDragOverId(item.id)}
                    onDrop={() => handleDrop(item.id)}
                    onDragEnd={() => {
                      setDraggedId(null)
                      setDragOverId(null)
                    }}
                  />
                </React.Fragment>
              )
            })}
          </TableBody>
        </Table>
      ) : (
        <Table className="min-w-[640px]">
          <TableHeader>
            <TableRow>
              <TableHead className="w-[44px]">
                <span className="sr-only">Play</span>
              </TableHead>
              <TableHead className="text-center w-[60px]">Track #</TableHead>
              <TableHead>Title</TableHead>
              <TableHead>Artist</TableHead>
              <TableHead className="hidden md:table-cell">Album</TableHead>
              <TableHead className="hidden md:table-cell">Album Artist</TableHead>
              <TableHead className="hidden lg:table-cell">Genre</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {showIntertitles
              ? albumGroups.map((group) => (
                  <React.Fragment key={group.album}>
                    <AlbumIntertitleRow group={group} />
                    {group.tracks.map((item) => (
                      <TrackRow
                        key={item.id}
                        item={item}
                        preview={previewData?.get(item.id)}
                        isPlaying={playingId === item.id}
                        onTogglePlay={handleTogglePlay}
                      />
                    ))}
                  </React.Fragment>
                ))
              : albumGroups[0]?.tracks.map((item) => (
                  <TrackRow
                    key={item.id}
                    item={item}
                    preview={previewData?.get(item.id)}
                    isPlaying={playingId === item.id}
                    onTogglePlay={handleTogglePlay}
                  />
                ))}
          </TableBody>
        </Table>
      )}
      </div>
    </div>
  )
}
