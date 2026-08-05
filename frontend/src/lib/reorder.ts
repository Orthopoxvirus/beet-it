// ============================================================================
// Track reorder logic (pure)
// ============================================================================
//
// Drag-reorder for the batch-edit "Selected album" card. Reordering is scoped
// to a single album and renumbers *within each disc* (per issue #104).
//
// The model is slot-based and symmetric across the "keep track titles" toggle:
//
//   - A partition is one (album, disc). Within it, the original tracks define
//     numbered slots, sorted by their current track number.
//   - Slot i owns a track number (and a title). When the user drags tracks
//     into a new order, the track that ends up at slot i adopts that slot's
//     number — and, when "keep titles" is on, that slot's title too.
//
//   keep titles OFF → the title travels with the file; only the number changes.
//   keep titles ON  → titles stay pinned to their slot; the file that moves in
//                     takes the slot's old title (so titles 1,2,3 stay 1,2,3).
//
// `computeReorderChanges` emits a change for a track only where the new value
// differs from its current one, so an untouched order produces no changes and
// nothing is committed. The same map drives both the inline preview and the
// explicit rules sent on "Apply Changes" — one source of truth, no drift.
// ============================================================================

import type { LibraryItem } from '@/api/libraryItems'
import type {
  ItemPreview,
  TransformationRule,
  ExplicitRule,
} from '@/types/batch-tag-editor'

/** The per-track values a reorder would write. */
export type ReorderChange = {
  track_number?: string
  title?: string
}

/**
 * Partition key for reorder scope: one numbering run per (album, disc).
 * Reorder is gated to single-album selections, so in practice this splits an
 * album into its discs.
 */
export function partitionKey(
  item: Pick<LibraryItem, 'album_id' | 'disc_number'>
): string {
  return `${item.album_id}::${item.disc_number}`
}

/**
 * Item ids in natural display order — mirrors LibraryItemsTable's sort so the
 * reorder list seeds exactly as the read-only table renders: album groups
 * alphabetical, tracks within a group by disc then track number.
 */
export function naturalReorderIds(items: LibraryItem[]): number[] {
  const groups = new Map<string, LibraryItem[]>()
  for (const it of items) {
    const album = it.album || 'Unknown Album'
    const arr = groups.get(album) ?? []
    arr.push(it)
    groups.set(album, arr)
  }
  const names = Array.from(groups.keys()).sort((a, b) => a.localeCompare(b))
  const ids: number[] = []
  for (const name of names) {
    const tracks = [...groups.get(name)!].sort(
      (a, b) => a.disc_number - b.disc_number || a.track_number - b.track_number
    )
    for (const t of tracks) ids.push(t.id)
  }
  return ids
}

/**
 * Compute the per-track changes implied by the working `order`, given the
 * "keep titles" toggle. Only changed tracks appear in the result.
 */
export function computeReorderChanges(
  items: LibraryItem[],
  order: number[],
  keepTitles: boolean
): Map<number, ReorderChange> {
  const changes = new Map<number, ReorderChange>()

  // Fail safe: only compute when the working order covers exactly the current
  // items. If a background refetch changed the item set while reorder mode was
  // open, `order` is stale — emit no changes rather than renumbering against a
  // mismatched order (which would otherwise silently commit wrong numbers).
  const orderSet = new Set(order)
  if (order.length !== items.length || !items.every((it) => orderSet.has(it.id))) {
    return changes
  }

  const partitions = new Map<string, LibraryItem[]>()
  for (const it of items) {
    const k = partitionKey(it)
    const arr = partitions.get(k) ?? []
    arr.push(it)
    partitions.set(k, arr)
  }

  const orderIndex = new Map(order.map((id, i) => [id, i]))

  for (const members of partitions.values()) {
    // Slots = original numbering, sorted by track number (stable by id).
    const slots = [...members].sort(
      (a, b) => a.track_number - b.track_number || a.id - b.id
    )
    // Current = the same members arranged by the working order.
    const current = [...members].sort(
      (a, b) => (orderIndex.get(a.id) ?? 0) - (orderIndex.get(b.id) ?? 0)
    )

    current.forEach((item, i) => {
      const slot = slots[i]
      if (!slot) return
      const change: ReorderChange = {}

      const newTrack = String(slot.track_number)
      if (newTrack !== String(item.track_number)) {
        change.track_number = newTrack
      }
      if (keepTitles) {
        const newTitle = slot.title ?? ''
        if (newTitle !== (item.title ?? '')) {
          change.title = newTitle
        }
      }

      if (change.track_number !== undefined || change.title !== undefined) {
        changes.set(item.id, change)
      }
    })
  }

  return changes
}

