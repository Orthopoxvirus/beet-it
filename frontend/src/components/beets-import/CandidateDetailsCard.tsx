import { useState, useMemo, useEffect, useRef } from 'react'
import {
  ChevronDown,
  ChevronRight,
  Music,
  Folder,
  Loader2,
  AlertCircle,
  Search,
  ArrowRight,
  Plus,
  Download,
  Check,
  RefreshCw,
  AudioLines,
  Trash2,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { cn } from '@/lib/utils'
import type {
  AnalyzeAlbumResponse,
  Candidate,
  CandidateTrack,
  ConvertAudioParams,
  ConvertSource,
  ConvertTarget,
  LocalTrackInfo,
  MetadataChange,
  MetadataSource,
} from '@/types/beets-import'
import ManualCandidateDialog from './ManualCandidateDialog'

// ============================================================================
// Types
// ============================================================================

interface CandidateDetailsCardProps {
  /** Analysis results to display */
  analysisData: AnalyzeAlbumResponse | null
  /** Whether analysis is in progress */
  isAnalyzing?: boolean
  /** Error message if analysis failed */
  error?: string | null
  /** Optional additional CSS class */
  className?: string
  /** Library slug — required for the manual-candidate search dialog */
  librarySlug: string
  /** Callback when adding a manual candidate link */
  onAddManualCandidate?: (link: string) => void
  /** Callback to re-run the beets analysis for the selected album */
  onReanalyze?: () => void
  /** Convert the local album's WAV/WMA files to FLAC or MP3 (with optional original deletion) */
  onConvertAudio?: (params: ConvertAudioParams) => void
  /** Remove the local album's duplicate WAV files (those with a FLAC twin) */
  onRemoveDuplicateWavs?: () => void
  /** Whether a WAV convert / dedup op is currently running */
  isAudioOpRunning?: boolean
  /** Error message from the last WAV convert / dedup op, if any */
  audioOpError?: string | null
  /** Whether manual candidate resolution is in progress */
  isAddingManualCandidate?: boolean
  /** Error message from manual candidate resolution failure */
  manualCandidateError?: string | null
  /** Callback when Import button is clicked on a candidate */
  onImportClick?: (candidate: Candidate) => void
  /** Whether an import is currently being initiated */
  isImporting?: boolean
  /** Index of the chosen candidate (for highlighting) */
  chosenCandidateIndex?: number | null
  /** Whether the album is currently being imported (job in progress) */
  isImportInProgress?: boolean
}

interface LocalAlbumInfoProps {
  path: string
  artist: string | null
  album: string | null
  trackCount: number
  /** Where artist/album came from; drives the "from folder name" label. */
  metadataSource?: MetadataSource
  /** Dominant container format of the album (e.g. "FLAC", "MP3"); null if unknown. */
  dominantFormat?: string | null
  /** Whether the album folder contains any .wav files. */
  hasWav?: boolean
  /** Count of .wav files that have a same-basename .flac sibling (real duplicates). */
  duplicateWavCount?: number
  /** Whether the album folder contains any .wma files. */
  hasWma?: boolean
  /** Smart-default convert target for the album's WMA files; null if no WMA. */
  wmaRecommendedTarget?: ConvertTarget | null
  /** Convert the album's WAV/WMA files to FLAC or MP3, optionally deleting originals. */
  onConvertAudio?: (params: ConvertAudioParams) => void
  /** Remove the album's duplicate WAVs. */
  onRemoveDuplicateWavs?: () => void
  /** Whether a WAV convert / dedup op is currently running. */
  isAudioOpRunning?: boolean
  /** Error message from the last WAV op, if any. */
  audioOpError?: string | null
}

interface CandidateCardProps {
  candidate: Candidate
  index: number
  isExpanded: boolean
  onToggle: () => void
  /** Full local track list for detecting track count mismatches */
  localTracks?: LocalTrackInfo[]
  /** Callback when Import button is clicked */
  onImportClick?: () => void
  /** Whether the import button should show loading state */
  isImporting?: boolean
  /** Whether this candidate is the chosen one (for highlighting) */
  isChosen?: boolean
  /** Whether the album has an import job in progress */
  isImportInProgress?: boolean
}

interface TrackComparisonTableProps {
  /** Full candidate track list — each is joined to its paired local track for display */
  candidateTracks?: CandidateTrack[]
  /** Full local track list — used to surface local tracks with no candidate counterpart */
  localTracks?: LocalTrackInfo[]
}

interface MetadataChangeListProps {
  changes: MetadataChange[]
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Format similarity score as percentage
 */
function formatSimilarity(similarity: number): string {
  return `${(similarity * 100).toFixed(1)}%`
}

/**
 * Format a duration in seconds as m:ss (e.g. 238 -> "3:58"). Returns null when
 * the length is unavailable, so callers can decide what to render.
 */
function formatTrackLength(seconds: number | null | undefined): string | null {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) {
    return null
  }
  const total = Math.round(seconds)
  const mins = Math.floor(total / 60)
  const secs = total % 60
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

/**
 * Durations whose raw difference is within this many seconds are rendered as a
 * single value: provider metadata and file duration routinely disagree by ~1 s,
 * and rounding each side to the nearest second can turn a sub-second gap into
 * a misleading "7:41 vs 7:42".
 */
const LENGTH_MATCH_TOLERANCE_SECONDS = 1

/**
 * Render the local vs. candidate duration the way the console import does:
 * "3:58 vs 4:01" when both are known and genuinely differ, a single value when
 * they match (within tolerance on the raw lengths) or only one side is known,
 * and a dash when neither is available.
 */
function formatLengthComparison(
  localLength: number | null | undefined,
  candidateLength: number | null | undefined
): string {
  const local = formatTrackLength(localLength)
  const candidate = formatTrackLength(candidateLength)
  if (local && candidate) {
    // local/candidate being non-null implies the raw lengths are finite numbers.
    const effectivelyEqual =
      Math.abs((localLength as number) - (candidateLength as number)) <=
      LENGTH_MATCH_TOLERANCE_SECONDS
    return effectivelyEqual ? local : `${local} vs ${candidate}`
  }
  return local ?? candidate ?? '—'
}

/**
 * Extract the filename from an absolute path (handles both / and \ separators).
 */
function basename(path: string | null | undefined): string | null {
  if (!path) return null
  const parts = path.split(/[/\\]/)
  return parts[parts.length - 1] || null
}

/**
 * Get badge variant based on similarity score
 */
function getSimilarityVariant(
  similarity: number
): 'default' | 'secondary' | 'destructive' {
  if (similarity >= 0.95) return 'default' // Green-ish (primary)
  if (similarity >= 0.85) return 'secondary' // Neutral
  return 'destructive' // Red for low matches
}

/**
 * Merge manual candidates with automatic candidates.
 * Manual candidates appear first in the list.
 */
function mergeAndSortCandidates(
  automaticCandidates: Candidate[],
  manualCandidates?: Candidate[]
): Candidate[] {
  const manual = manualCandidates ?? []
  // Manual candidates first, then automatic candidates
  return [...manual, ...automaticCandidates]
}

// ============================================================================
// Subcomponents
// ============================================================================

export function LocalAlbumInfo({
  path,
  artist,
  album,
  trackCount,
  metadataSource = 'tags',
  dominantFormat,
  hasWav = false,
  duplicateWavCount = 0,
  hasWma = false,
  wmaRecommendedTarget = null,
  onConvertAudio,
  onRemoveDuplicateWavs,
  isAudioOpRunning = false,
  audioOpError = null,
}: LocalAlbumInfoProps) {
  // Which confirmation dialog is open, plus the convert dialog's state: which
  // source the user is converting, the chosen target, and the delete checkbox.
  const [dialog, setDialog] = useState<'convert' | 'dedupe' | null>(null)
  const [convertSource, setConvertSource] = useState<ConvertSource>('wav')
  const [targetFormat, setTargetFormat] = useState<ConvertTarget>('flac')
  const [deleteOriginals, setDeleteOriginals] = useState(false)

  const showConvertWav = hasWav && !!onConvertAudio
  const showConvertWma = hasWma && !!onConvertAudio
  const showDedupe = duplicateWavCount > 0 && !!onRemoveDuplicateWavs
  const showActions = showConvertWav || showConvertWma || showDedupe

  const openConvert = (source: ConvertSource) => {
    setConvertSource(source)
    // Smart preselect: WAV is lossless → FLAC; WMA follows the backend's
    // bitrate-based recommendation (MP3 ≤320 kbit, FLAC above), defaulting to
    // MP3 when no recommendation is available.
    setTargetFormat(source === 'wma' ? wmaRecommendedTarget ?? 'mp3' : 'flac')
    setDeleteOriginals(false)
    setDialog('convert')
  }

  const confirmConvert = () => {
    onConvertAudio?.({ sourceFormat: convertSource, targetFormat, deleteOriginals })
    setDialog(null)
  }

  const confirmDedupe = () => {
    onRemoveDuplicateWavs?.()
    setDialog(null)
  }

  const sourceLabel = convertSource.toUpperCase()

  return (
    <div className="p-4 rounded-lg bg-muted/50 border">
      <div className="flex items-start gap-3">
        <Folder className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h4 className="font-medium text-sm">Local Album</h4>
            {metadataSource !== 'tags' && (
              <Badge variant="outline" className="text-xs font-normal">
                {metadataSource === 'folder'
                  ? 'from folder name'
                  : 'from tags + folder name'}
              </Badge>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-1 font-mono break-all">
            {path}
          </p>
          <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <div className="min-w-0">
              <span className="text-muted-foreground">Artist:</span>
              <p className="font-medium break-words">{artist || '(unknown)'}</p>
            </div>
            <div className="min-w-0">
              <span className="text-muted-foreground">Album:</span>
              <p className="font-medium break-words">{album || '(unknown)'}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Tracks:</span>
              <p className="font-medium">{trackCount}</p>
            </div>
            <div className="min-w-0">
              <span className="text-muted-foreground">Format:</span>
              <p className="font-medium">
                {dominantFormat ? (
                  <Badge variant="secondary">{dominantFormat}</Badge>
                ) : (
                  '(unknown)'
                )}
              </p>
            </div>
          </div>

          {/* WAV / WMA handling actions */}
          {showActions && (
            <div className="mt-3 pt-3 border-t flex flex-wrap items-center gap-2">
              {showConvertWav && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => openConvert('wav')}
                  disabled={isAudioOpRunning}
                  data-testid="convert-wav-button"
                >
                  {isAudioOpRunning ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <AudioLines className="mr-2 h-4 w-4" />
                  )}
                  Convert WAV
                </Button>
              )}
              {showConvertWma && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => openConvert('wma')}
                  disabled={isAudioOpRunning}
                  data-testid="convert-wma-button"
                >
                  {isAudioOpRunning ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <AudioLines className="mr-2 h-4 w-4" />
                  )}
                  Convert WMA
                </Button>
              )}
              {showDedupe && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setDialog('dedupe')}
                  disabled={isAudioOpRunning}
                  data-testid="dedupe-wav-button"
                >
                  {isAudioOpRunning ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Trash2 className="mr-2 h-4 w-4" />
                  )}
                  Remove duplicate WAVs ({duplicateWavCount})
                </Button>
              )}
            </div>
          )}

          {audioOpError && (
            <p
              className="mt-2 text-xs text-destructive break-words"
              data-testid="audio-op-error"
            >
              {audioOpError}
            </p>
          )}
        </div>
      </div>

      {/* Convert confirmation */}
      <AlertDialog
        open={dialog === 'convert'}
        onOpenChange={(open) => !open && setDialog(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Convert {sourceLabel} files?</AlertDialogTitle>
            <AlertDialogDescription>
              Every <code>.{convertSource}</code> in this album will be
              transcoded to the format you pick below. An existing file of the
              same name is never overwritten.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm text-muted-foreground">Target format</span>
              <Select
                value={targetFormat}
                onValueChange={(v) => setTargetFormat(v as ConvertTarget)}
              >
                <SelectTrigger
                  className="w-44"
                  data-testid="convert-target-select"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="flac">FLAC (lossless)</SelectItem>
                  <SelectItem value="mp3">MP3 (V0)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <Checkbox
                checked={deleteOriginals}
                onCheckedChange={setDeleteOriginals}
                data-testid="delete-originals-checkbox"
              />
              Delete original {sourceLabel} files after conversion
            </label>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmConvert}>
              Convert
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Dedupe confirmation */}
      <AlertDialog
        open={dialog === 'dedupe'}
        onOpenChange={(open) => !open && setDialog(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove duplicate WAV files?</AlertDialogTitle>
            <AlertDialogDescription>
              {duplicateWavCount} WAV file{duplicateWavCount !== 1 ? 's' : ''} that
              already {duplicateWavCount !== 1 ? 'have' : 'has'} a matching FLAC
              will be deleted. WAVs without a FLAC twin are never touched.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDedupe}>
              Remove {duplicateWavCount} WAV{duplicateWavCount !== 1 ? 's' : ''}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function MetadataChangeList({ changes }: MetadataChangeListProps) {
  if (changes.length === 0) {
    return null
  }

  return (
    <div className="space-y-1.5">
      {changes.map((change, idx) => (
        <div key={`${change.field}-${idx}`} className="flex items-start gap-2 text-sm">
          <span className="text-muted-foreground capitalize min-w-[60px] flex-shrink-0 pt-0.5">
            {change.field}:
          </span>
          <span className="text-destructive/70 line-through break-words min-w-0 flex-1">
            {change.fromValue || '(empty)'}
          </span>
          <ArrowRight className="h-3 w-3 text-muted-foreground flex-shrink-0 mt-1" />
          <span className="text-green-600 dark:text-green-400 break-words min-w-0 flex-1">
            {change.toValue || '(empty)'}
          </span>
        </div>
      ))}
    </div>
  )
}

type TrackRowState = 'changed' | 'unchanged' | 'new'

interface ComparedTrackRow {
  /** Per-disc track number from the candidate (what the import writes to tags). */
  index: number
  /** Continuous playback position 1..N across discs — drives display order and the # column. */
  position: number
  disc: number | null
  localTitle: string | null
  candidateTitle: string
  state: TrackRowState
  localLength: number | null
  candidateLength: number | null
  localPath: string | null
}

interface LocalOnlyRow {
  trackNum: number | null
  title: string | null
  length: number | null
  path: string | null
}

/**
 * Join candidate tracks with their local counterparts for display.
 *
 * The backend pairs each candidate track with its local file
 * (localTitle/localPath), so every candidate track renders a row showing the
 * actual local value — matched tracks included — instead of collapsing to
 * "(new)" with an empty Local column. For results cached before that change
 * (no localTitle/localPath present), we fall back to pairing by track number
 * so nothing regresses.
 */
export function buildTrackComparison(
  candidateTracks?: CandidateTrack[],
  localTracks?: LocalTrackInfo[]
): { rows: ComparedTrackRow[]; localOnly: LocalOnlyRow[]; unmatchedCount: number } {
  const candidates = candidateTracks ?? []
  const locals = localTracks ?? []

  const localByNum = new Map<number, LocalTrackInfo>()
  const localByPath = new Map<string, LocalTrackInfo>()
  for (const t of locals) {
    if (t.trackNum != null) localByNum.set(t.trackNum, t)
    if (t.path) localByPath.set(t.path, t)
  }

  let rows: ComparedTrackRow[] = candidates
    .map((t) => {
      const hasExplicitPairing = t.localTitle !== undefined || t.localPath !== undefined
      let localTitle: string | null
      let localPath: string | null
      let paired: boolean
      // The paired local track, when we can resolve it, gives us the local
      // duration to display next to the candidate's.
      let pairedLocal: LocalTrackInfo | undefined
      if (hasExplicitPairing) {
        localTitle = t.localTitle ?? null
        localPath = t.localPath ?? null
        paired = (t.localTitle ?? null) !== null || (t.localPath ?? null) !== null
        pairedLocal = localPath ? localByPath.get(localPath) : undefined
      } else {
        // Backward-compat with results cached before explicit pairing existed.
        const lt = localByNum.get(t.index)
        localTitle = lt?.title ?? null
        localPath = lt?.path ?? null
        paired = !!lt
        pairedLocal = lt
      }
      const state: TrackRowState = !paired
        ? 'new'
        : localTitle === t.title
          ? 'unchanged'
          : 'changed'
      return {
        index: t.index,
        position: 0, // stamped after sorting
        disc: t.disc ?? null,
        localTitle,
        candidateTitle: t.title,
        state,
        localLength: pairedLocal?.length ?? null,
        candidateLength: t.length ?? null,
        localPath,
      }
    })
    // Playback order, not bare index: on a multi-disc release the per-disc
    // index restarts at 1 each CD, so sorting by it alone groups all the
    // disc-first tracks together (issue #184).
    .sort((a, b) => (a.disc ?? 1) - (b.disc ?? 1) || a.index - b.index)
    .map((r, i) => ({ ...r, position: i + 1 }))

  // Degenerate case: neither explicit nor track-number pairing matched a single
  // track, yet there are equal numbers of candidate and local tracks. This is
  // what tag-less files (no tracknumber) plus a legacy cached result, or a local
  // path that failed to resolve, look like — and it wrongly reports 2xN
  // unmatched rows. If the per-position durations line up, the two sides are
  // clearly the same album, so pair them by sorted order. The length check keeps
  // a genuinely different (all-new) album from being force-paired.
  const LENGTH_TOLERANCE_S = 2
  const lengthsAgree = (a: number | null, b: number | null) =>
    a == null || b == null || Math.abs(a - b) <= LENGTH_TOLERANCE_S
  const nothingPaired = rows.length > 0 && rows.every((r) => r.state === 'new')
  const countsMatch = candidates.length === locals.length && locals.length > 0
  const pairByPosition =
    nothingPaired &&
    countsMatch &&
    rows.every((r, i) => lengthsAgree(r.candidateLength, locals[i].length ?? null))

  if (pairByPosition) {
    rows = rows.map((r, i) => {
      const lt = locals[i]
      const localTitle = lt.title ?? null
      return {
        ...r,
        localTitle,
        localLength: lt.length ?? null,
        localPath: lt.path ?? null,
        state: localTitle === r.candidateTitle ? 'unchanged' : 'changed',
      }
    })
  }

  // Local files with no candidate counterpart at all. When we paired by
  // position every local track is consumed, so there are none left over.
  const pairedPaths = new Set(
    candidates.map((t) => t.localPath).filter((p): p is string => !!p)
  )
  const pairedNums = new Set(
    candidates
      .filter((t) => t.localTitle === undefined && t.localPath === undefined)
      .map((t) => t.index)
  )
  const localOnly: LocalOnlyRow[] = pairByPosition
    ? []
    : locals
        .filter(
          (t) =>
            !pairedPaths.has(t.path) &&
            !(t.trackNum != null && pairedNums.has(t.trackNum))
        )
        .map((t) => ({
          trackNum: t.trackNum,
          title: t.title,
          length: t.length ?? null,
          path: t.path ?? null,
        }))

  const unmatchedCount =
    rows.filter((r) => r.state === 'new').length + localOnly.length

  return { rows, localOnly, unmatchedCount }
}

function TrackComparisonTable({ candidateTracks, localTracks }: TrackComparisonTableProps) {
  const { rows, localOnly } = useMemo(
    () => buildTrackComparison(candidateTracks, localTracks),
    [candidateTracks, localTracks]
  )

  if (rows.length === 0 && localOnly.length === 0) {
    return (
      <p className="text-sm text-muted-foreground italic">
        No tracks to compare
      </p>
    )
  }

  return (
    <div className="border rounded-md overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-muted/50">
          <tr>
            <th className="px-3 py-2 text-left font-medium text-muted-foreground w-10">
              #
            </th>
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">
              Local
            </th>
            <th className="px-3 py-2 text-center w-8">
              <ArrowRight className="h-3 w-3 mx-auto text-muted-foreground" />
            </th>
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">
              Candidate
            </th>
            <th className="px-3 py-2 text-right font-medium text-muted-foreground whitespace-nowrap">
              Length
            </th>
          </tr>
        </thead>
        <tbody>
          {/* One row per candidate track, showing the paired local title. */}
          {rows.map((r) => (
            <tr
              key={`track-${r.position}`}
              className={cn('border-t align-top', r.state === 'new' && 'bg-green-500/5')}
            >
              <td className="px-3 py-2 text-muted-foreground">{r.position}</td>
              {r.state === 'new' ? (
                <td className="px-3 py-2 text-muted-foreground italic">—</td>
              ) : (
                <td
                  className={cn(
                    'px-3 py-2 break-words',
                    r.state === 'changed'
                      ? 'text-destructive/70 line-through'
                      : 'text-muted-foreground'
                  )}
                >
                  {r.localTitle || '(empty)'}
                  {basename(r.localPath) && (
                    <span className="block text-[10px] text-muted-foreground font-mono break-all no-underline">
                      {basename(r.localPath)}
                    </span>
                  )}
                </td>
              )}
              <td className="px-3 py-2 text-center">
                <ArrowRight className="h-3 w-3 mx-auto text-muted-foreground mt-1" />
              </td>
              <td
                className={cn(
                  'px-3 py-2 break-words',
                  r.state === 'unchanged'
                    ? 'text-foreground'
                    : 'text-green-600 dark:text-green-400'
                )}
              >
                {r.candidateTitle || '(empty)'}
                {r.state === 'new' && (
                  <span className="ml-1.5 text-[10px] text-green-600/60 dark:text-green-400/60 font-normal">
                    (new)
                  </span>
                )}
              </td>
              <td className="px-3 py-2 text-right text-muted-foreground whitespace-nowrap tabular-nums">
                {formatLengthComparison(r.localLength, r.candidateLength)}
              </td>
            </tr>
          ))}
          {/* Local-only tracks: exist in local but not in candidate */}
          {localOnly.map((t, i) => (
            <tr
              key={`local-only-${t.trackNum ?? `x${i}`}`}
              className="border-t bg-amber-500/5 align-top"
            >
              <td className="px-3 py-2 text-muted-foreground">{t.trackNum ?? '—'}</td>
              <td className="px-3 py-2 text-amber-600 dark:text-amber-400 break-words">
                {t.title || '(empty)'}
                <span className="ml-1.5 text-[10px] text-amber-600/60 dark:text-amber-400/60 font-normal">(no match)</span>
                {basename(t.path) && (
                  <span className="block text-[10px] text-muted-foreground font-mono break-all">
                    {basename(t.path)}
                  </span>
                )}
              </td>
              <td className="px-3 py-2 text-center">
                <ArrowRight className="h-3 w-3 mx-auto text-muted-foreground mt-1" />
              </td>
              <td className="px-3 py-2 text-muted-foreground italic">—</td>
              <td className="px-3 py-2 text-right text-muted-foreground whitespace-nowrap tabular-nums">
                {formatTrackLength(t.length) ?? '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function CandidateCard({
  candidate,
  index,
  isExpanded,
  onToggle,
  localTracks,
  onImportClick,
  isImporting = false,
  isChosen = false,
  isImportInProgress = false,
}: CandidateCardProps) {
  const hasAlbumChanges = candidate.changes.length > 0
  const isManual = candidate.isManual === true

  // Derive both the renamed-track count and unmatched count from the same join
  // the comparison table renders from. trackChanges now carries a row per
  // matched track (for durations/filenames), so it can't be used as a
  // "how many titles changed" signal — count 'changed' rows instead.
  const { titleChangeCount, unmatchedCount } = useMemo(() => {
    const { rows, unmatchedCount } = buildTrackComparison(
      candidate.tracks,
      localTracks
    )
    return {
      titleChangeCount: rows.filter((r) => r.state === 'changed').length,
      unmatchedCount,
    }
  }, [candidate.tracks, localTracks])
  const hasTrackChanges = titleChangeCount > 0

  // Import button is disabled if currently importing or if this album already has an import in progress
  const importDisabled = isImporting || isImportInProgress

  const handleImportClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (onImportClick && !importDisabled) {
      onImportClick()
    }
  }

  return (
    <div
      className={cn(
        'border rounded-lg overflow-hidden transition-colors',
        isChosen && 'border-blue-500 bg-blue-500/5 ring-1 ring-blue-500/20'
      )}
      data-testid="candidate-card"
    >
      {/* Header - always visible */}
      <button
        type="button"
        className="w-full flex flex-wrap items-center gap-2 sm:gap-3 p-3 hover:bg-muted/50 transition-colors text-left"
        onClick={onToggle}
        aria-expanded={isExpanded}
      >
        {/* Expand/collapse chevron */}
        {isExpanded ? (
          <ChevronDown className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
        )}

        {/* Rank badge */}
        <div className="flex-shrink-0 w-6 h-6 rounded-full bg-muted flex items-center justify-center text-xs font-medium">
          {index + 1}
        </div>

        {/* Chosen indicator badge */}
        {isChosen && (
          <Badge
            variant="default"
            className="flex-shrink-0 bg-blue-600 hover:bg-blue-600"
          >
            <Check className="h-3 w-3 mr-1" />
            Chosen
          </Badge>
        )}

        {/* Manual indicator badge */}
        {isManual && !isChosen && (
          <Badge
            variant="default"
            className="flex-shrink-0 bg-purple-600 hover:bg-purple-600"
          >
            Manual
          </Badge>
        )}

        {/* Similarity score */}
        <Badge
          variant={getSimilarityVariant(candidate.similarity)}
          className="flex-shrink-0"
        >
          {formatSimilarity(candidate.similarity)}
        </Badge>

        {/* Source label */}
        <Badge variant="outline" className="flex-shrink-0">
          {candidate.source}
        </Badge>

        {/* Artist - Album */}
        <div className="basis-full order-last sm:order-none sm:basis-0 sm:flex-1 min-w-0">
          <span className="font-medium break-words block">
            {candidate.artist} - {candidate.album}
          </span>
          {candidate.year && (
            <span className="text-xs text-muted-foreground break-words">
              {candidate.year}
              {candidate.label && ` - ${candidate.label}`}
              {candidate.country && ` (${candidate.country})`}
            </span>
          )}
        </div>

        {/* Change indicators */}
        {(hasAlbumChanges || hasTrackChanges || unmatchedCount > 0) && (
          <div className="flex items-center gap-1 text-xs text-muted-foreground flex-shrink-0">
            {hasAlbumChanges && (
              <span className="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-700 dark:text-amber-300">
                {candidate.changes.length} field{candidate.changes.length !== 1 ? 's' : ''}
              </span>
            )}
            {hasTrackChanges && (
              <span className="px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-700 dark:text-blue-300">
                {titleChangeCount} track{titleChangeCount !== 1 ? 's' : ''}
              </span>
            )}
            {unmatchedCount > 0 && (
              <span className="px-1.5 py-0.5 rounded bg-red-500/20 text-red-700 dark:text-red-300">
                {unmatchedCount} unmatched
              </span>
            )}
          </div>
        )}
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div className="border-t p-4 space-y-4 bg-muted/20">
          {/* Album-level changes */}
          {hasAlbumChanges && (
            <div>
              <h5 className="text-sm font-medium mb-2">Album Changes</h5>
              <MetadataChangeList changes={candidate.changes} />
            </div>
          )}

          {/* Track changes */}
          <div>
            <h5 className="text-sm font-medium mb-2">Track Changes</h5>
            <TrackComparisonTable
              candidateTracks={candidate.tracks}
              localTracks={localTracks}
            />
          </div>

          {/* Additional metadata */}
          {(candidate.media || candidate.label) && (
            <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
              {candidate.media && (
                <span className="px-2 py-1 rounded bg-muted">
                  Media: {candidate.media}
                </span>
              )}
              {candidate.label && (
                <span className="px-2 py-1 rounded bg-muted">
                  Label: {candidate.label}
                </span>
              )}
              {candidate.sourceId && (
                <span className="px-2 py-1 rounded bg-muted font-mono text-[10px]">
                  ID: {candidate.sourceId}
                </span>
              )}
            </div>
          )}

          {/* Import button */}
          {onImportClick && (
            <div className="pt-2 border-t">
              <Button
                onClick={handleImportClick}
                disabled={importDisabled}
                size="sm"
                className="w-full"
                data-testid="import-button"
              >
                {isImporting ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Starting Import...
                  </>
                ) : isImportInProgress ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Import In Progress
                  </>
                ) : (
                  <>
                    <Download className="h-4 w-4 mr-2" />
                    Import with this Candidate
                  </>
                )}
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center px-4">
      <Music className="h-12 w-12 text-muted-foreground/50" />
      <h3 className="mt-4 font-medium">No Album Selected</h3>
      <p className="mt-2 text-sm text-muted-foreground max-w-sm">
        Select an album from the list to view its details. Click the first disc icon
        to analyze an album and find matching candidates.
      </p>
    </div>
  )
}

function LoadingState() {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center px-4">
      <Loader2 className="h-10 w-10 animate-spin text-primary" />
      <h3 className="mt-4 font-medium">Analyzing Album</h3>
      <p className="mt-2 text-sm text-muted-foreground max-w-sm">
        Searching MusicBrainz and other sources for matching candidates...
        This may take a few seconds.
      </p>
    </div>
  )
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center px-4">
      <AlertCircle className="h-10 w-10 text-destructive" />
      <h3 className="mt-4 font-medium text-destructive">Analysis Failed</h3>
      <p className="mt-2 text-sm text-muted-foreground max-w-sm">{message}</p>
    </div>
  )
}

interface NoMatchesStateProps {
  onAddManual?: () => void
  onReanalyze?: () => void
  isAnalyzing?: boolean
}

function NoMatchesState({ onAddManual, onReanalyze, isAnalyzing = false }: NoMatchesStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center px-4">
      <Search className="h-10 w-10 text-muted-foreground/50" />
      <h3 className="mt-4 font-medium">No Matches Found</h3>
      <p className="mt-2 text-sm text-muted-foreground max-w-sm">
        Beets could not find any matching candidates for this album.
        This may happen if the album is not in MusicBrainz or has insufficient metadata.
      </p>
      {(onAddManual || onReanalyze) && (
        <div className="mt-4 flex items-center gap-2">
          {onReanalyze && (
            <Button
              variant="outline"
              size="sm"
              onClick={onReanalyze}
              disabled={isAnalyzing}
            >
              <RefreshCw
                className={cn('mr-2 h-4 w-4', isAnalyzing && 'animate-spin')}
              />
              Re-analyze
            </Button>
          )}
          {onAddManual && (
            <Button
              variant="outline"
              size="sm"
              onClick={onAddManual}
            >
              <Plus className="mr-2 h-4 w-4" />
              Add Manual Candidate
            </Button>
          )}
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * Card displaying candidate analysis details for the selected album.
 * Shows local album info, candidate matches, and track-by-track comparisons.
 */
export default function CandidateDetailsCard({
  analysisData,
  isAnalyzing = false,
  error = null,
  className,
  librarySlug,
  onAddManualCandidate,
  onReanalyze,
  onConvertAudio,
  onRemoveDuplicateWavs,
  isAudioOpRunning = false,
  audioOpError = null,
  isAddingManualCandidate = false,
  manualCandidateError = null,
  onImportClick,
  isImporting = false,
  chosenCandidateIndex = null,
  isImportInProgress = false,
}: CandidateDetailsCardProps) {
  // Track which candidates are expanded (first one by default when data loads)
  const [expandedCandidates, setExpandedCandidates] = useState<Set<number>>(
    new Set([0])
  )
  const [isDialogOpen, setIsDialogOpen] = useState(false)

  const toggleCandidate = (index: number) => {
    setExpandedCandidates((prev) => {
      const next = new Set(prev)
      if (next.has(index)) {
        next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }

  // Merge manual and automatic candidates
  const allCandidates = useMemo(() => {
    if (!analysisData) return []
    return mergeAndSortCandidates(
      analysisData.candidates,
      analysisData.manualCandidates
    )
  }, [analysisData])

  // Handle manual candidate dialog submission
  const handleManualCandidateSubmit = (link: string) => {
    if (onAddManualCandidate) {
      onAddManualCandidate(link)
    }
  }

  const handleOpenChange = (open: boolean) => {
    // Only allow closing if not loading
    if (!open && isAddingManualCandidate) return
    setIsDialogOpen(open)
  }

  // Close the dialog once a manual candidate has been added successfully.
  // We detect the isAddingManualCandidate true -> false transition; on
  // failure manualCandidateError is set, so the dialog stays open and the
  // error remains visible.
  const wasAddingRef = useRef(false)
  useEffect(() => {
    if (wasAddingRef.current && !isAddingManualCandidate && !manualCandidateError) {
      setIsDialogOpen(false)
    }
    wasAddingRef.current = isAddingManualCandidate
  }, [isAddingManualCandidate, manualCandidateError])

  // Determine what to render
  const renderContent = () => {
    if (isAnalyzing) {
      return <LoadingState />
    }

    if (error) {
      return <ErrorState message={error} />
    }

    if (!analysisData) {
      return <EmptyState />
    }

    // Check if we have any candidates (manual or automatic)
    const hasAnyCandidates = allCandidates.length > 0

    if (!hasAnyCandidates) {
      return (
        <div className="space-y-4">
          <LocalAlbumInfo
            path={analysisData.localAlbum.path}
            artist={analysisData.localAlbum.artist}
            album={analysisData.localAlbum.album}
            trackCount={analysisData.localAlbum.tracks.length}
            metadataSource={analysisData.localAlbum.metadataSource}
            dominantFormat={analysisData.localAlbum.dominantFormat}
            hasWav={analysisData.localAlbum.hasWav}
            duplicateWavCount={analysisData.localAlbum.duplicateWavCount}
            hasWma={analysisData.localAlbum.hasWma}
            wmaRecommendedTarget={analysisData.localAlbum.wmaRecommendedTarget}
            onConvertAudio={onConvertAudio}
            onRemoveDuplicateWavs={onRemoveDuplicateWavs}
            isAudioOpRunning={isAudioOpRunning}
            audioOpError={audioOpError}
          />
          <NoMatchesState
            onAddManual={onAddManualCandidate ? () => setIsDialogOpen(true) : undefined}
            onReanalyze={onReanalyze}
            isAnalyzing={isAnalyzing}
          />
        </div>
      )
    }

    return (
      <div className="space-y-4">
        {/* Local album info */}
        <LocalAlbumInfo
          path={analysisData.localAlbum.path}
          artist={analysisData.localAlbum.artist}
          album={analysisData.localAlbum.album}
          trackCount={analysisData.localAlbum.tracks.length}
          metadataSource={analysisData.localAlbum.metadataSource}
          dominantFormat={analysisData.localAlbum.dominantFormat}
          hasWav={analysisData.localAlbum.hasWav}
          duplicateWavCount={analysisData.localAlbum.duplicateWavCount}
          hasWma={analysisData.localAlbum.hasWma}
          wmaRecommendedTarget={analysisData.localAlbum.wmaRecommendedTarget}
          onConvertAudio={onConvertAudio}
          onRemoveDuplicateWavs={onRemoveDuplicateWavs}
          isAudioOpRunning={isAudioOpRunning}
          audioOpError={audioOpError}
        />

        {/* Candidates list */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-sm font-medium">
              Candidates
              <Badge variant="secondary" className="ml-2">
                {allCandidates.length}
              </Badge>
            </h4>
            <div className="flex items-center gap-2">
              {onReanalyze && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onReanalyze}
                  disabled={isAnalyzing}
                >
                  <RefreshCw
                    className={cn('mr-2 h-4 w-4', isAnalyzing && 'animate-spin')}
                  />
                  Re-analyze
                </Button>
              )}
              {onAddManualCandidate && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setIsDialogOpen(true)}
                >
                  <Plus className="mr-2 h-4 w-4" />
                  Add Manual
                </Button>
              )}
            </div>
          </div>
          <div className="space-y-2">
            {allCandidates.map((candidate, index) => (
              <CandidateCard
                key={`${candidate.isManual ? 'manual-' : ''}${candidate.sourceId || index}`}
                candidate={candidate}
                index={index}
                isExpanded={expandedCandidates.has(index)}
                onToggle={() => toggleCandidate(index)}
                localTracks={analysisData.localAlbum.tracks}
                onImportClick={onImportClick ? () => onImportClick(candidate) : undefined}
                isImporting={isImporting}
                isChosen={chosenCandidateIndex === index}
                isImportInProgress={isImportInProgress}
              />
            ))}
          </div>
        </div>

        {/* Analysis timestamp */}
        <p className="text-xs text-muted-foreground text-right">
          Analyzed {new Date(analysisData.analyzedAt).toLocaleString()}
        </p>
      </div>
    )
  }

  return (
    <>
      <Card className={cn('flex flex-col', className)}>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">Candidate Details</CardTitle>
        </CardHeader>

        <CardContent className="flex-1 min-h-[300px]">
          {renderContent()}
        </CardContent>
      </Card>

      {/* Manual candidate dialog */}
      <ManualCandidateDialog
        open={isDialogOpen}
        onOpenChange={handleOpenChange}
        librarySlug={librarySlug}
        albumKey={analysisData?.albumPath ?? null}
        initialQuery={
          analysisData
            ? [analysisData.localAlbum.artist, analysisData.localAlbum.album]
                .filter(Boolean)
                .join(' - ')
            : ''
        }
        initialArtist={analysisData?.localAlbum.artist ?? null}
        initialAlbum={analysisData?.localAlbum.album ?? null}
        expectedTracks={analysisData?.localAlbum.tracks.length ?? null}
        onSubmit={handleManualCandidateSubmit}
        isLoading={isAddingManualCandidate}
        error={manualCandidateError}
      />
    </>
  )
}
