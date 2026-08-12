import React, { useMemo, useRef, useState, useEffect, useCallback } from 'react'
import { Loader2, FolderOpen, FileAudio, AlertCircle, ArrowRight, Play, Pause } from 'lucide-react'
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Input } from '@/components/ui/input'
import { useQueryClient } from '@tanstack/react-query'
import { useImportFolderItems } from '@/hooks/useImportFolderItems'
import { scanKeys } from '@/hooks/useScanStatus'
import { getImportItemAudioUrl } from '@/api/scan'
import { convertAudio, removeDuplicateWavs } from '@/api/beets-import'
import { LocalAlbumInfo } from '@/components/beets-import/CandidateDetailsCard'
import { useAudioOpJobs } from '@/components/beets-import/AudioOpJobsProvider'
import type { ImportItem } from '@/types/scan'
import type { ConvertAudioParams, ConvertTarget } from '@/types/beets-import'
import type { ItemPreview, TagName } from '@/types/batch-tag-editor'
import {
  initTrackOrder,
  applyManualNumber,
  applyDragReorder,
  trackOrderDiff,
  type TrackOrderEntry,
} from '@/lib/track-order'

// ============================================================================
// Types
// ============================================================================

interface ImportFolderTableProps {
  /** Library slug to fetch items for */
  librarySlug: string
  /** Selected folder path (null if none selected) */
  path: string | null
  /** Optional CSS class name */
  className?: string
  /** Preview data from batch tag editor (map of item ID to preview) */
  previewData?: Map<number, ItemPreview>
  /** Callback with item IDs when items are loaded */
  onItemsLoaded?: (itemIds: number[]) => void
  /**
   * Replace the plain "Selected folder" header with the richer Local Album
   * summary box (artist / album / track count / format) derived from the
   * scanned tags — no beets analysis required.
   */
  showSummary?: boolean
  /**
   * Batch editor's Track Number field is in Manual mode: rows become
   * drag-sortable and the Track # cell turns into a number input.
   */
  manualTrackNumbers?: boolean
  /**
   * Reports the item-id → track-number map of manual edits (only tracks whose
   * number differs from the scan) whenever the user types or drags.
   */
  onManualNumbersChange?: (values: Record<number, string>) => void
}

