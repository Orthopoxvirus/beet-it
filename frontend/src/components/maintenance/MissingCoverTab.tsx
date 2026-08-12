import { useEffect, useState, useCallback } from 'react'
import { Check, FolderX, ImageOff, Loader2, Search, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { toast } from '@/components/ui/toast'
import { CoverArtUpload } from '@/components/album/CoverArtUpload'
import { useMissingCover, useRemoveGhostAlbum } from '@/hooks/useMaintenance'
import { AlbumApiError, searchCoverArt, downloadCoverArtFromUrl } from '@/api/albums'
import type { CoverSearchResult } from '@/api/albums'
import type { MissingCoverAlbum } from '@/api/maintenance'
import { runPool } from '@/lib/concurrency'
import { cn } from '@/lib/utils'

interface MissingCoverTabProps {
  slug: string
}

// Keep the bulk "search all" gentle on the public cover sources: at most this
// many album searches run at once, the rest queue behind them. Each individual
// search already fans out (and caps) its own per-source requests server-side.
const SEARCH_CONCURRENCY = 3

type SearchPhase = 'idle' | 'searching' | 'done' | 'error'
type ApplyPhase = 'idle' | 'applying' | 'applied' | 'error'
type RemovePhase = 'idle' | 'removing' | 'removed' | 'error'

interface RowState {
  search: SearchPhase
  candidates: CoverSearchResult[]
  searchError?: string
  apply: ApplyPhase
  appliedUrl?: string
  applyError?: string
  remove: RemovePhase
}

const DEFAULT_ROW: RowState = {
  search: 'idle',
  candidates: [],
  apply: 'idle',
  remove: 'idle',
}

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback
}

// The API's raw `detail` strings expose server paths — translate the common
// failure into something a user can act on.
function applyErrorMessage(err: unknown): string {
  if (err instanceof AlbumApiError && err.status === 404) {
    return 'Album folder not found on disk — the files may have been moved or deleted.'
  }
  return errorMessage(err, 'Failed to apply cover art')
}

// The wire `source` is the image host; map the common ones to friendly names.
function friendlySource(source: string): string {
  const s = source.toLowerCase()
  if (s.includes('mzstatic') || s.includes('apple')) return 'iTunes'
  if (s.includes('dzcdn') || s.includes('deezer')) return 'Deezer'
  if (s.includes('archive.org') || s.includes('coverartarchive'))
    return 'Cover Art Archive'
  return source
}

function resolutionLabel(c: CoverSearchResult): string {
  return c.width && c.height ? `${c.width}×${c.height}` : 'unknown size'
}

