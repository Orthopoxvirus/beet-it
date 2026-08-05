import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import UnimportedTab from '../UnimportedTab'

const h = vi.hoisted(() => ({
  unimported: null as unknown,
  enable: vi.fn(),
  action: vi.fn(),
  asCover: vi.fn(),
}))

vi.mock('@/hooks/useMaintenance', () => ({
  useUnimported: () => h.unimported,
  useEnablePlugin: () => ({
    mutate: h.enable,
    isPending: false,
    isError: false,
    error: null,
  }),
  useStrayAction: () => ({
    mutate: h.action,
    isPending: false,
    isError: false,
    error: null,
  }),
  useStrayAsCover: () => ({
    mutate: h.asCover,
    isPending: false,
    isError: false,
    error: null,
  }),
}))

const groupData = {
  data: {
    enabled: true,
    total_files: 1,
    groups: [
      {
        folder: '/m/stray',
        relative_folder: 'stray',
        total_size: 10,
        fully_untracked: true,
        album_id: null,
        cover_version: null,
        files: [
          { path: '/m/stray/s.mp3', name: 's.mp3', size: 10, is_image: false },
        ],
      },
    ],
  },
  isLoading: false,
  isError: false,
  error: null,
}

const trackedImageGroupData = {
  data: {
    enabled: true,
    total_files: 1,
    groups: [
      {
        folder: '/m/real',
        relative_folder: 'real',
        total_size: 10,
        fully_untracked: false,
        album_id: 7,
        cover_version: 1234,
        files: [
          { path: '/m/real/00-big.jpg', name: '00-big.jpg', size: 10, is_image: true },
        ],
      },
    ],
  },
  isLoading: false,
  isError: false,
  error: null,
}

describe('UnimportedTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('offers to enable the plugin when it is disabled', () => {
    h.unimported = {
      data: { enabled: false, groups: [], total_files: 0 },
      isLoading: false,
      isError: false,
      error: null,
    }
    render(<UnimportedTab slug="jazz" />)
    fireEvent.click(screen.getByRole('button', { name: /enable plugin/i }))
    expect(h.enable).toHaveBeenCalledWith('unimported')
  })

  it('requires a confirm step before deleting a stray group', () => {
    h.unimported = groupData
    render(<UnimportedTab slug="jazz" />)

    // First click only reveals the confirm button — no action yet.
    fireEvent.click(screen.getByRole('button', { name: /^delete$/i }))
    expect(h.action).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: /confirm delete/i }))
    expect(h.action).toHaveBeenCalledWith(
      { paths: ['/m/stray/s.mp3'], action: 'delete' },
      expect.anything()
    )
  })

  it('moves a stray group to import in one click', () => {
    h.unimported = groupData
    render(<UnimportedTab slug="jazz" />)
    fireEvent.click(screen.getByRole('button', { name: /move to import/i }))
    expect(h.action).toHaveBeenCalledWith(
      { paths: ['/m/stray/s.mp3'], action: 'move_to_import' },
      expect.anything()
    )
  })

  it('shows the current cover and previews for stray images in tracked albums', () => {
    h.unimported = trackedImageGroupData
    render(<UnimportedTab slug="jazz" />)
    expect(screen.getByAltText('Current cover')).toBeInTheDocument()
    expect(screen.getByAltText('00-big.jpg')).toBeInTheDocument()
  })

  it('requires a confirm step before replacing the cover with a stray image', () => {
    h.unimported = trackedImageGroupData
    render(<UnimportedTab slug="jazz" />)

    fireEvent.click(screen.getByRole('button', { name: /use as cover/i }))
    expect(h.asCover).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: /replace cover/i }))
    expect(h.asCover).toHaveBeenCalledWith('/m/real/00-big.jpg', expect.anything())
  })

  it('offers no cover action for image files outside tracked albums', () => {
    h.unimported = {
      ...groupData,
      data: {
        ...(groupData.data as object),
        groups: [
          {
            folder: '/m/stray',
            relative_folder: 'stray',
            total_size: 10,
            fully_untracked: true,
            album_id: null,
            cover_version: null,
            files: [
              { path: '/m/stray/x.jpg', name: 'x.jpg', size: 10, is_image: true },
            ],
          },
        ],
      },
    }
    render(<UnimportedTab slug="jazz" />)
    expect(
      screen.queryByRole('button', { name: /use as cover/i })
    ).not.toBeInTheDocument()
  })
})
