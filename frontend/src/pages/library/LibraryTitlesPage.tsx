import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useOutletContext, useSearchParams } from 'react-router-dom'
import {
  AlertCircle,
  Check,
  ChevronLeft,
  ChevronRight,
  Download,
  ListPlus,
  Loader2,
  Music,
  Pause,
  Play,
  Plus,
  Search,
  Volume2,
  X,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { toast } from '@/components/ui/toast'
import { useTitles, useTitleArtists } from '@/hooks/useTitles'
import { useDebouncedValue } from '@/hooks/useTagPreview'
import { useDownloadGather } from '@/contexts/DownloadGatherContext'
import { ArtistFilter } from '@/components/library/ArtistFilter'
import {
  fetchTitleIds,
  getTitleDownloadUrl,
  getTitleStreamUrl,
  type TitleFilters,
  type TitleRow,
} from '@/api/titles'
import type { LibraryDetailContext } from '../LibraryDetailLayout'

const PER_PAGE = 100

// Default playback volume. Deliberately low so opening the page and hitting
// play never blasts anyone at full volume. Persisted per browser once changed.
const DEFAULT_VOLUME = 0.3
const VOLUME_STORAGE_KEY = 'titles-player-volume'

function readStoredVolume(): number {
  if (typeof window === 'undefined') return DEFAULT_VOLUME
  try {
    const raw = window.localStorage.getItem(VOLUME_STORAGE_KEY)
    if (raw == null) return DEFAULT_VOLUME
    const v = parseFloat(raw)
    return Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : DEFAULT_VOLUME
  } catch {
    return DEFAULT_VOLUME
  }
}

// Filters + page live in the URL (?q=…&bpmMin=…&artist=…&page=…) so a reload
// or back-navigation restores the exact list the user was looking at.
function parseTitlesParams(params: URLSearchParams) {
  const page = parseInt(params.get('page') ?? '', 10)
  return {
    search: params.get('q') ?? '',
    bpmMin: params.get('bpmMin') ?? '',
    bpmMax: params.get('bpmMax') ?? '',
    includeHalfDouble: params.get('halfDouble') === '1',
    artists: params.getAll('artist'),
    page: Number.isFinite(page) && page > 0 ? page : 1,
  }
}

function formatLength(seconds: number | null): string {
  if (!seconds || seconds <= 0) return '–'
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

function TitleActions({ slug, row }: { slug: string; row: TitleRow }) {
  const { isTrackGathered, addTracks, removeTrack } = useDownloadGather()
  const gathered = isTrackGathered(row.id)
  return (
    <div className="flex justify-end gap-1">
      <Button
        size="icon"
        variant={gathered ? 'default' : 'ghost'}
        onClick={() =>
          gathered
            ? removeTrack(row.id)
            : addTracks(slug, [{ id: row.id, title: row.title, artist: row.artist }])
        }
        title={gathered ? 'Remove from download selection' : 'Mark for download'}
        aria-label={gathered ? `Remove ${row.title} from selection` : `Mark ${row.title} for download`}
        aria-pressed={gathered}
      >
        {gathered ? <Check className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
      </Button>
      <Button size="icon" variant="ghost" asChild title="Download this title">
        <a href={getTitleDownloadUrl(slug, row.id)} download aria-label={`Download ${row.title}`}>
          <Download className="h-4 w-4" />
        </a>
      </Button>
    </div>
  )
}

interface TitleTableRowProps {
  slug: string
  row: TitleRow
  isPlaying: boolean
  onTogglePlay: (row: TitleRow) => void
}

// Memoised so the volume slider (page-level state) doesn't re-render every row
// on each drag tick — only the row whose `isPlaying` flips actually updates.
const TitleTableRow = memo(function TitleTableRow({
  slug,
  row,
  isPlaying,
  onTogglePlay,
}: TitleTableRowProps) {
  return (
    <TableRow>
      <TableCell className="w-10 pr-0">
        <Button
          size="icon"
          variant="ghost"
          className="h-8 w-8"
          onClick={() => onTogglePlay(row)}
          title={isPlaying ? 'Pause' : 'Play'}
          aria-label={isPlaying ? `Pause ${row.title}` : `Play ${row.title}`}
          aria-pressed={isPlaying}
        >
          {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
        </Button>
      </TableCell>
      <TableCell className="max-w-64 truncate font-medium" title={row.title}>
        {row.title}
      </TableCell>
      <TableCell className="max-w-48 truncate" title={row.artist}>
        {row.artist}
      </TableCell>
      <TableCell className="max-w-48 truncate" title={row.albumartist}>
        {row.albumartist || '–'}
      </TableCell>
      <TableCell className="max-w-48 truncate text-muted-foreground" title={row.album}>
        {row.album}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {row.bpm ? Math.round(row.bpm) : '–'}
      </TableCell>
      <TableCell className="text-right tabular-nums">{formatLength(row.length)}</TableCell>
      <TableCell className="text-right uppercase text-muted-foreground">
        {row.format || '–'}
      </TableCell>
      <TableCell className="text-right">
        <TitleActions slug={slug} row={row} />
      </TableCell>
    </TableRow>
  )
})

export default function LibraryTitlesPage() {
  const { library } = useOutletContext<LibraryDetailContext>()
  const slug = library.slug
  const { addTracks } = useDownloadGather()

  const [searchParams, setSearchParams] = useSearchParams()
  const initialParams = useRef(parseTitlesParams(searchParams)).current

  const [searchInput, setSearchInput] = useState(initialParams.search)
  const [bpmMinInput, setBpmMinInput] = useState(initialParams.bpmMin)
  const [bpmMaxInput, setBpmMaxInput] = useState(initialParams.bpmMax)
  const [includeHalfDouble, setIncludeHalfDouble] = useState(initialParams.includeHalfDouble)
  const [selectedArtists, setSelectedArtists] = useState<string[]>(initialParams.artists)
  const [page, setPage] = useState(initialParams.page)
  const [selectingAll, setSelectingAll] = useState(false)

  // Mirror filters + page into the URL. Replace instead of push — typing must
  // not pile up one history entry per keystroke.
  useEffect(() => {
    const next = new URLSearchParams()
    const q = searchInput.trim()
    if (q) next.set('q', q)
    if (bpmMinInput) next.set('bpmMin', bpmMinInput)
    if (bpmMaxInput) next.set('bpmMax', bpmMaxInput)
    if (includeHalfDouble) next.set('halfDouble', '1')
    for (const artist of selectedArtists) next.append('artist', artist)
    if (page > 1) next.set('page', String(page))
    setSearchParams(next, { replace: true })
  }, [searchInput, bpmMinInput, bpmMaxInput, includeHalfDouble, selectedArtists, page, setSearchParams])

  // --- Inline audio preview ---------------------------------------------
  // One shared <audio> element plays at most one track at a time; a single
  // volume slider governs it. Refs mirror the reactive state so the toggle
  // callback stays referentially stable and the memoised rows don't churn.
  const audioRef = useRef<HTMLAudioElement>(null)
  const [playingId, setPlayingId] = useState<number | null>(null)
  const [volume, setVolume] = useState<number>(readStoredVolume)
  const playingIdRef = useRef<number | null>(null)
  playingIdRef.current = playingId
  const volumeRef = useRef(volume)
  volumeRef.current = volume

  // Keep the element's volume in sync (initial mount + every change).
  useEffect(() => {
    if (audioRef.current) audioRef.current.volume = volume
  }, [volume])

  const handleVolumeChange = useCallback((value: number[]) => {
    const v = Math.min(1, Math.max(0, value[0] ?? DEFAULT_VOLUME))
    setVolume(v)
    try {
      window.localStorage.setItem(VOLUME_STORAGE_KEY, String(v))
    } catch {
      // Non-fatal — volume just won't persist across reloads.
    }
  }, [])

  const handleTogglePlay = useCallback(
    (row: TitleRow) => {
      const audio = audioRef.current
      if (!audio) return
      if (playingIdRef.current === row.id) {
        audio.pause()
        setPlayingId(null)
        return
      }
      audio.src = getTitleStreamUrl(slug, row.id)
      audio.volume = volumeRef.current
      setPlayingId(row.id)
      void audio.play().catch(() => {
        // Autoplay/decoding failure — reset only if this row is still active.
        setPlayingId((cur) => (cur === row.id ? null : cur))
      })
    },
    [slug]
  )

  const search = useDebouncedValue(searchInput.trim(), 300)
  const bpmMin = useDebouncedValue(bpmMinInput, 300)
  const bpmMax = useDebouncedValue(bpmMaxInput, 300)

  // Both bounds must be valid numbers for the BPM filter to apply.
  const filters: TitleFilters = useMemo(() => {
    const min = parseFloat(bpmMin)
    const max = parseFloat(bpmMax)
    const bpmActive = Number.isFinite(min) && Number.isFinite(max) && min <= max
    return {
      search: search || undefined,
      bpmMin: bpmActive ? min : undefined,
      bpmMax: bpmActive ? max : undefined,
      includeHalfDouble: bpmActive ? includeHalfDouble : undefined,
      albumArtists: selectedArtists.length ? selectedArtists : undefined,
    }
  }, [search, bpmMin, bpmMax, includeHalfDouble, selectedArtists])

  // Artist dropdown reflects the search + BPM result (not the selection), so
  // the list — and which artists sit at the top — stays sensible while picking.
  const artistsQuery = useTitleArtists(slug, filters)

  // New filters restart at page 1 (key change resets, state follows lazily).
  const filterKey = JSON.stringify(filters)
  const [lastFilterKey, setLastFilterKey] = useState(filterKey)
  if (filterKey !== lastFilterKey) {
    setLastFilterKey(filterKey)
    setPage(1)
  }

  const { data, isLoading, isError, error, isFetching } = useTitles(slug, filters, page, PER_PAGE)

  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE))
  const hasFilters = !!(filters.search || filters.bpmMin != null || selectedArtists.length)

  const handleSelectAll = async () => {
    setSelectingAll(true)
    try {
      const result = await fetchTitleIds(slug, filters)
      addTracks(slug, result.items)
      toast.success({
        title: `${result.total} titles marked for download`,
        description: 'Pack them from the bar at the bottom.',
      })
    } catch (err) {
      toast.error({
        title: 'Could not select all results',
        description: err instanceof Error ? err.message : 'Please try again.',
      })
    } finally {
      setSelectingAll(false)
    }
  }

  const clearFilters = () => {
    setSearchInput('')
    setBpmMinInput('')
    setBpmMaxInput('')
    setIncludeHalfDouble(false)
    setSelectedArtists([])
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold">Titles</h2>
        <p className="text-sm text-muted-foreground">
          Search and filter individual titles across the library, mark them for
          download or grab them directly.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="relative min-w-56 flex-1">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search title, artist or album…"
            className="pl-8"
            aria-label="Search titles"
          />
        </div>
        <div className="flex items-end gap-2">
          <div className="space-y-1">
            <Label htmlFor="bpm-min" className="text-xs text-muted-foreground">BPM min</Label>
            <Input
              id="bpm-min"
              type="number"
              min={1}
              max={1000}
              value={bpmMinInput}
              onChange={(e) => setBpmMinInput(e.target.value)}
              className="w-24"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="bpm-max" className="text-xs text-muted-foreground">BPM max</Label>
            <Input
              id="bpm-max"
              type="number"
              min={1}
              max={1000}
              value={bpmMaxInput}
              onChange={(e) => setBpmMaxInput(e.target.value)}
              className="w-24"
            />
          </div>
          <div className="flex h-9 items-center gap-2 pl-1">
            <Checkbox
              id="half-double"
              checked={includeHalfDouble}
              onCheckedChange={(v) => setIncludeHalfDouble(v === true)}
            />
            <Label htmlFor="half-double" className="text-xs text-muted-foreground">
              ±half/double tempo
            </Label>
          </div>
        </div>
        <ArtistFilter
          inResult={artistsQuery.data?.in_result ?? []}
          others={artistsQuery.data?.others ?? []}
          selected={selectedArtists}
          onChange={setSelectedArtists}
          isLoading={artistsQuery.isLoading}
        />
        <div className="space-y-1">
          <Label className="text-xs text-muted-foreground">Volume</Label>
          <div className="flex h-9 items-center gap-2">
            <Volume2 className="h-4 w-4 shrink-0 text-muted-foreground" />
            <Slider
              value={[volume]}
              min={0}
              max={1}
              step={0.01}
              onValueChange={handleVolumeChange}
              className="w-28"
              aria-label="Playback volume"
            />
          </div>
        </div>
        {hasFilters && (
          <Button variant="ghost" size="sm" onClick={clearFilters}>
            <X className="mr-1 h-4 w-4" /> Clear
          </Button>
        )}
      </div>

      {/* Shared inline-preview player. Hidden — driven by the per-row play
          buttons and the volume slider above; only one track at a time. */}
      <audio
        ref={audioRef}
        className="hidden"
        onEnded={() => setPlayingId(null)}
        onError={() => setPlayingId(null)}
      />

      {isError && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" />
          {error instanceof Error ? error.message : 'Could not load titles.'}
        </div>
      )}

      {isLoading && (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-10 animate-pulse rounded-md bg-muted" />
          ))}
        </div>
      )}

      {data && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-muted-foreground">
              {total} title{total === 1 ? '' : 's'}
              {hasFilters ? ' matching' : ''}
              {isFetching ? ' …' : ''}
            </p>
            {total > 0 && (
              <Button
                variant="secondary"
                size="sm"
                onClick={handleSelectAll}
                disabled={selectingAll}
              >
                {selectingAll ? (
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                ) : (
                  <ListPlus className="mr-1.5 h-4 w-4" />
                )}
                Mark all {total} for download
              </Button>
            )}
          </div>

          {total === 0 ? (
            <div className="rounded-lg border bg-muted/20 py-12 text-center">
              <Music className="mx-auto h-12 w-12 text-muted-foreground" />
              <h3 className="mt-4 text-lg font-medium">No titles found</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                {hasFilters ? 'Try a broader search, artist, or BPM range.' : 'This library has no tracks yet.'}
              </p>
            </div>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-10">
                      <span className="sr-only">Play</span>
                    </TableHead>
                    <TableHead>Title</TableHead>
                    <TableHead>Artist</TableHead>
                    <TableHead>Album Artist</TableHead>
                    <TableHead>Album</TableHead>
                    <TableHead className="text-right">BPM</TableHead>
                    <TableHead className="text-right">Length</TableHead>
                    <TableHead className="text-right">Format</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((row) => (
                    <TitleTableRow
                      key={row.id}
                      slug={slug}
                      row={row}
                      isPlaying={playingId === row.id}
                      onTogglePlay={handleTogglePlay}
                    />
                  ))}
                </TableBody>
              </Table>
            </div>
          )}

          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                <ChevronLeft className="h-4 w-4" /> Prev
              </Button>
              <span className="text-sm text-muted-foreground">
                Page {page} of {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
