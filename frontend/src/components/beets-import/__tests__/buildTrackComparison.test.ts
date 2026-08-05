import { describe, it, expect } from 'vitest'
import { buildTrackComparison } from '../CandidateDetailsCard'
import type { CandidateTrack, LocalTrackInfo } from '@/types/beets-import'

const cand = (
  index: number,
  title: string,
  length: number | null,
  extra: Partial<CandidateTrack> = {}
): CandidateTrack => ({ index, title, length, changes: [], ...extra })

const local = (
  path: string,
  title: string | null,
  length: number | null,
  trackNum: number | null = null
): LocalTrackInfo => ({ path, title, trackNum, length })

describe('buildTrackComparison', () => {
  it('pairs explicit local_path/local_title when present', () => {
    const candidates = [cand(1, 'Stay', 180, { localTitle: 'Stay', localPath: '/a/01.flac' })]
    const locals = [local('/a/01.flac', 'Stay', 180, 1)]

    const { rows, localOnly, unmatchedCount } = buildTrackComparison(candidates, locals)

    expect(rows).toHaveLength(1)
    expect(rows[0].state).toBe('unchanged')
    expect(rows[0].localPath).toBe('/a/01.flac')
    expect(localOnly).toHaveLength(0)
    expect(unmatchedCount).toBe(0)
  })

  it('positionally pairs equal-count tracks when nothing paired but durations line up', () => {
    // Bug repro: tag-less files / legacy cache → every candidate row arrives
    // with localPath:null. Without a fallback this is reported as 2xN unmatched.
    const candidates = Array.from({ length: 3 }, (_, i) =>
      cand(i + 1, `Teil ${i + 1}`, [150, 75, 26][i], { localTitle: null, localPath: null })
    )
    const locals = [
      local('/a/01.flac', null, 150),
      local('/a/02.flac', null, 75),
      local('/a/03.flac', null, 26),
    ]

    const { rows, localOnly, unmatchedCount } = buildTrackComparison(candidates, locals)

    expect(rows).toHaveLength(3)
    expect(rows.every((r) => r.state !== 'new')).toBe(true)
    expect(rows.map((r) => r.localPath)).toEqual(['/a/01.flac', '/a/02.flac', '/a/03.flac'])
    expect(localOnly).toHaveLength(0)
    expect(unmatchedCount).toBe(0)
  })

  it('does NOT force positional pairing when durations disagree (genuinely different album)', () => {
    const candidates = [
      cand(1, 'X', 300, { localTitle: null, localPath: null }),
      cand(2, 'Y', 301, { localTitle: null, localPath: null }),
    ]
    const locals = [local('/a/01.flac', null, 120), local('/a/02.flac', null, 119)]

    const { rows, localOnly, unmatchedCount } = buildTrackComparison(candidates, locals)

    expect(rows.every((r) => r.state === 'new')).toBe(true)
    expect(localOnly).toHaveLength(2)
    expect(unmatchedCount).toBe(4)
  })

  it('orders multi-disc candidates by playback order with a continuous # (issue #184)', () => {
    // Per-disc indices restart at 1 on each CD; sorting by bare index grouped
    // all the disc-first tracks together and rendered repeated "#1" rows.
    const candidates = [
      cand(1, 'Kapitel über den Bären', 100, { disc: 2, localTitle: 'Kompass_03', localPath: '/a/03.mp3' }),
      cand(2, 'Kapitel 2 – Süden', 100, { disc: 1, localTitle: 'Kompass_02', localPath: '/a/02.mp3' }),
      cand(1, 'Kapitel 1 – Größe', 100, { disc: 1, localTitle: 'Kompass_01', localPath: '/a/01.mp3' }),
      cand(2, 'Kapitel 4 – Schluß', 100, { disc: 2, localTitle: 'Kompass_04', localPath: '/a/04.mp3' }),
    ]

    const { rows } = buildTrackComparison(candidates, [])

    expect(rows.map((r) => r.localTitle)).toEqual([
      'Kompass_01',
      'Kompass_02',
      'Kompass_03',
      'Kompass_04',
    ])
    expect(rows.map((r) => r.position)).toEqual([1, 2, 3, 4])
    expect(rows.map((r) => r.index)).toEqual([1, 2, 1, 2])
  })

  it('keeps single-disc order and numbering: position === index', () => {
    const candidates = [
      cand(2, 'Zwei', 100, { localTitle: 'b', localPath: '/a/02.flac' }),
      cand(1, 'Eins', 100, { localTitle: 'a', localPath: '/a/01.flac' }),
    ]

    const { rows } = buildTrackComparison(candidates, [])

    expect(rows.map((r) => r.position)).toEqual([1, 2])
    expect(rows.map((r) => r.index)).toEqual([1, 2])
  })

  it('does NOT force positional pairing when counts differ', () => {
    const candidates = [
      cand(1, 'X', 150, { localTitle: null, localPath: null }),
      cand(2, 'Y', 150, { localTitle: null, localPath: null }),
    ]
    const locals = [local('/a/01.flac', null, 150)]

    const { rows, localOnly } = buildTrackComparison(candidates, locals)

    expect(rows.every((r) => r.state === 'new')).toBe(true)
    expect(localOnly).toHaveLength(1)
  })
})
