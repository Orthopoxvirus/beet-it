import { useState } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, within, fireEvent } from '@testing-library/react'

import LibraryItemsTable from './LibraryItemsTable'
import type { LibraryItem } from '@/api/libraryItems'
import {
  naturalReorderIds,
  computeReorderChanges,
  mergeReorderPreview,
} from '@/lib/reorder'

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
    path: '/music/Artist/Album/01.flac',
    duration: 180,
    format: 'FLAC',
    bitrate: 1_000_000,
    ...overrides,
  }
}

describe('LibraryItemsTable album-header metadata', () => {
  it('shows format, average bitrate and track count on each album intertitle', () => {
    const items: LibraryItem[] = [
      makeItem({ id: 1, album: 'Album A', album_id: 1, format: 'FLAC', bitrate: 1_000_000 }),
      makeItem({ id: 2, album: 'Album A', album_id: 1, track_number: 2, format: 'FLAC', bitrate: 1_000_000 }),
      makeItem({ id: 3, album: 'Album B', album_id: 2, format: 'MP3', bitrate: 320_000 }),
    ]

    render(
      <LibraryItemsTable
        librarySlug="test-lib"
        items={items}
        isLoading={false}
        error={null}
        selectedAlbum="Multiple"
        total={items.length}
      />
    )

    const albumARow = screen.getByText('Album: Album A').closest('tr')!
    expect(within(albumARow).getByText(/FLAC/)).toBeInTheDocument()
    expect(within(albumARow).getByText(/1000 kbps/)).toBeInTheDocument()
    expect(within(albumARow).getByText(/2 tracks/)).toBeInTheDocument()

    const albumBRow = screen.getByText('Album: Album B').closest('tr')!
    expect(within(albumBRow).getByText(/320 kbps/)).toBeInTheDocument()
    expect(within(albumBRow).getByText(/1 track\b/)).toBeInTheDocument()
  })

  it('lists distinct formats when an album mixes containers', () => {
    const items: LibraryItem[] = [
      makeItem({ id: 1, album: 'Mixed', album_id: 1, format: 'flac', bitrate: 900_000 }),
      makeItem({ id: 2, album: 'Mixed', album_id: 1, track_number: 2, format: 'mp3', bitrate: 300_000 }),
      makeItem({ id: 3, album: 'Other', album_id: 2, format: 'FLAC', bitrate: 1_000_000 }),
    ]

    render(
      <LibraryItemsTable
        librarySlug="test-lib"
        items={items}
        isLoading={false}
        error={null}
        selectedAlbum="Multiple"
        total={items.length}
      />
    )

    const mixedRow = screen.getByText('Album: Mixed').closest('tr')!
    expect(within(mixedRow).getByText(/FLAC, MP3/)).toBeInTheDocument()
  })

  it('surfaces the summary in the header card for a single album', () => {
    const items: LibraryItem[] = [
      makeItem({ id: 1, album: 'Solo', album_id: 1, format: 'FLAC', bitrate: 1_411_000 }),
      makeItem({ id: 2, album: 'Solo', album_id: 1, track_number: 2, format: 'FLAC', bitrate: 1_411_000 }),
    ]

    render(
      <LibraryItemsTable
        librarySlug="test-lib"
        items={items}
        isLoading={false}
        error={null}
        selectedAlbum="Solo"
        total={items.length}
      />
    )

    // Single album → no intertitle row, so the facts live in the header card.
    expect(screen.queryByText('Album: Solo')).not.toBeInTheDocument()
    expect(screen.getByText(/FLAC · 1411 kbps · 2 tracks/)).toBeInTheDocument()
  })
})