export default function MissingCoverTab({ slug }: MissingCoverTabProps) {
  const { data, isLoading, isError, error } = useMissingCover(slug)

  // Snapshot the album list once so applied rows can stay in place (greyed)
  // instead of vanishing on a refetch and shifting every row below them.
  const [rows, setRows] = useState<MissingCoverAlbum[] | null>(null)
  useEffect(() => {
    if (data && rows === null) {
      setRows(data.items)
    }
  }, [data, rows])

  const [rowStates, setRowStates] = useState<Record<number, RowState>>({})
  const [bulkRunning, setBulkRunning] = useState(false)
  const [progress, setProgress] = useState({ done: 0, total: 0 })
  const [coverAlbumId, setCoverAlbumId] = useState<number | null>(null)

  const patchRow = useCallback((albumId: number, partial: Partial<RowState>) => {
    setRowStates((prev) => ({
      ...prev,
      [albumId]: { ...DEFAULT_ROW, ...prev[albumId], ...partial },
    }))
  }, [])

  const searchOne = useCallback(
    async (albumId: number) => {
      patchRow(albumId, { search: 'searching', searchError: undefined })
      try {
        const res = await searchCoverArt(slug, albumId)
        patchRow(albumId, { search: 'done', candidates: res.results })
      } catch (err) {
        patchRow(albumId, {
          search: 'error',
          searchError: errorMessage(err, 'Search failed'),
        })
      }
    },
    [slug, patchRow]
  )

  const handleSearchAll = useCallback(async () => {
    if (!rows) return
    // (Re)search albums that haven't resolved yet; skip applied ones and ones
    // already searched/in-flight so a second click only retries what's left.
    const targets = rows.filter((album) => {
      if (album.folder_missing) return false
      const s = rowStates[album.album_id]
      if (s?.apply === 'applied') return false
      if (s?.search === 'done' || s?.search === 'searching') return false
      return true
    })
    if (targets.length === 0) return

    setBulkRunning(true)
    setProgress({ done: 0, total: targets.length })
    await runPool(targets, SEARCH_CONCURRENCY, async (album) => {
      await searchOne(album.album_id)
      setProgress((p) => ({ ...p, done: p.done + 1 }))
    })
    setBulkRunning(false)
  }, [rows, rowStates, searchOne])

  const applyCandidate = useCallback(
    async (albumId: number, url: string) => {
      patchRow(albumId, {
        apply: 'applying',
        appliedUrl: url,
        applyError: undefined,
      })
      try {
        await downloadCoverArtFromUrl(slug, albumId, url)
        patchRow(albumId, { apply: 'applied', appliedUrl: url })
      } catch (err) {
        const friendly = applyErrorMessage(err)
        toast.error({
          title: 'Could not apply cover art',
          description: friendly,
        })
        patchRow(albumId, { apply: 'error', applyError: friendly })
      }
    },
    [slug, patchRow]
  )

  const removeGhost = useRemoveGhostAlbum(slug)
  const { mutateAsync: removeGhostAsync } = removeGhost
  const handleRemove = useCallback(
    async (albumId: number) => {
      patchRow(albumId, { remove: 'removing' })
      try {
        await removeGhostAsync(albumId)
        patchRow(albumId, { remove: 'removed' })
      } catch (err) {
        toast.error({
          title: 'Could not remove album',
          description: errorMessage(err, 'Failed to remove album'),
        })
        patchRow(albumId, { remove: 'error' })
      }
    },
    [removeGhostAsync, patchRow]
  )

  if (isLoading && rows === null) {
    return <p className="text-sm text-muted-foreground">Scanning library…</p>
  }
  if (isError && rows === null) {
    return (
      <p className="text-sm text-destructive">
        {error instanceof Error ? error.message : 'Failed to load'}
      </p>
    )
  }
  if (!rows || rows.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">Every album has cover art.</p>
    )
  }

  const resolvedCount = rows.filter(
    (a) => rowStates[a.album_id]?.apply === 'applied'
  ).length
  const ghostCount = rows.filter((a) => a.folder_missing).length

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {rows.length} album{rows.length === 1 ? '' : 's'} without cover art
          {ghostCount > 0 && ` · ${ghostCount} with files missing on disk`}
          {resolvedCount > 0 && ` · ${resolvedCount} resolved this session`}.
        </p>
        <Button size="sm" onClick={handleSearchAll} disabled={bulkRunning}>
          {bulkRunning ? (
            <>
              <Loader2 className="h-4 w-4 mr-1 animate-spin" />
              Searching… {progress.done}/{progress.total}
            </>
          ) : (
            <>
              <Search className="h-4 w-4 mr-1" />
              Search all online
            </>
          )}
        </Button>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[280px]">Artist / Album</TableHead>
            <TableHead>Cover art candidates</TableHead>
            <TableHead className="w-[180px]" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((album) => {
            const state = rowStates[album.album_id] ?? DEFAULT_ROW
            const isApplied = state.apply === 'applied'
            const isRemoved = state.remove === 'removed'
            return (
              <TableRow
                key={album.album_id}
                className={cn((isApplied || isRemoved) && 'opacity-50')}
              >
                <TableCell className="align-top">
                  <div className="font-medium">{album.artist || '—'}</div>
                  <div className="text-sm text-muted-foreground">
                    {album.title || '—'}
                  </div>
                </TableCell>

                {album.folder_missing ? (
                  // Ghost entry: the folder is gone from disk, so cover
                  // search/upload can only 404 — offer a DB-only removal.
                  <>
                    <TableCell className="align-top">
                      <span className="inline-flex items-center gap-1 text-sm text-muted-foreground">
                        <FolderX className="h-4 w-4" />
                        {isRemoved
                          ? 'Removed from library'
                          : 'Files missing on disk — cover search unavailable'}
                      </span>
                    </TableCell>
                    <TableCell className="text-right align-top">
                      {!isRemoved && (
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={state.remove === 'removing'}
                          onClick={() => handleRemove(album.album_id)}
                        >
                          {state.remove === 'removing' ? (
                            <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                          ) : (
                            <Trash2 className="h-4 w-4 mr-1" />
                          )}
                          Remove from library
                        </Button>
                      )}
                    </TableCell>
                  </>
                ) : (
                  <>
                    <TableCell className="align-top">
                      <CandidateCell
                        state={state}
                        onSearch={() => searchOne(album.album_id)}
                        onApply={(url) => applyCandidate(album.album_id, url)}
                      />
                    </TableCell>

                    <TableCell className="text-right align-top">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setCoverAlbumId(album.album_id)}
                      >
                        <ImageOff className="h-4 w-4 mr-1" />
                        Change cover art
                      </Button>
                    </TableCell>
                  </>
                )}
              </TableRow>
            )
          })}
        </TableBody>
      </Table>

      {coverAlbumId !== null && (
        <CoverArtUpload
          slug={slug}
          albumId={coverAlbumId}
          isOpen={coverAlbumId !== null}
          defaultMode="search"
          onClose={() => setCoverAlbumId(null)}
          // Mark resolved in place rather than refetching, so the row greys out
          // without the list reshuffling under the user.
          onSuccess={() => patchRow(coverAlbumId, { apply: 'applied' })}
        />
      )}
    </div>
  )
}

