import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import type { ReactNode } from 'react'

import { DownloadGatherProvider, useDownloadGather } from './DownloadGatherContext'

const wrapper = ({ children }: { children: ReactNode }) => (
  <DownloadGatherProvider>{children}</DownloadGatherProvider>
)

const album = (id: number, sizeBytes: number | null = null) => ({
  id,
  title: `Album ${id}`,
  artist: `Artist ${id}`,
  sizeBytes,
})

describe('DownloadGatherContext', () => {
  beforeEach(() => localStorage.clear())

  it('adds albums and tracks count, total size and last-added', () => {
    const { result } = renderHook(() => useDownloadGather(), { wrapper })

    act(() => result.current.addAlbum('lib', album(1, 100)))
    act(() => result.current.addAlbum('lib', album(2, 250)))

    expect(result.current.count).toBe(2)
    expect(result.current.totalSize).toBe(350)
    expect(result.current.lastAdded?.id).toBe(2)
    expect(result.current.isGathered(1)).toBe(true)
    expect(result.current.slug).toBe('lib')
  })

  it('upserts in place to fill in a later size without changing order', () => {
    const { result } = renderHook(() => useDownloadGather(), { wrapper })

    act(() => result.current.addAlbum('lib', album(1, null)))
    act(() => result.current.addAlbum('lib', album(2, 50)))
    act(() => result.current.addAlbum('lib', album(1, 999))) // size arrives late

    expect(result.current.count).toBe(2)
    expect(result.current.totalSize).toBe(1049)
    expect(result.current.items[0].id).toBe(1) // position preserved
  })

  it('removes albums and clears the slug when empty', () => {
    const { result } = renderHook(() => useDownloadGather(), { wrapper })

    act(() => result.current.addAlbum('lib', album(1)))
    act(() => result.current.removeAlbum(1))

    expect(result.current.count).toBe(0)
    expect(result.current.slug).toBeNull()
  })

  it('starts a fresh gather when adding from a different library', () => {
    const { result } = renderHook(() => useDownloadGather(), { wrapper })

    act(() => result.current.addAlbum('lib-a', album(1)))
    act(() => result.current.addAlbum('lib-a', album(2)))
    act(() => result.current.addAlbum('lib-b', album(3)))

    expect(result.current.slug).toBe('lib-b')
    expect(result.current.count).toBe(1)
    expect(result.current.isGathered(1)).toBe(false)
  })

  it('persists to localStorage and rehydrates', () => {
    const first = renderHook(() => useDownloadGather(), { wrapper })
    act(() => first.result.current.addAlbum('lib', album(7, 42)))

    // A fresh provider instance reads the persisted state.
    const second = renderHook(() => useDownloadGather(), { wrapper })
    expect(second.result.current.count).toBe(1)
    expect(second.result.current.items[0].id).toBe(7)
    expect(second.result.current.totalSize).toBe(42)
  })

  it('clear() empties the gather', () => {
    const { result } = renderHook(() => useDownloadGather(), { wrapper })
    act(() => result.current.addAlbum('lib', album(1)))
    act(() => result.current.clear())
    expect(result.current.count).toBe(0)
    expect(result.current.slug).toBeNull()
  })
})

describe('DownloadGatherContext — tracks', () => {
  beforeEach(() => localStorage.clear())

  const track = (id: number) => ({ id, title: `Title ${id}`, artist: `Artist ${id}` })

  it('adds tracks alongside albums with separate counts and membership', () => {
    const { result } = renderHook(() => useDownloadGather(), { wrapper })

    act(() => result.current.addAlbum('lib', album(1, 100)))
    act(() => result.current.addTracks('lib', [track(1), track(2)]))

    expect(result.current.count).toBe(3)
    expect(result.current.albumCount).toBe(1)
    expect(result.current.trackCount).toBe(2)
    // Track id 1 and album id 1 don't collide.
    expect(result.current.isGathered(1)).toBe(true)
    expect(result.current.isTrackGathered(1)).toBe(true)
    expect(result.current.isTrackGathered(3)).toBe(false)
  })

  it('bulk add deduplicates against already-gathered tracks', () => {
    const { result } = renderHook(() => useDownloadGather(), { wrapper })

    act(() => result.current.addTracks('lib', [track(1), track(2)]))
    act(() => result.current.addTracks('lib', [track(2), track(3)]))

    expect(result.current.trackCount).toBe(3)
  })

  it('removeTrack only removes the track, not a same-id album', () => {
    const { result } = renderHook(() => useDownloadGather(), { wrapper })

    act(() => result.current.addAlbum('lib', album(7)))
    act(() => result.current.addTracks('lib', [track(7)]))
    act(() => result.current.removeTrack(7))

    expect(result.current.trackCount).toBe(0)
    expect(result.current.isGathered(7)).toBe(true)
  })

  it('treats persisted entries without kind as albums (legacy storage)', () => {
    localStorage.setItem(
      'download-gather',
      JSON.stringify({ slug: 'lib', items: [{ id: 5, title: 'Old', artist: 'A', sizeBytes: 10 }] })
    )
    const { result } = renderHook(() => useDownloadGather(), { wrapper })

    expect(result.current.albumCount).toBe(1)
    expect(result.current.trackCount).toBe(0)
    expect(result.current.isGathered(5)).toBe(true)
  })
})
