// ============================================================================
// Manual track ordering — pure logic for the batch editor's Manual mode
// ============================================================================
//
// Position is the source of truth: typing a number into a row moves that row
// to the typed position, and both typing and dragging renumber every row to
// its position (1..N). A hand-placed row therefore keeps its spot until the
// user moves something across it on purpose — manual entries are never
// clobbered by a later drag, they just flow with the order.

/** One row of the manual ordering state for a single album table. */
export interface TrackOrderEntry {
  itemId: number
  /** Current (possibly edited) track number shown in the row's input. */
  number: number
  /** The track number the scan found, for computing the changed-values diff. */
  originalNumber: number | null
}

interface OrderableItem {
  id: number
  trackNumber: number | null
  filename: string
}

/**
 * Build the initial ordering from scanned items: sorted by current track
 * number (unnumbered tracks last, then by filename), numbers prefilled with
 * what is currently set. Unnumbered tracks are prefilled with their position
 * so every input starts with a value.
 */
export function initTrackOrder(items: OrderableItem[]): TrackOrderEntry[] {
  const sorted = [...items].sort((a, b) => {
    if (a.trackNumber !== null && b.trackNumber !== null) {
      return a.trackNumber - b.trackNumber || a.filename.localeCompare(b.filename)
    }
    if (a.trackNumber !== null) return -1
    if (b.trackNumber !== null) return 1
    return a.filename.localeCompare(b.filename)
  })
  return sorted.map((item, index) => ({
    itemId: item.id,
    number: item.trackNumber ?? index + 1,
    originalNumber: item.trackNumber,
  }))
}

/** Renumber entries to match their position (1..N). */
function renumber(entries: TrackOrderEntry[]): TrackOrderEntry[] {
  return entries.map((entry, index) =>
    entry.number === index + 1 ? entry : { ...entry, number: index + 1 }
  )
}

/**
 * Commit a manually typed number: move the row to that position (clamped to
 * 1..N) and renumber everything, so the table re-sorts and the other tracks
 * shift around the moved one.
 */
export function applyManualNumber(
  entries: TrackOrderEntry[],
  itemId: number,
  typedNumber: number
): TrackOrderEntry[] {
  const from = entries.findIndex((e) => e.itemId === itemId)
  if (from < 0) return entries
  const to = Math.min(Math.max(Math.trunc(typedNumber), 1), entries.length) - 1
  return applyDragReorder(entries, from, to)
}

/** Move a row from one position to another (drag & drop) and renumber. */
export function applyDragReorder(
  entries: TrackOrderEntry[],
  fromIndex: number,
  toIndex: number
): TrackOrderEntry[] {
  if (
    fromIndex === toIndex ||
    fromIndex < 0 ||
    toIndex < 0 ||
    fromIndex >= entries.length ||
    toIndex >= entries.length
  ) {
    return renumber(entries)
  }
  const next = [...entries]
  const [moved] = next.splice(fromIndex, 1)
  next.splice(toIndex, 0, moved)
  return renumber(next)
}

/**
 * The item-id → value map for the ExplicitRule: only tracks whose number
 * actually differs from what the scan found, so an untouched Manual mode
 * previews and applies as a no-op.
 */
export function trackOrderDiff(entries: TrackOrderEntry[]): Record<number, string> {
  const values: Record<number, string> = {}
  for (const entry of entries) {
    if (entry.number !== entry.originalNumber) {
      values[entry.itemId] = String(entry.number)
    }
  }
  return values
}
