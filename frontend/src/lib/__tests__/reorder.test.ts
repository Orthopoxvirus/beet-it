import { describe, it, expect } from 'vitest'

import type { LibraryItem } from '@/api/libraryItems'
import {
  partitionKey,
  naturalReorderIds,
  computeReorderChanges,
  nudge,
  moveWithinPartition,
  buildReorderRules,
  mergeReorderPreview,
} from '../reorder'
import type { ItemPreview } from '@/types/batch-tag-editor'

function makeItem(overrides: Partial<LibraryItem>): LibraryItem {
  return {
    id: 1,
    title: 'Track',
    artist: 'Artist',
    album: 'Album',
    album_artist: 'Artist',
    album_id: 1,
    track_number: 1,
    disc_number: 1,
    genre: null,
    path: '/music/Album/01.flac',
    duration: 180,
    format: 'FLAC',
    bitrate: 1_000_000,
    ...overrides,
  }
}

// Three-track single-disc album, titles A/B/C at positions 1/2/3.
const A = makeItem({ id: 10, track_number: 1, title: 'A' })
const B = makeItem({ id: 20, track_number: 2, title: 'B' })
const C = makeItem({ id: 30, track_number: 3, title: 'C' })
const album = [A, B, C]

describe('naturalReorderIds', () => {
  it('orders by album then disc then track number', () => {
    expect(naturalReorderIds([C, A, B])).toEqual([10, 20, 30])
  })

  it('keeps discs contiguous and ordered', () => {
    const d1t1 = makeItem({ id: 1, disc_number: 1, track_number: 1 })
    const d1t2 = makeItem({ id: 2, disc_number: 1, track_number: 2 })
    const d2t1 = makeItem({ id: 3, disc_number: 2, track_number: 1 })
    expect(naturalReorderIds([d2t1, d1t2, d1t1])).toEqual([1, 2, 3])
  })
})

describe('computeReorderChanges — keep titles OFF', () => {
  it('renumbers by position; titles travel with the track', () => {
    // Move C to the front: [C, A, B].
    const changes = computeReorderChanges(album, [30, 10, 20], false)
    expect(changes.get(30)).toEqual({ track_number: '1' }) // C: 3 -> 1
    expect(changes.get(10)).toEqual({ track_number: '2' }) // A: 1 -> 2
    expect(changes.get(20)).toEqual({ track_number: '3' }) // B: 2 -> 3
    // No title changes in this mode.
    expect(changes.get(30)?.title).toBeUndefined()
  })

  it('emits nothing for the untouched natural order', () => {
    expect(computeReorderChanges(album, [10, 20, 30], false).size).toBe(0)
  })

  it('fails safe (no changes) when the order does not cover the items', () => {
    // Stale order from a background refetch that changed the item set: an id in
    // `items` is missing from `order`. Must not renumber against a mismatch.
    expect(computeReorderChanges(album, [30, 10], false).size).toBe(0)
    // Order references an id that is no longer present.
    expect(computeReorderChanges(album, [30, 10, 20, 99], false).size).toBe(0)
  })
})

describe('computeReorderChanges — keep titles ON', () => {
  it('pins titles to their slot; the moved track adopts the slot title', () => {
    // Move C to the front: [C, A, B]. Titles 1,2,3 stay A,B,C by position.
    const changes = computeReorderChanges(album, [30, 10, 20], true)
    expect(changes.get(30)).toEqual({ track_number: '1', title: 'A' }) // C -> slot 1 (A)
    expect(changes.get(10)).toEqual({ track_number: '2', title: 'B' }) // A -> slot 2 (B)
    expect(changes.get(20)).toEqual({ track_number: '3', title: 'C' }) // B -> slot 3 (C)
  })

  it('emits nothing for the untouched natural order', () => {
    expect(computeReorderChanges(album, [10, 20, 30], true).size).toBe(0)
  })
})

