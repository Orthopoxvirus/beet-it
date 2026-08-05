import type { AlbumQualityStats } from '@/types/beets-import'

interface UpgradeComparisonProps {
  existing: AlbumQualityStats | null
  incoming: AlbumQualityStats | null
}

// ---- formatting helpers ----------------------------------------------------

function formatBytes(n: number | null | undefined): string {
  if (!n) return '—'
  const units = ['B', 'KB', 'MB', 'GB']
  let v = n
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`
}

function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return '—'
  const totalMin = Math.round(seconds / 60)
  if (totalMin < 60) return `${totalMin} min`
  const h = Math.floor(totalMin / 60)
  const m = totalMin % 60
  return `${h}h ${m.toString().padStart(2, '0')}m`
}

function formatBitrate(kbps: number | null | undefined): string {
  if (!kbps) return '—'
  return `${kbps} kbps`
}

// ---- diff direction --------------------------------------------------------

// 'up' = incoming is better, 'down' = existing is better, 'same' or null.
type Direction = 'up' | 'down' | 'same' | null

function compareNumeric(
  existing: number | null | undefined,
  incoming: number | null | undefined,
  higherIsBetter: boolean
): Direction {
  if (existing == null || incoming == null) return null
  if (existing === incoming) return 'same'
  const incomingBigger = incoming > existing
  if (incomingBigger === higherIsBetter) return 'up'
  return 'down'
}

function compareFormat(existing: string | null, incoming: string | null): Direction {
  if (!existing || !incoming) return null
  if (existing === incoming) return 'same'
  // Lossless wins over lossy. If the tiers differ, we can call it; otherwise leave neutral.
  const lossless = new Set(['FLAC', 'WAV', 'AIFF', 'ALAC', 'APE'])
  const eLossless = lossless.has(existing.toUpperCase())
  const iLossless = lossless.has(incoming.toUpperCase())
  if (iLossless && !eLossless) return 'up'
  if (!iLossless && eLossless) return 'down'
  return null
}

function directionClass(dir: Direction): string {
  if (dir === 'up') return 'text-emerald-600 dark:text-emerald-400 font-medium'
  if (dir === 'down') return 'text-red-600 dark:text-red-400 font-medium'
  return ''
}

// ---- component -------------------------------------------------------------

interface Row {
  label: string
  existing: string
  incoming: string
  dir: Direction
}

export function UpgradeComparison({
  existing,
  incoming,
}: UpgradeComparisonProps) {
  // Nothing to show — fall back to the plain "no details" note.
  if (!existing && !incoming) {
    return (
      <p className="text-xs text-muted-foreground italic">
        No detailed comparison available for this pair.
      </p>
    )
  }

  const rows: Row[] = [
    {
      label: 'Format',
      existing: existing?.dominantFormat ?? '—',
      incoming: incoming?.dominantFormat ?? '—',
      dir: compareFormat(
        existing?.dominantFormat ?? null,
        incoming?.dominantFormat ?? null
      ),
    },
    {
      label: 'Bitrate',
      existing: formatBitrate(existing?.avgBitrateKbps),
      incoming: formatBitrate(incoming?.avgBitrateKbps),
      dir: compareNumeric(existing?.avgBitrateKbps, incoming?.avgBitrateKbps, true),
    },
    {
      label: 'Tracks',
      existing: existing?.trackCount?.toString() ?? '—',
      incoming: incoming?.trackCount?.toString() ?? '—',
      dir: compareNumeric(existing?.trackCount, incoming?.trackCount, true),
    },
    {
      label: 'Duration',
      existing: formatDuration(existing?.totalDurationSeconds),
      incoming: formatDuration(incoming?.totalDurationSeconds),
      dir: compareNumeric(
        existing?.totalDurationSeconds,
        incoming?.totalDurationSeconds,
        true
      ),
    },
    {
      label: 'Size',
      existing: formatBytes(existing?.totalBytes),
      incoming: formatBytes(incoming?.totalBytes),
      // Bigger size isn't necessarily better — leave neutral.
      dir: null,
    },
  ]

  return (
    <div className="rounded border text-xs">
      <div className="grid grid-cols-[auto_1fr_1fr] gap-x-2 gap-y-1 p-3">
        <div className="font-medium text-muted-foreground">&nbsp;</div>
        <div className="font-medium">Incoming</div>
        <div className="font-medium">Existing</div>
        {rows.map((row) => (
          <FragmentRow key={row.label} row={row} />
        ))}
      </div>
    </div>
  )
}

function FragmentRow({ row }: { row: Row }) {
  return (
    <>
      <div className="text-muted-foreground">{row.label}</div>
      <div className={directionClass(row.dir)}>{row.incoming}</div>
      <div>{row.existing}</div>
    </>
  )
}
