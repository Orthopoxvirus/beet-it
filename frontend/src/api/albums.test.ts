import { describe, it, expect } from 'vitest'

import { getAlbumCoverUrl } from './albums'

describe('getAlbumCoverUrl', () => {
  it('returns the bare cover URL with no params', () => {
    expect(getAlbumCoverUrl('rock', 7)).toMatch(/\/libraries\/rock\/albums\/7\/cover$/)
  })

  it('appends the size param', () => {
    expect(getAlbumCoverUrl('rock', 7, 384)).toMatch(/\/cover\?size=384$/)
  })

  it('appends the cover_version cache-buster as v', () => {
    const url = getAlbumCoverUrl('rock', 7, 384, 1750000000)
    expect(url).toContain('size=384')
    expect(url).toContain('v=1750000000')
  })

  it('adds v even when size is omitted', () => {
    expect(getAlbumCoverUrl('rock', 7, undefined, 42)).toMatch(/\/cover\?v=42$/)
  })

  it('omits v when version is null or undefined (issue #105 — unchanged covers keep caching)', () => {
    expect(getAlbumCoverUrl('rock', 7, 384, null)).not.toContain('v=')
    expect(getAlbumCoverUrl('rock', 7, 384, undefined)).not.toContain('v=')
  })

  it('treats version 0 as a valid buster (not falsy-dropped)', () => {
    expect(getAlbumCoverUrl('rock', 7, 384, 0)).toContain('v=0')
  })
})