describe('LibraryItemsTable per-track playback', () => {
  const twoTracks: LibraryItem[] = [
    makeItem({ id: 1, title: 'Track A', album: 'Solo', album_id: 1, track_number: 1 }),
    makeItem({ id: 2, title: 'Track B', album: 'Solo', album_id: 1, track_number: 2 }),
  ]

  it('renders a play button per track', () => {
    render(
      <LibraryItemsTable
        librarySlug="test-lib"
        items={twoTracks}
        isLoading={false}
        error={null}
        selectedAlbum="Solo"
        total={twoTracks.length}
      />
    )

    expect(screen.getByRole('button', { name: 'Play Track A' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Play Track B' })).toBeInTheDocument()
  })

  it('toggles the clicked track to a pause control and leaves others idle', () => {
    render(
      <LibraryItemsTable
        librarySlug="test-lib"
        items={twoTracks}
        isLoading={false}
        error={null}
        selectedAlbum="Solo"
        total={twoTracks.length}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Play Track A' }))

    // The clicked row now offers Pause; the other stays on Play.
    expect(screen.getByRole('button', { name: 'Pause Track A' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Play Track B' })).toBeInTheDocument()

    // Only one track plays at a time: starting B reverts A to Play.
    fireEvent.click(screen.getByRole('button', { name: 'Play Track B' }))
    expect(screen.getByRole('button', { name: 'Play Track A' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pause Track B' })).toBeInTheDocument()

    // Clicking the active track again pauses it.
    fireEvent.click(screen.getByRole('button', { name: 'Pause Track B' }))
    expect(screen.getByRole('button', { name: 'Play Track B' })).toBeInTheDocument()
  })
})

describe('LibraryItemsTable reorder mode', () => {
  const album: LibraryItem[] = [
    makeItem({ id: 1, title: 'Track A', album: 'Solo', album_id: 1, track_number: 1 }),
    makeItem({ id: 2, title: 'Track B', album: 'Solo', album_id: 1, track_number: 2 }),
    makeItem({ id: 3, title: 'Track C', album: 'Solo', album_id: 1, track_number: 3 }),
  ]

  // Mirrors how BatchEditTab drives the table: holds the working order and
  // recomputes the merged preview from the real reorder lib on each change.
  function ReorderHarness({
    items,
    keepTitles = false,
  }: {
    items: LibraryItem[]
    keepTitles?: boolean
  }) {
    const [order, setOrder] = useState<number[]>(() => naturalReorderIds(items))
    const previewData = mergeReorderPreview(
      new Map(),
      computeReorderChanges(items, order, keepTitles)
    )
    return (
      <LibraryItemsTable
        librarySlug="test-lib"
        items={items}
        isLoading={false}
        error={null}
        selectedAlbum="Solo"
        total={items.length}
        previewData={previewData}
        canReorder
        reorderMode
        keepTitles={keepTitles}
        order={order}
        onReorder={setOrder}
      />
    )
  }

  it('offers a Reorder button when reordering is available', () => {
    const onToggle = vi.fn()
    render(
      <LibraryItemsTable
        librarySlug="test-lib"
        items={album}
        isLoading={false}
        error={null}
        selectedAlbum="Solo"
        total={album.length}
        canReorder
        onToggleReorder={onToggle}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: 'Reorder' }))
    expect(onToggle).toHaveBeenCalledOnce()
  })

  it('hides the Reorder button when reordering is not available', () => {
    render(
      <LibraryItemsTable
        librarySlug="test-lib"
        items={album}
        isLoading={false}
        error={null}
        selectedAlbum="Solo"
        total={album.length}
        canReorder={false}
      />
    )
    expect(screen.queryByRole('button', { name: 'Reorder' })).not.toBeInTheDocument()
  })

  it('disables the up control on the first row', () => {
    render(<ReorderHarness items={album} />)
    expect(screen.getByRole('button', { name: 'Move Track A up' })).toBeDisabled()
  })

  it('renumbers via the preview when a track moves (keep titles off)', () => {
    render(<ReorderHarness items={album} />)
    fireEvent.click(screen.getByRole('button', { name: 'Move Track A down' }))

    // Track A drops to position 2 → its number previews 1 → 2.
    const rowA = screen.getByTestId('reorder-row-1')
    expect(within(rowA).getByText('2')).toBeInTheDocument()
    // Title travels with the track in this mode.
    expect(within(rowA).queryByText('Track B')).not.toBeInTheDocument()
  })

  it('reassigns titles to their slot when keep titles is on', () => {
    render(<ReorderHarness items={album} keepTitles />)
    fireEvent.click(screen.getByRole('button', { name: 'Move Track A down' }))

    // Slot-pinned titles: A moves into slot 2 and adopts "Track B".
    const rowA = screen.getByTestId('reorder-row-1')
    expect(within(rowA).getByText('Track B')).toBeInTheDocument()
  })

  it('toggles keep-titles via the switch', () => {
    const onKeep = vi.fn()
    render(
      <LibraryItemsTable
        librarySlug="test-lib"
        items={album}
        isLoading={false}
        error={null}
        selectedAlbum="Solo"
        total={album.length}
        canReorder
        reorderMode
        keepTitles={false}
        onKeepTitlesChange={onKeep}
        order={naturalReorderIds(album)}
      />
    )
    fireEvent.click(screen.getByRole('switch', { name: 'Keep track titles' }))
    expect(onKeep).toHaveBeenCalledWith(true)
  })
})