interface CandidateCellProps {
  state: RowState
  onSearch: () => void
  onApply: (url: string) => void
}

function CandidateCell({ state, onSearch, onApply }: CandidateCellProps) {
  if (state.apply === 'applied') {
    return (
      <span className="inline-flex items-center gap-1 text-sm text-muted-foreground">
        <Check className="h-4 w-4 text-primary" />
        Cover applied
      </span>
    )
  }

  if (state.search === 'searching') {
    return (
      <span className="inline-flex items-center gap-1 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Searching…
      </span>
    )
  }

  if (state.search === 'error') {
    return (
      <div className="space-y-1">
        <p className="text-sm text-destructive">
          {state.searchError ?? 'Search failed'}
        </p>
        <Button variant="ghost" size="sm" onClick={onSearch}>
          Retry
        </Button>
      </div>
    )
  }

  if (state.search === 'done' && state.candidates.length === 0) {
    return (
      <div className="space-y-1">
        <p className="text-sm text-muted-foreground">No matches found.</p>
        <Button variant="ghost" size="sm" onClick={onSearch}>
          Search again
        </Button>
      </div>
    )
  }

  if (state.search === 'done') {
    const applying = state.apply === 'applying'
    return (
      <div className="space-y-1">
        <div className="flex gap-2 overflow-x-auto py-1">
          {state.candidates.map((c) => {
            const chosen = applying && state.appliedUrl === c.url
            return (
              <button
                key={c.url}
                type="button"
                disabled={applying}
                onClick={() => onApply(c.url)}
                aria-label={`Use this ${friendlySource(c.source)} cover (${resolutionLabel(c)})`}
                title={`${resolutionLabel(c)} · ${friendlySource(c.source)}`}
                className="group relative w-24 shrink-0 rounded-md overflow-hidden border hover:border-primary focus:border-primary focus:outline-none disabled:opacity-60"
              >
                <img
                  src={c.url}
                  alt="Cover art candidate"
                  loading="lazy"
                  className="w-full aspect-square object-cover"
                />
                {chosen && (
                  <span className="absolute inset-0 flex items-center justify-center bg-black/40">
                    <Loader2 className="h-5 w-5 animate-spin text-white" />
                  </span>
                )}
                <span className="block px-1 py-0.5 text-[10px] leading-tight text-muted-foreground truncate text-left">
                  {resolutionLabel(c)} · {friendlySource(c.source)}
                </span>
              </button>
            )
          })}
        </div>
        {state.apply === 'error' && (
          <p className="text-sm text-destructive">
            {state.applyError ?? 'Failed to apply cover art'}
          </p>
        )}
      </div>
    )
  }

  // Idle: offer a per-row search as well as the bulk button up top.
  return (
    <Button variant="ghost" size="sm" onClick={onSearch}>
      <Search className="h-4 w-4 mr-1" />
      Search
    </Button>
  )
}