interface AlbumGroup {
  album: string
  tracks: ImportItem[]
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Formats track number as "x/y" if trackTotal is available, otherwise just "x".
 * Returns null if trackNumber is null.
 */
function formatTrackNumber(trackNumber: number | null, trackTotal: number | null): string | null {
  if (trackNumber === null) {
    return null
  }
  if (trackTotal !== null) {
    return `${trackNumber}/${trackTotal}`
  }
  return String(trackNumber)
}

/**
 * Groups tracks by album and sorts by track number within each group.
 */
function groupTracksByAlbum(items: ImportItem[]): AlbumGroup[] {
  const groups = new Map<string, ImportItem[]>()

  items.forEach((item) => {
    const album = item.album || 'Unknown Album'
    if (!groups.has(album)) {
      groups.set(album, [])
    }
    groups.get(album)!.push(item)
  })

  // Sort tracks within each album by track number
  const result: AlbumGroup[] = []
  groups.forEach((tracks, album) => {
    tracks.sort((a, b) => (a.trackNumber || 0) - (b.trackNumber || 0))
    result.push({ album, tracks })
  })

  // Sort album groups alphabetically
  result.sort((a, b) => a.album.localeCompare(b.album))

  return result
}

/**
 * Summarises container format(s) and bitrate across a folder's tracks for the
 * card header. A folder can hold mixed quality, so formats are de-duplicated
 * ("FLAC, MP3") and bitrate is shown as a range ("192–320 kbps") when it varies.
 * Returns null when no track carries either field (e.g. pre-migration scans).
 */
function summarizeAudioQuality(items: ImportItem[]): string | null {
  const formats = Array.from(
    new Set(
      items
        .map((item) => item.format)
        .filter((f): f is string => !!f)
        .map((f) => f.toUpperCase())
    )
  ).sort()

  const bitrates = items
    .map((item) => item.bitrate)
    .filter((b): b is number => typeof b === 'number' && b > 0)

  const parts: string[] = []
  if (formats.length > 0) {
    parts.push(formats.join(', '))
  }
  if (bitrates.length > 0) {
    const min = Math.min(...bitrates)
    const max = Math.max(...bitrates)
    parts.push(min === max ? `${min} kbps` : `${min}–${max} kbps`)
  }

  return parts.length > 0 ? parts.join(' · ') : null
}

/**
 * Picks the most frequent non-empty value, so a stray mistagged track doesn't
 * decide the album-level summary.
 */
function mostCommon(values: (string | null)[]): string | null {
  const counts = new Map<string, number>()
  for (const value of values) {
    if (!value) continue
    counts.set(value, (counts.get(value) ?? 0) + 1)
  }
  let best: string | null = null
  let bestCount = 0
  for (const [value, count] of counts) {
    if (count > bestCount) {
      best = value
      bestCount = count
    }
  }
  return best
}

/**
 * Derive an album-level summary (artist / album / dominant format) from the
 * scanned tags of a folder's tracks, for the Local Album summary box. Prefers
 * the album artist, falling back to the track artist.
 */
function summarizeLocalAlbum(items: ImportItem[]): {
  artist: string | null
  album: string | null
  dominantFormat: string | null
} {
  return {
    artist:
      mostCommon(items.map((i) => i.albumArtist)) ??
      mostCommon(items.map((i) => i.artist)),
    album: mostCommon(items.map((i) => i.album)),
    dominantFormat: mostCommon(items.map((i) => i.format))?.toUpperCase() ?? null,
  }
}

// Above this WMA bitrate (kbps) we recommend FLAC, else MP3 — mirrors the
// backend's wav_flac_service.recommend_wma_target so both entry points agree.
const WMA_FLAC_BITRATE_THRESHOLD_KBPS = 320

/**
 * Detect WAV/WMA files (and WAVs that have a same-basename FLAC twin) from the
 * scanned items, so the Local Album card can offer the convert / dedup actions
 * without a beets analysis. Matches the backend's wav_flac_service semantics:
 * per-directory, case-insensitive basename matching, recursive over the folder.
 * The WMA target recommendation follows the same bitrate rule as the backend.
 */
function summarizeAudioStatus(items: ImportItem[]): {
  hasWav: boolean
  duplicateWavCount: number
  hasWma: boolean
  wmaRecommendedTarget: ConvertTarget | null
} {
  // FLAC basenames per directory (lowercased) — used to spot WAVs with a twin.
  const flacByDir = new Map<string, Set<string>>()
  const wavs: { dir: string; base: string }[] = []
  let hasWma = false
  let maxWmaBitrate = 0
  for (const item of items) {
    const name = (item.filename ?? '').toLowerCase()
    const dot = name.lastIndexOf('.')
    if (dot < 0) continue
    const ext = name.slice(dot)
    const base = name.slice(0, dot)
    const dir = item.directory ?? ''
    if (ext === '.flac') {
      if (!flacByDir.has(dir)) flacByDir.set(dir, new Set())
      flacByDir.get(dir)!.add(base)
    } else if (ext === '.wav') {
      wavs.push({ dir, base })
    } else if (ext === '.wma') {
      hasWma = true
      if (typeof item.bitrate === 'number' && item.bitrate > maxWmaBitrate) {
        maxWmaBitrate = item.bitrate
      }
    }
  }
  const duplicateWavCount = wavs.filter((w) =>
    flacByDir.get(w.dir)?.has(w.base)
  ).length
  const wmaRecommendedTarget: ConvertTarget | null = hasWma
    ? maxWmaBitrate > WMA_FLAC_BITRATE_THRESHOLD_KBPS
      ? 'flac'
      : 'mp3'
    : null
  return {
    hasWav: wavs.length > 0,
    duplicateWavCount,
    hasWma,
    wmaRecommendedTarget,
  }
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

function AlbumIntertitleRow({ album }: { album: string }) {
  return (
    <TableRow className="bg-muted/50 hover:bg-muted/50">
      <TableCell colSpan={9} className="py-2">
        <span className="font-semibold text-sm">Album: {album}</span>
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
 * Leading cell with a play/pause toggle for the track.
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
}

/**
 * Cell that shows original value and preview value (if different)
 */
function PreviewCell({ original, preview, maxWidthClass, center }: PreviewCellProps) {
  const originalStr = original != null ? String(original) : '-'
  const hasPreview = preview !== undefined && preview !== originalStr && preview !== String(original)

  return (
    <TableCell className={`${maxWidthClass || ''} ${center ? 'text-center' : ''}`}>
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

interface TrackRowCellsProps {
  item: ImportItem
  preview?: ItemPreview
  isPlaying: boolean
  onTogglePlay: (item: ImportItem) => void
  /** Replaces the Track # preview cell (Manual mode's number input). */
  trackNumberCell?: React.ReactNode
}

/** The cells of one track row, shared by the plain and drag-sortable rows. */
function TrackRowCells({
  item,
  preview,
  isPlaying,
  onTogglePlay,
  trackNumberCell,
}: TrackRowCellsProps) {
  // Helper to get preview value for a tag
  const getPreview = (tag: TagName): string | undefined => {
    return preview?.changes[tag]
  }

  return (
    <>
      <PlayButtonCell
        isPlaying={isPlaying}
        onToggle={() => onTogglePlay(item)}
        trackLabel={item.title || item.filename || 'track'}
      />
      <TableCell className="max-w-[150px] truncate" title={item.directory}>
        {item.directory}
      </TableCell>
      <TableCell className="max-w-[200px] truncate" title={item.filename}>
        {item.filename}
      </TableCell>
      <PreviewCell
        original={item.album}
        preview={getPreview('album')}
        maxWidthClass="max-w-[150px]"
      />
      <PreviewCell
        original={item.albumArtist}
        preview={getPreview('album_artist')}
        maxWidthClass="max-w-[120px]"
      />
      <PreviewCell
        original={item.artist}
        preview={getPreview('artist')}
        maxWidthClass="max-w-[120px]"
      />
      <PreviewCell
        original={item.title}
        preview={getPreview('title')}
        maxWidthClass="max-w-[150px]"
      />
      {trackNumberCell ?? (
        <PreviewCell
          original={formatTrackNumber(item.trackNumber, item.trackTotal)}
          preview={getPreview('track_number')}
          maxWidthClass="w-[60px]"
          center
        />
      )}
      <PreviewCell
        original={item.genre}
        preview={getPreview('genre')}
        maxWidthClass="max-w-[100px]"
      />
    </>
  )
}

interface TrackRowProps {
  item: ImportItem
  preview?: ItemPreview
  isPlaying: boolean
  onTogglePlay: (item: ImportItem) => void
}

function TrackRow({ item, preview, isPlaying, onTogglePlay }: TrackRowProps) {
  return (
    <TableRow>
      <TrackRowCells
        item={item}
        preview={preview}
        isPlaying={isPlaying}
        onTogglePlay={onTogglePlay}
      />
    </TableRow>
  )
}

// ============================================================================
// Manual Track Numbering (batch editor Manual mode)
// ============================================================================

interface ManualNumberCellProps {
  entry: TrackOrderEntry
  onCommit: (itemId: number, typedNumber: number) => void
}

/**
 * Track # cell in Manual mode: a number input prefilled with the current
 * number. Committing (blur / Enter) moves the track to the typed position —
 * the table re-sorts and the other tracks shift automatically.
 */
function ManualNumberCell({ entry, onCommit }: ManualNumberCellProps) {
  const [draft, setDraft] = useState(String(entry.number))

  // Re-sync the input whenever a commit or drag renumbers this row.
  useEffect(() => {
    setDraft(String(entry.number))
  }, [entry.number])

  const commit = () => {
    const typed = parseInt(draft, 10)
    if (!Number.isFinite(typed) || typed < 1 || typed === entry.number) {
      setDraft(String(entry.number))
      return
    }
    onCommit(entry.itemId, typed)
  }

  return (
    <TableCell className="w-[70px] text-center">
      <Input
        type="number"
        min={1}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') e.currentTarget.blur()
        }}
        // Keep typing/selecting inside the input from starting a row drag.
        onPointerDown={(e) => e.stopPropagation()}
        className="h-8 w-16 text-center mx-auto"
        aria-label="Track number"
      />
      {entry.originalNumber !== entry.number && (
        <div className="mt-0.5 text-xs text-muted-foreground">
          was {entry.originalNumber ?? '–'}
        </div>
      )}
    </TableCell>
  )
}

interface SortableTrackRowProps extends TrackRowProps {
  entry: TrackOrderEntry
  onCommitNumber: (itemId: number, typedNumber: number) => void
}

/** A track row that is drag-sortable and carries the manual number input. */
function SortableTrackRow({
  item,
  preview,
  isPlaying,
  onTogglePlay,
  entry,
  onCommitNumber,
}: SortableTrackRowProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: item.id })

  return (
    <TableRow
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`cursor-grab active:cursor-grabbing ${
        isDragging ? 'relative z-10 bg-muted shadow-md' : ''
      }`}
      {...attributes}
      {...listeners}
    >
      <TrackRowCells
        item={item}
        preview={preview}
        isPlaying={isPlaying}
        onTogglePlay={onTogglePlay}
        trackNumberCell={<ManualNumberCell entry={entry} onCommit={onCommitNumber} />}
      />
    </TableRow>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export default function ImportFolderTable({
  librarySlug,
  path,
  className,
  previewData,
  onItemsLoaded,
  showSummary = false,
  manualTrackNumbers = false,
  onManualNumbersChange,
}: ImportFolderTableProps) {
  const { data, isLoading, error } = useImportFolderItems(librarySlug, path)

  // Shared audio player: a single <audio> element plays at most one track at a
  // time. `playingId` is the item id currently playing (or null).
  const audioRef = useRef<HTMLAudioElement>(null)
  const [playingId, setPlayingId] = useState<number | null>(null)

  const handleTogglePlay = useCallback(
    (item: ImportItem) => {
      const audio = audioRef.current
      if (!audio) return
      if (playingId === item.id) {
        audio.pause()
        setPlayingId(null)
        return
      }
      audio.src = getImportItemAudioUrl(librarySlug, item.id)
      audio.play().catch(() => setPlayingId(null))
      setPlayingId(item.id)
    },
    [librarySlug, playingId]
  )

  // Stop playback when the selected folder changes (the playing track may no
  // longer be in view).
  useEffect(() => {
    const audio = audioRef.current
    if (audio) {
      audio.pause()
      audio.removeAttribute('src')
    }
    setPlayingId(null)
  }, [path])

  // Files the last scan flagged "deleted" no longer exist on disk, so they must
  // not show up as tracks or feed the WAV/dedup actions — otherwise a deleted
  // WAV still sharing a folder with its FLAC looks like a removable duplicate,
  // and clicking it errors because the backend checks the live disk (issue #125).
  // The API already excludes deleted items by default; this is a belt-and-braces
  // guard against any path that fetches with an explicit status filter.
  const visibleItems = useMemo(
    () => (data?.items ?? []).filter((item) => item.status !== 'deleted'),
    [data?.items]
  )

  // Group tracks by album
  const albumGroups = useMemo(
    () => groupTracksByAlbum(visibleItems),
    [visibleItems]
  )

  // Notify parent of loaded item IDs (excluding deleted, which aren't real
  // tracks). Guarded on data presence so it stays quiet until a fetch resolves.
  React.useEffect(() => {
    if (data?.items && onItemsLoaded) {
      onItemsLoaded(visibleItems.map((item) => item.id))
    }
  }, [data?.items, visibleItems, onItemsLoaded])

  // Manual track-numbering state: the ordered rows (with editable numbers) for
  // this table while the batch editor's Track Number field is in Manual mode.
  const [manualOrder, setManualOrder] = useState<TrackOrderEntry[] | null>(null)

  // (Re)build the order when Manual mode turns on or the underlying items
  // change — including their stored numbers, so a successful Apply (which
  // refetches the items) resets the baseline instead of re-showing stale
  // diffs. Turning Manual mode off clears the state.
  useEffect(() => {
    if (!manualTrackNumbers) {
      setManualOrder(null)
      return
    }
    setManualOrder((prev) => {
      const itemsSignature = visibleItems
        .map((i) => `${i.id}:${i.trackNumber ?? ''}`)
        .sort()
        .join(',')
      const prevSignature = prev
        ?.map((e) => `${e.itemId}:${e.originalNumber ?? ''}`)
        .sort()
        .join(',')
      if (prev && itemsSignature === prevSignature) return prev
      return initTrackOrder(
        visibleItems.map((i) => ({
          id: i.id,
          trackNumber: i.trackNumber,
          filename: i.filename ?? '',
        }))
      )
    })
  }, [manualTrackNumbers, visibleItems])

  // Report the changed numbers upward so the batch editor can preview/apply.
  useEffect(() => {
    if (manualTrackNumbers && manualOrder && onManualNumbersChange) {
      onManualNumbersChange(trackOrderDiff(manualOrder))
    }
  }, [manualTrackNumbers, manualOrder, onManualNumbersChange])

  const handleCommitNumber = useCallback((itemId: number, typedNumber: number) => {
    setManualOrder((prev) => (prev ? applyManualNumber(prev, itemId, typedNumber) : prev))
  }, [])

  const handleDragEnd = useCallback((event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return
    setManualOrder((prev) => {
      if (!prev) return prev
      const from = prev.findIndex((e) => e.itemId === active.id)
      const to = prev.findIndex((e) => e.itemId === over.id)
      return applyDragReorder(prev, from, to)
    })
  }, [])

  // Whole rows are draggable; the distance constraint keeps plain clicks
  // (play button, input focus) from registering as drags.
  const dndSensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } })
  )

  const itemById = useMemo(() => {
    const map = new Map<number, ImportItem>()
    for (const item of visibleItems) map.set(item.id, item)
    return map
  }, [visibleItems])

  // Determine if we should show album intertitles
  const showIntertitles = albumGroups.length > 1

  // Aggregate container format(s) + bitrate for the header
  const qualitySummary = useMemo(
    () => (visibleItems.length ? summarizeAudioQuality(visibleItems) : null),
    [visibleItems]
  )

  // Album-level summary (artist / album / dominant format) for the Local Album
  // box, derived from scanned tags — available without a beets analysis.
  const localAlbumSummary = useMemo(
    () => (visibleItems.length ? summarizeLocalAlbum(visibleItems) : null),
    [visibleItems]
  )

  // WAV/WMA presence, duplicate count, and WMA target hint for the card actions.
  const audioStatus = useMemo(
    () => (visibleItems.length ? summarizeAudioStatus(visibleItems) : null),
    [visibleItems]
  )

  // WAV→FLAC convert / duplicate-WAV cleanup running on this folder. In the
  // combined import view the shared registry owns it (background, per-album);
  // these locals are the standalone-page fallback.
  const sharedJobs = useAudioOpJobs()
  const queryClient = useQueryClient()
  const [isAudioOpRunning, setIsAudioOpRunning] = useState(false)
  const [audioOpError, setAudioOpError] = useState<string | null>(null)
  // The Local Album card spins only when *this* folder has an active job —
  // keyed by its own path, so it no longer follows the selection around.
  const audioOpRunningForPath = sharedJobs
    ? !!path && sharedJobs.isActive(path)
    : isAudioOpRunning

  // Refetch the folder items after a WAV op so the table + summary reflect the
  // new on-disk files (e.g. WAVs replaced by FLACs).
  const refreshAfterAudioOp = useCallback(async () => {
    await queryClient.invalidateQueries({
      queryKey: [...scanKeys.importItems(), librarySlug],
    })
  }, [queryClient, librarySlug])

  const handleConvertAudio = useCallback(
    async (params: ConvertAudioParams) => {
      if (!path) return
      if (sharedJobs) {
        sharedJobs.startConvert(path, params)
        return
      }
      if (isAudioOpRunning) return
      const { sourceFormat, targetFormat, deleteOriginals } = params
      setAudioOpError(null)
      setIsAudioOpRunning(true)
      try {
        await convertAudio(librarySlug, path, sourceFormat, targetFormat, deleteOriginals)
      } catch (err) {
        setAudioOpError(err instanceof Error ? err.message : 'Conversion failed')
      } finally {
        // Always re-read the folder: on success the files changed on disk, and
        // on failure (e.g. a stale action that no longer matches the disk) this
        // recomputes the buttons so the dead option disappears (issue #125).
        await refreshAfterAudioOp()
        setIsAudioOpRunning(false)
      }
    },
    [path, sharedJobs, isAudioOpRunning, librarySlug, refreshAfterAudioOp]
  )

  const handleRemoveDuplicateWavs = useCallback(async () => {
    if (!path) return
    if (sharedJobs) {
      sharedJobs.startDedupe(path)
      return
    }
    if (isAudioOpRunning) return
    setAudioOpError(null)
    setIsAudioOpRunning(true)
    try {
      await removeDuplicateWavs(librarySlug, path)
    } catch (err) {
      setAudioOpError(err instanceof Error ? err.message : 'Cleanup failed')
    } finally {
      // See handleConvertWavs: refresh on both paths so a stale dedupe button
      // recomputes against the live disk instead of dead-ending (issue #125).
      await refreshAfterAudioOp()
      setIsAudioOpRunning(false)
    }
  }, [path, sharedJobs, isAudioOpRunning, librarySlug, refreshAfterAudioOp])

  // No folder selected
  if (!path) {
    return (
      <div className={`border rounded-md ${className || ''}`}>
        <EmptyState
          message="Select a folder to view tracks"
          icon={FolderOpen}
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

  // No scan completed yet
  if (!data?.scanId) {
    return (
      <div className={`border rounded-md ${className || ''}`}>
        <EmptyState
          message="This folder has not been scanned yet. Run a scan to discover tracks."
          icon={FileAudio}
        />
      </div>
    )
  }

  // No tracks found
  if (albumGroups.length === 0) {
    return (
      <div className={`border rounded-md ${className || ''}`}>
        <EmptyState
          message="No tracks found in this folder"
          icon={FileAudio}
        />
      </div>
    )
  }

  return (
    <div className={`border rounded-md ${className || ''}`}>
      {/* Header: the rich Local Album summary box, or the plain folder header */}
      {showSummary ? (
        <div className="p-3 border-b bg-muted/30">
          <LocalAlbumInfo
            path={path}
            artist={localAlbumSummary?.artist ?? null}
            album={localAlbumSummary?.album ?? null}
            trackCount={data.total}
            dominantFormat={localAlbumSummary?.dominantFormat ?? qualitySummary}
            hasWav={audioStatus?.hasWav ?? false}
            duplicateWavCount={audioStatus?.duplicateWavCount ?? 0}
            hasWma={audioStatus?.hasWma ?? false}
            wmaRecommendedTarget={audioStatus?.wmaRecommendedTarget ?? null}
            onConvertAudio={handleConvertAudio}
            onRemoveDuplicateWavs={handleRemoveDuplicateWavs}
            isAudioOpRunning={audioOpRunningForPath}
            audioOpError={audioOpError}
          />
        </div>
      ) : (
        <div className="p-3 border-b bg-muted/30">
          <p className="text-xs text-muted-foreground">Selected folder</p>
          <p className="text-sm font-mono truncate" title={path}>
            {path}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            {data.total} track{data.total !== 1 ? 's' : ''}
            {showIntertitles && ` in ${albumGroups.length} albums`}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {qualitySummary ?? '—'}
          </p>
        </div>
      )}

      {/* Shared audio element: stops/resets playing state when a track ends or fails */}
      <audio
        ref={audioRef}
        className="hidden"
        onEnded={() => setPlayingId(null)}
        onError={() => setPlayingId(null)}
      />

      {/* Table. In Manual numbering mode the rows are one flat drag-sortable
          list in the manual order (album intertitles would fight the single
          ordering), each with its number input. */}
      <DndContext
        sensors={dndSensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[44px]">
                <span className="sr-only">Play</span>
              </TableHead>
              <TableHead>Directory</TableHead>
              <TableHead>Filename</TableHead>
              <TableHead>Album</TableHead>
              <TableHead>Album Artist</TableHead>
              <TableHead>Artist</TableHead>
              <TableHead>Title</TableHead>
              <TableHead className="text-center">Track #</TableHead>
              <TableHead>Genre</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {manualTrackNumbers && manualOrder ? (
              <SortableContext
                items={manualOrder.map((e) => e.itemId)}
                strategy={verticalListSortingStrategy}
              >
                {manualOrder.map((entry) => {
                  const item = itemById.get(entry.itemId)
                  if (!item) return null
                  return (
                    <SortableTrackRow
                      key={item.id}
                      item={item}
                      preview={previewData?.get(item.id)}
                      isPlaying={playingId === item.id}
                      onTogglePlay={handleTogglePlay}
                      entry={entry}
                      onCommitNumber={handleCommitNumber}
                    />
                  )
                })}
              </SortableContext>
            ) : showIntertitles ? (
              albumGroups.map((group) => (
                <React.Fragment key={group.album}>
                  <AlbumIntertitleRow album={group.album} />
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
            ) : (
              albumGroups[0]?.tracks.map((item) => (
                <TrackRow
                  key={item.id}
                  item={item}
                  preview={previewData?.get(item.id)}
                  isPlaying={playingId === item.id}
                  onTogglePlay={handleTogglePlay}
                />
              ))
            )}
          </TableBody>
        </Table>
      </DndContext>
    </div>
  )
}
