import { describe, it, expect } from 'vitest'

import {
  initTrackOrder,
  applyManualNumber,
  applyDragReorder,
  trackOrderDiff,
} from './track-order'

const items = [
  { id: 11, trackNumber: 2, filename: '02 - Grüße.flac' },
  { id: 12, trackNumber: 1, filename: '01 - Anfang.flac' },
  { id: 13, trackNumber: 3, filename: '03 - Schluß.flac' },
]

describe('initTrackOrder', () => {
  it('sorts by current track number and prefills the numbers as-is', () => {
    const order = initTrackOrder(items)
    expect(order.map((e) => e.itemId)).toEqual([12, 11, 13])
    expect(order.map((e) => e.number)).toEqual([1, 2, 3])
    expect(order.map((e) => e.originalNumber)).toEqual([1, 2, 3])
  })

  it('puts unnumbered tracks last (by filename) and prefills their position', () => {
    const order = initTrackOrder([
      { id: 21, trackNumber: null, filename: 'b.flac' },
      { id: 22, trackNumber: 5, filename: 'a.flac' },
      { id: 23, trackNumber: null, filename: 'a.flac' },
    ])
    expect(order.map((e) => e.itemId)).toEqual([22, 23, 21])
    expect(order.map((e) => e.number)).toEqual([5, 2, 3])
  })

  it('breaks duplicate numbers by filename', () => {
    const order = initTrackOrder([
      { id: 31, trackNumber: 1, filename: 'b.flac' },
      { id: 32, trackNumber: 1, filename: 'a.flac' },
    ])
    expect(order.map((e) => e.itemId)).toEqual([32, 31])
  })
})

describe('applyManualNumber', () => {
  it('moves the track to the typed position and shifts the others', () => {
    // Type "1" on the last track: it moves to the top, the rest shift down.
    const next = applyManualNumber(initTrackOrder(items), 13, 1)
    expect(next.map((e) => e.itemId)).toEqual([13, 12, 11])
    expect(next.map((e) => e.number)).toEqual([1, 2, 3])
  })

  it('clamps typed numbers to the album length', () => {
    const next = applyManualNumber(initTrackOrder(items), 12, 99)
    expect(next.map((e) => e.itemId)).toEqual([11, 13, 12])
    expect(next.map((e) => e.number)).toEqual([1, 2, 3])
  })

  it('ignores unknown item ids', () => {
    const order = initTrackOrder(items)
    expect(applyManualNumber(order, 999, 1)).toBe(order)
  })
})

describe('applyDragReorder', () => {
  it('moves the dragged row and renumbers everything by position', () => {
    const next = applyDragReorder(initTrackOrder(items), 0, 2)
    expect(next.map((e) => e.itemId)).toEqual([11, 13, 12])
    expect(next.map((e) => e.number)).toEqual([1, 2, 3])
  })

  it('renumbers gapped prefills even when nothing moves', () => {
    const order = initTrackOrder([
      { id: 41, trackNumber: 3, filename: 'a.flac' },
      { id: 42, trackNumber: 7, filename: 'b.flac' },
    ])
    const next = applyDragReorder(order, 0, 0)
    expect(next.map((e) => e.number)).toEqual([1, 2])
  })
})

describe('trackOrderDiff', () => {
  it('is empty while the order is untouched', () => {
    expect(trackOrderDiff(initTrackOrder(items))).toEqual({})
  })

  it('contains only tracks whose number changed', () => {
    const next = applyManualNumber(initTrackOrder(items), 13, 1)
    expect(trackOrderDiff(next)).toEqual({ 13: '1', 12: '2', 11: '3' })
    // Move it back — the diff collapses to empty again.
    const back = applyManualNumber(next, 13, 3)
    expect(trackOrderDiff(back)).toEqual({})
  })

  it('includes previously unnumbered tracks once they get a number', () => {
    const order = initTrackOrder([
      { id: 51, trackNumber: 1, filename: 'a.flac' },
      { id: 52, trackNumber: null, filename: 'b.flac' },
    ])
    expect(trackOrderDiff(order)).toEqual({ 52: '2' })
  })
})