/**
 * Move a track one slot up (`dir = -1`) or down (`dir = 1`) within its
 * partition. A no-op when it would cross a partition boundary or run off the
 * end — returns the same array reference so callers can skip a state update.
 */
export function nudge(
  order: number[],
  items: LibraryItem[],
  id: number,
  dir: -1 | 1
): number[] {
  const byId = new Map(items.map((i) => [i.id, i]))
  const idx = order.indexOf(id)
  if (idx < 0) return order
  const swap = idx + dir
  if (swap < 0 || swap >= order.length) return order

  const a = byId.get(order[idx])
  const b = byId.get(order[swap])
  if (!a || !b || partitionKey(a) !== partitionKey(b)) return order

  const next = order.slice()
  ;[next[idx], next[swap]] = [next[swap], next[idx]]
  return next
}

/**
 * Drag-drop reorder: place `draggedId` at `targetId`'s position. Constrained
 * to a single partition — dropping across an album/disc boundary is ignored
 * (returns the same array reference).
 */
export function moveWithinPartition(
  order: number[],
  items: LibraryItem[],
  draggedId: number,
  targetId: number
): number[] {
  if (draggedId === targetId) return order
  const byId = new Map(items.map((i) => [i.id, i]))
  const a = byId.get(draggedId)
  const b = byId.get(targetId)
  if (!a || !b || partitionKey(a) !== partitionKey(b)) return order

  const from = order.indexOf(draggedId)
  const targetIdx = order.indexOf(targetId)
  if (from < 0 || targetIdx < 0) return order

  const next = order.slice()
  next.splice(from, 1)
  const insertAt = next.indexOf(targetId)
  // Dropping downward lands after the target; upward lands before it.
  const finalIdx = from < targetIdx ? insertAt + 1 : insertAt
  next.splice(finalIdx, 0, draggedId)
  return next
}

/**
 * Convert reorder changes into explicit transformation rules — one per tag —
 * for the batch-update request. Empty when there are no changes.
 */
export function buildReorderRules(
  changes: Map<number, ReorderChange>
): TransformationRule[] {
  const trackValues: Record<number, string> = {}
  const titleValues: Record<number, string> = {}
  for (const [id, change] of changes) {
    if (change.track_number !== undefined) trackValues[id] = change.track_number
    if (change.title !== undefined) titleValues[id] = change.title
  }

  const rules: TransformationRule[] = []
  if (Object.keys(trackValues).length > 0) {
    rules.push({ tag: 'track_number', mode: 'explicit', values: trackValues } as ExplicitRule)
  }
  if (Object.keys(titleValues).length > 0) {
    rules.push({ tag: 'title', mode: 'explicit', values: titleValues } as ExplicitRule)
  }
  return rules
}

/**
 * Overlay reorder changes onto the batch-editor's preview map so the table
 * renders both in one pass. Reorder wins for the tags it touches.
 */
export function mergeReorderPreview(
  base: Map<number, ItemPreview>,
  changes: Map<number, ReorderChange>
): Map<number, ItemPreview> {
  if (changes.size === 0) return base
  const merged = new Map(base)
  for (const [id, change] of changes) {
    const existing = merged.get(id)
    merged.set(id, {
      itemId: id,
      changes: { ...(existing?.changes ?? {}), ...change },
      warnings: existing?.warnings,
    })
  }
  return merged
}