describe('computeReorderChanges — multi-disc', () => {
  it('renumbers within each disc independently', () => {
    const d1t1 = makeItem({ id: 1, disc_number: 1, track_number: 1, title: 'a' })
    const d1t2 = makeItem({ id: 2, disc_number: 1, track_number: 2, title: 'b' })
    const d2t1 = makeItem({ id: 3, disc_number: 2, track_number: 1, title: 'c' })
    const d2t2 = makeItem({ id: 4, disc_number: 2, track_number: 2, title: 'd' })
    const items = [d1t1, d1t2, d2t1, d2t2]
    // Swap within disc 1 only: [2,1, 3,4].
    const changes = computeReorderChanges(items, [2, 1, 3, 4], false)
    expect(changes.get(2)).toEqual({ track_number: '1' })
    expect(changes.get(1)).toEqual({ track_number: '2' })
    // Disc 2 untouched.
    expect(changes.has(3)).toBe(false)
    expect(changes.has(4)).toBe(false)
  })
})

describe('nudge', () => {
  it('swaps a track up within its partition', () => {
    expect(nudge([10, 20, 30], album, 20, -1)).toEqual([20, 10, 30])
  })

  it('moves a track down', () => {
    expect(nudge([10, 20, 30], album, 10, 1)).toEqual([20, 10, 30])
  })

  it('is a no-op at the top of the list', () => {
    const order = [10, 20, 30]
    expect(nudge(order, album, 10, -1)).toBe(order)
  })

  it('is a no-op at the bottom of the list', () => {
    const order = [10, 20, 30]
    expect(nudge(order, album, 30, 1)).toBe(order)
  })

  it('does not cross a disc boundary', () => {
    const d1 = makeItem({ id: 1, disc_number: 1, track_number: 1 })
    const d2 = makeItem({ id: 2, disc_number: 1, track_number: 2 })
    const d3 = makeItem({ id: 3, disc_number: 2, track_number: 1 })
    const items = [d1, d2, d3]
    const order = [1, 2, 3]
    // Nudging the first disc-2 track up would cross into disc 1 — blocked.
    expect(nudge(order, items, 3, -1)).toBe(order)
  })
})

describe('moveWithinPartition', () => {
  it('drops a track upward, before the target', () => {
    expect(moveWithinPartition([10, 20, 30], album, 30, 10)).toEqual([30, 10, 20])
  })

  it('drops a track downward, after the target', () => {
    expect(moveWithinPartition([10, 20, 30], album, 10, 30)).toEqual([20, 30, 10])
  })

  it('is a no-op across partitions', () => {
    const d1 = makeItem({ id: 1, disc_number: 1, track_number: 1 })
    const d2 = makeItem({ id: 2, disc_number: 2, track_number: 1 })
    const items = [d1, d2]
    const order = [1, 2]
    expect(moveWithinPartition(order, items, 2, 1)).toBe(order)
  })

  it('is a no-op when source equals target', () => {
    const order = [10, 20, 30]
    expect(moveWithinPartition(order, album, 20, 20)).toBe(order)
  })
})

describe('buildReorderRules', () => {
  it('produces one explicit rule per changed tag', () => {
    const changes = new Map([
      [30, { track_number: '1', title: 'A' }],
      [10, { track_number: '2' }],
    ])
    const rules = buildReorderRules(changes)
    const track = rules.find((r) => r.tag === 'track_number')
    const title = rules.find((r) => r.tag === 'title')
    expect(track).toMatchObject({ mode: 'explicit', values: { 30: '1', 10: '2' } })
    expect(title).toMatchObject({ mode: 'explicit', values: { 30: 'A' } })
  })

  it('returns nothing for an empty change set', () => {
    expect(buildReorderRules(new Map())).toEqual([])
  })
})

describe('mergeReorderPreview', () => {
  it('overlays reorder changes onto existing preview entries', () => {
    const base = new Map<number, ItemPreview>([
      [10, { itemId: 10, changes: { artist: 'New Artist' } }],
    ])
    const changes = new Map([[10, { track_number: '2' }]])
    const merged = mergeReorderPreview(base, changes)
    expect(merged.get(10)?.changes).toEqual({
      artist: 'New Artist',
      track_number: '2',
    })
  })

  it('returns the base map unchanged when there are no reorder changes', () => {
    const base = new Map<number, ItemPreview>()
    expect(mergeReorderPreview(base, new Map())).toBe(base)
  })
})

describe('partitionKey', () => {
  it('combines album id and disc number', () => {
    expect(partitionKey(makeItem({ album_id: 7, disc_number: 2 }))).toBe('7::2')
  })
})
