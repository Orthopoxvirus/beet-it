import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ManualCandidateDialog from '../ManualCandidateDialog'
import { searchCandidates } from '@/api/beets-import'
import type { SearchCandidatesResponse } from '@/types/beets-import'

// The dialog's Search tab calls the API client directly; mock it.
vi.mock('@/api/beets-import', () => ({
  searchCandidates: vi.fn(),
}))

const mockedSearch = vi.mocked(searchCandidates)

function makeResponse(overrides: Partial<SearchCandidatesResponse> = {}): SearchCandidatesResponse {
  return {
    query: 'daft punk',
    page: 1,
    perPage: 5,
    providers: [
      {
        provider: 'musicbrainz',
        available: true,
        reason: null,
        hasMore: true,
        results: [
          {
            provider: 'musicbrainz',
            sourceId: 'mb1',
            title: 'Discovery',
            artist: 'Daft Punk',
            year: 2001,
            trackCount: 14,
            externalUrl: 'https://musicbrainz.org/release/mb1',
            coverUrl: null,
          },
        ],
      },
      { provider: 'spotify', available: true, reason: null, hasMore: false, results: [] },
      {
        provider: 'deezer',
        available: true,
        reason: null,
        hasMore: false,
        results: [
          {
            provider: 'deezer',
            sourceId: 'dz1',
            title: 'Homework',
            artist: 'Daft Punk',
            year: null,
            trackCount: 16,
            externalUrl: 'https://www.deezer.com/album/dz1',
            coverUrl: null,
          },
        ],
      },
      {
        provider: 'discogs',
        available: false,
        reason:
          'Discogs search requires a personal access token (set discogs.user_token in the library config).',
        hasMore: false,
        results: [],
      },
    ],
    ...overrides,
  }
}

describe('ManualCandidateDialog', () => {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    librarySlug: 'test-library',
    onSubmit: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
    mockedSearch.mockResolvedValue(makeResponse())
  })

  /** Switch to the "Paste link" tab and return its input. */
  async function gotoLinkTab(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole('tab', { name: /paste link/i }))
    return screen.getByLabelText('Link or MusicBrainz ID')
  }

  describe('Rendering', () => {
    it('should render dialog when open and default to the Search tab', () => {
      render(<ManualCandidateDialog {...defaultProps} />)

      expect(screen.getByText('Add Manual Candidate')).toBeInTheDocument()
      expect(screen.getByLabelText('Search term')).toBeInTheDocument()
    })

    it('should not render dialog when closed', () => {
      render(<ManualCandidateDialog {...defaultProps} open={false} />)

      expect(screen.queryByText('Add Manual Candidate')).not.toBeInTheDocument()
    })

    it('should expose both Search and Paste link tabs', () => {
      render(<ManualCandidateDialog {...defaultProps} />)

      expect(screen.getByRole('tab', { name: /search/i })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: /paste link/i })).toBeInTheDocument()
    })

    it('should show supported providers info on the link tab', async () => {
      const user = userEvent.setup()
      render(<ManualCandidateDialog {...defaultProps} />)
      await gotoLinkTab(user)

      expect(screen.getByText('Supported providers:')).toBeInTheDocument()
      expect(screen.getByText('Deezer:')).toBeInTheDocument()
      expect(screen.getByText('Spotify:')).toBeInTheDocument()
      expect(screen.getByText('Discogs:')).toBeInTheDocument()
      expect(screen.getByText('MusicBrainz:')).toBeInTheDocument()
    })
  })

  describe('Search mode', () => {
    it('runs a search and renders results grouped by provider', async () => {
      const user = userEvent.setup()
      render(<ManualCandidateDialog {...defaultProps} />)

      await user.type(screen.getByLabelText('Search term'), 'daft punk')
      await user.click(screen.getByRole('button', { name: /search/i }))

      await waitFor(() => expect(screen.getByText('Discovery')).toBeInTheDocument())
      expect(screen.getByText('Homework')).toBeInTheDocument()
      expect(mockedSearch).toHaveBeenCalledWith(
        'test-library',
        'daft punk',
        1,
        5,
        undefined,
        { artist: null, album: null },
        null
      )
    })

    it('forwards expectedTracks and flags rows whose track count matches', async () => {
      const user = userEvent.setup()
      render(<ManualCandidateDialog {...defaultProps} expectedTracks={14} />)

      await user.type(screen.getByLabelText('Search term'), 'daft punk')
      await user.click(screen.getByRole('button', { name: /search/i }))

      await waitFor(() => expect(screen.getByText('Discovery')).toBeInTheDocument())
      // The local track count is forwarded to the API as the 7th argument.
      expect(mockedSearch).toHaveBeenCalledWith(
        'test-library',
        'daft punk',
        1,
        5,
        undefined,
        { artist: null, album: null },
        14
      )
      // Discovery has 14 tracks (== expected) and is flagged; Homework (16) is not.
      const flags = screen.getAllByTitle('Track count matches the local folder')
      expect(flags).toHaveLength(1)
    })

    it('shows a greyed-out badge for unavailable providers', async () => {
      const user = userEvent.setup()
      render(<ManualCandidateDialog {...defaultProps} />)

      await user.type(screen.getByLabelText('Search term'), 'daft punk')
      await user.click(screen.getByRole('button', { name: /search/i }))

      await waitFor(() => expect(screen.getByText('Discovery')).toBeInTheDocument())
      // Discogs is unavailable → rendered as a greyed badge
      const discogsBadge = screen.getByText('Discogs')
      expect(discogsBadge).toBeInTheDocument()
      expect(discogsBadge.className).toContain('opacity-50')
    })

    it('calls onSubmit with the external URL when a result is used', async () => {
      const user = userEvent.setup()
      const onSubmit = vi.fn()
      render(<ManualCandidateDialog {...defaultProps} onSubmit={onSubmit} />)

      await user.type(screen.getByLabelText('Search term'), 'daft punk')
      await user.click(screen.getByRole('button', { name: /search/i }))

      await waitFor(() => expect(screen.getByText('Discovery')).toBeInTheDocument())
      const useButtons = screen.getAllByRole('button', { name: 'Use' })
      await user.click(useButtons[0])

      expect(onSubmit).toHaveBeenCalledWith('https://musicbrainz.org/release/mb1')
    })

    it('shows a per-provider Load more control when a provider has more results', async () => {
      const user = userEvent.setup()
      render(<ManualCandidateDialog {...defaultProps} />)

      await user.type(screen.getByLabelText('Search term'), 'daft punk')
      await user.click(screen.getByRole('button', { name: /search/i }))

      // Only MusicBrainz has hasMore in the fixture → exactly one button, named after it.
      await waitFor(() =>
        expect(
          screen.getByRole('button', { name: /load more from musicbrainz/i })
        ).toBeInTheDocument()
      )
      expect(screen.getAllByRole('button', { name: /load more/i })).toHaveLength(1)
    })

    it('appends the next page for one provider on Load more, deduped by sourceId', async () => {
      const user = userEvent.setup()
      // Page 1: one MB hit, hasMore. Page 2 (MB only — filtered request):
      // a duplicate (mb1) + a new hit (mb2).
      mockedSearch
        .mockResolvedValueOnce(makeResponse())
        .mockResolvedValueOnce(
          makeResponse({
            page: 2,
            providers: [
              {
                provider: 'musicbrainz',
                available: true,
                reason: null,
                hasMore: false,
                results: [
                  {
                    provider: 'musicbrainz',
                    sourceId: 'mb1', // duplicate of page 1 — must not be re-added
                    title: 'Discovery',
                    artist: 'Daft Punk',
                    year: 2001,
                    trackCount: 14,
                    externalUrl: 'https://musicbrainz.org/release/mb1',
                    coverUrl: null,
                  },
                  {
                    provider: 'musicbrainz',
                    sourceId: 'mb2',
                    title: 'Reflections',
                    artist: 'Daft Punk',
                    year: 2003,
                    trackCount: 12,
                    externalUrl: 'https://musicbrainz.org/release/mb2',
                    coverUrl: null,
                  },
                ],
              },
            ],
          })
        )

      render(<ManualCandidateDialog {...defaultProps} />)
      await user.type(screen.getByLabelText('Search term'), 'daft punk')
      await user.click(screen.getByRole('button', { name: /search/i }))
      await waitFor(() => expect(screen.getByText('Discovery')).toBeInTheDocument())

      await user.click(screen.getByRole('button', { name: /load more from musicbrainz/i }))

      await waitFor(() => expect(screen.getByText('Reflections')).toBeInTheDocument())
      // Load more fetches ONLY the clicked provider's next page.
      expect(mockedSearch).toHaveBeenLastCalledWith(
        'test-library',
        'daft punk',
        2,
        5,
        ['musicbrainz'],
        { artist: null, album: null },
        null
      )
      // Duplicate sourceId must appear only once
      expect(screen.getAllByText('Discovery')).toHaveLength(1)
      // Groups absent from the partial response are kept (Deezer from page 1)
      expect(screen.getByText('Homework')).toBeInTheDocument()
    })

    it('paginates the submitted query even after the input is edited', async () => {
      const user = userEvent.setup()
      render(<ManualCandidateDialog {...defaultProps} />)

      await user.type(screen.getByLabelText('Search term'), 'daft punk')
      await user.click(screen.getByRole('button', { name: /search/i }))
      await waitFor(() => expect(screen.getByText('Discovery')).toBeInTheDocument())

      // Edit the input WITHOUT re-submitting, then click Load more.
      await user.clear(screen.getByLabelText('Search term'))
      await user.type(screen.getByLabelText('Search term'), 'something else')
      await user.click(screen.getByRole('button', { name: /load more from musicbrainz/i }))

      // Load more must paginate the SUBMITTED term, not the live input value.
      expect(mockedSearch).toHaveBeenLastCalledWith(
        'test-library',
        'daft punk',
        2,
        5,
        ['musicbrainz'],
        { artist: null, album: null },
        null
      )
    })

    it('filters results to the selected source and back to All', async () => {
      const user = userEvent.setup()
      render(<ManualCandidateDialog {...defaultProps} />)

      await user.type(screen.getByLabelText('Search term'), 'daft punk')
      await user.click(screen.getByRole('button', { name: /search/i }))
      await waitFor(() => expect(screen.getByText('Discovery')).toBeInTheDocument())

      const filter = screen.getByRole('group', { name: /filter by source/i })
      expect(filter).toBeInTheDocument()

      // Filter to Deezer → MB results hidden, Deezer results shown (no refetch).
      const callsBefore = mockedSearch.mock.calls.length
      await user.click(screen.getByRole('button', { name: /deezer \(1\)/i }))
      expect(screen.queryByText('Discovery')).not.toBeInTheDocument()
      expect(screen.getByText('Homework')).toBeInTheDocument()
      expect(mockedSearch.mock.calls).toHaveLength(callsBefore)

      // Back to All → both groups visible again.
      await user.click(screen.getByRole('button', { name: 'All' }))
      expect(screen.getByText('Discovery')).toBeInTheDocument()
      expect(screen.getByText('Homework')).toBeInTheDocument()
    })

    it('keeps the source filter across a new search', async () => {
      const user = userEvent.setup()
      render(<ManualCandidateDialog {...defaultProps} />)

      await user.type(screen.getByLabelText('Search term'), 'daft punk')
      await user.click(screen.getByRole('button', { name: /search/i }))
      await waitFor(() => expect(screen.getByText('Discovery')).toBeInTheDocument())

      await user.click(screen.getByRole('button', { name: /deezer \(1\)/i }))
      expect(screen.queryByText('Discovery')).not.toBeInTheDocument()

      // Re-submit a search — the Deezer filter must persist (issue #51 Q1).
      await user.clear(screen.getByLabelText('Search term'))
      await user.type(screen.getByLabelText('Search term'), 'justice')
      await user.click(screen.getByRole('button', { name: /^search$/i }))

      await waitFor(() => expect(screen.getByText('Homework')).toBeInTheDocument())
      expect(screen.queryByText('Discovery')).not.toBeInTheDocument()
    })

    it('renders an empty state when no provider returns results', async () => {
      const user = userEvent.setup()
      mockedSearch.mockResolvedValue(
        makeResponse({
          providers: [
            { provider: 'musicbrainz', available: true, reason: null, hasMore: false, results: [] },
            { provider: 'spotify', available: true, reason: null, hasMore: false, results: [] },
            { provider: 'deezer', available: true, reason: null, hasMore: false, results: [] },
            { provider: 'discogs', available: true, reason: null, hasMore: false, results: [] },
          ],
        })
      )
      render(<ManualCandidateDialog {...defaultProps} />)

      await user.type(screen.getByLabelText('Search term'), 'zzzz')
      await user.click(screen.getByRole('button', { name: /search/i }))

      await waitFor(() => expect(screen.getByText(/no results found/i)).toBeInTheDocument())
    })
  })

  describe('Result caching across close/reopen (issue #53)', () => {
    it('shows the previous results immediately when reopened for the same album', async () => {
      const user = userEvent.setup()
      const { rerender } = render(
        <ManualCandidateDialog {...defaultProps} albumKey="/music/album-a" />
      )

      await user.type(screen.getByLabelText('Search term'), 'daft punk')
      await user.click(screen.getByRole('button', { name: /search/i }))
      await waitFor(() => expect(screen.getByText('Discovery')).toBeInTheDocument())
      const callsAfterSearch = mockedSearch.mock.calls.length

      // Close and reopen — same album.
      rerender(
        <ManualCandidateDialog {...defaultProps} open={false} albumKey="/music/album-a" />
      )
      expect(screen.queryByText('Discovery')).not.toBeInTheDocument()
      rerender(<ManualCandidateDialog {...defaultProps} albumKey="/music/album-a" />)

      // Results and query are restored without refetching.
      expect(screen.getByText('Discovery')).toBeInTheDocument()
      expect(screen.getByText('Homework')).toBeInTheDocument()
      expect(screen.getByLabelText('Search term')).toHaveValue('daft punk')
      expect(mockedSearch.mock.calls).toHaveLength(callsAfterSearch)
    })

    it('keeps the source filter when reopened for the same album', async () => {
      const user = userEvent.setup()
      const { rerender } = render(
        <ManualCandidateDialog {...defaultProps} albumKey="/music/album-a" />
      )

      await user.type(screen.getByLabelText('Search term'), 'daft punk')
      await user.click(screen.getByRole('button', { name: /search/i }))
      await waitFor(() => expect(screen.getByText('Discovery')).toBeInTheDocument())
      await user.click(screen.getByRole('button', { name: /deezer \(1\)/i }))
      expect(screen.queryByText('Discovery')).not.toBeInTheDocument()

      rerender(
        <ManualCandidateDialog {...defaultProps} open={false} albumKey="/music/album-a" />
      )
      rerender(<ManualCandidateDialog {...defaultProps} albumKey="/music/album-a" />)

      // Deezer filter still active: its result visible, MusicBrainz's hidden.
      expect(screen.getByText('Homework')).toBeInTheDocument()
      expect(screen.queryByText('Discovery')).not.toBeInTheDocument()
    })

    it('drops cached results when reopened for a different album', async () => {
      const user = userEvent.setup()
      const { rerender } = render(
        <ManualCandidateDialog {...defaultProps} albumKey="/music/album-a" />
      )

      await user.type(screen.getByLabelText('Search term'), 'daft punk')
      await user.click(screen.getByRole('button', { name: /search/i }))
      await waitFor(() => expect(screen.getByText('Discovery')).toBeInTheDocument())

      rerender(
        <ManualCandidateDialog {...defaultProps} open={false} albumKey="/music/album-a" />
      )
      rerender(<ManualCandidateDialog {...defaultProps} albumKey="/music/album-b" />)

      expect(screen.queryByText('Discovery')).not.toBeInTheDocument()
      expect(screen.getByLabelText('Search term')).toHaveValue('')
    })

    it('discards an in-flight response that arrives after the album changed', async () => {
      const user = userEvent.setup()
      // A search the test resolves manually, after the album has switched.
      let resolveSearch!: (value: SearchCandidatesResponse) => void
      mockedSearch.mockImplementationOnce(
        () => new Promise((resolve) => (resolveSearch = resolve))
      )
      const { rerender } = render(
        <ManualCandidateDialog {...defaultProps} albumKey="/music/album-a" />
      )

      await user.type(screen.getByLabelText('Search term'), 'daft punk')
      await user.click(screen.getByRole('button', { name: /search/i }))

      // Close mid-flight, switch albums, reopen, THEN let the response land.
      rerender(
        <ManualCandidateDialog {...defaultProps} open={false} albumKey="/music/album-a" />
      )
      rerender(<ManualCandidateDialog {...defaultProps} albumKey="/music/album-b" />)
      resolveSearch(makeResponse())
      // Flush the resolved promise's state updates before asserting.
      await act(async () => {})

      // Album A's results must not appear in album B's cache.
      expect(screen.queryByText('Discovery')).not.toBeInTheDocument()
    })
  })

  describe('Pre-populated search query (issue #59)', () => {
    it('seeds the search field with initialQuery on open', () => {
      render(<ManualCandidateDialog {...defaultProps} initialQuery="Daft Punk - Discovery" />)

      expect(screen.getByLabelText('Search term')).toHaveValue('Daft Punk - Discovery')
    })

    it('re-seeds the field when the album changes', () => {
      const { rerender } = render(
        <ManualCandidateDialog
          {...defaultProps}
          albumKey="/music/album-a"
          initialQuery="Artist A - Album A"
        />
      )
      expect(screen.getByLabelText('Search term')).toHaveValue('Artist A - Album A')

      rerender(
        <ManualCandidateDialog
          {...defaultProps}
          albumKey="/music/album-b"
          initialQuery="Artist B - Album B"
        />
      )
      expect(screen.getByLabelText('Search term')).toHaveValue('Artist B - Album B')
    })

    it('keeps the user edits over the seed when reopened for the same album', async () => {
      const user = userEvent.setup()
      const { rerender } = render(
        <ManualCandidateDialog
          {...defaultProps}
          albumKey="/music/album-a"
          initialQuery="Artist A - Album A"
        />
      )

      const input = screen.getByLabelText('Search term')
      await user.clear(input)
      await user.type(input, 'my own search')

      // Close and reopen for the SAME album — the seed must not clobber the edit.
      rerender(
        <ManualCandidateDialog
          {...defaultProps}
          open={false}
          albumKey="/music/album-a"
          initialQuery="Artist A - Album A"
        />
      )
      rerender(
        <ManualCandidateDialog
          {...defaultProps}
          albumKey="/music/album-a"
          initialQuery="Artist A - Album A"
        />
      )

      expect(screen.getByLabelText('Search term')).toHaveValue('my own search')
    })
  })

  describe('Structured search query (issue #69)', () => {
    it('sends seeded artist/album as structured terms on the first search', async () => {
      const user = userEvent.setup()
      render(
        <ManualCandidateDialog
          {...defaultProps}
          initialQuery="Daft Punk - Discovery"
          initialArtist="Daft Punk"
          initialAlbum="Discovery"
        />
      )

      await user.click(screen.getByRole('button', { name: /search/i }))

      await waitFor(() =>
        expect(mockedSearch).toHaveBeenCalledWith(
          'test-library',
          'Daft Punk - Discovery',
          1,
          5,
          undefined,
          { artist: 'Daft Punk', album: 'Discovery' },
          null
        )
      )
    })

    it('drops the structured terms once the user edits the search box', async () => {
      const user = userEvent.setup()
      render(
        <ManualCandidateDialog
          {...defaultProps}
          initialQuery="Daft Punk - Discovery"
          initialArtist="Daft Punk"
          initialAlbum="Discovery"
        />
      )

      const input = screen.getByLabelText('Search term')
      await user.clear(input)
      await user.type(input, 'something else')
      await user.click(screen.getByRole('button', { name: /search/i }))

      // A hand-typed term is free text — no structured fields.
      await waitFor(() =>
        expect(mockedSearch).toHaveBeenCalledWith(
          'test-library',
          'something else',
          1,
          5,
          undefined,
          { artist: null, album: null },
          null
        )
      )
    })

    it('paginates with the structured terms that produced the results', async () => {
      const user = userEvent.setup()
      render(
        <ManualCandidateDialog
          {...defaultProps}
          initialQuery="Daft Punk - Discovery"
          initialArtist="Daft Punk"
          initialAlbum="Discovery"
        />
      )

      await user.click(screen.getByRole('button', { name: /search/i }))
      await waitFor(() => expect(screen.getByText('Discovery')).toBeInTheDocument())
      await user.click(screen.getByRole('button', { name: /load more from musicbrainz/i }))

      await waitFor(() =>
        expect(mockedSearch).toHaveBeenLastCalledWith(
          'test-library',
          'Daft Punk - Discovery',
          2,
          5,
          ['musicbrainz'],
          { artist: 'Daft Punk', album: 'Discovery' },
          null
        )
      )
    })
  })

  describe('Link validation', () => {
    it('should show detected provider for valid Spotify link', async () => {
      const user = userEvent.setup()
      render(<ManualCandidateDialog {...defaultProps} />)
      const input = await gotoLinkTab(user)
      await user.type(input, 'https://open.spotify.com/album/4LH4d3cOWNNsVw41Gqt2kv')

      expect(screen.getByText('Detected: Spotify')).toBeInTheDocument()
    })

    it('should show detected provider for valid Deezer link', async () => {
      const user = userEvent.setup()
      render(<ManualCandidateDialog {...defaultProps} />)
      const input = await gotoLinkTab(user)
      await user.type(input, 'https://www.deezer.com/album/12345')

      expect(screen.getByText('Detected: Deezer')).toBeInTheDocument()
    })

    it('should show detected provider for valid MusicBrainz UUID', async () => {
      const user = userEvent.setup()
      render(<ManualCandidateDialog {...defaultProps} />)
      const input = await gotoLinkTab(user)
      await user.type(input, 'a1b2c3d4-e5f6-7890-abcd-ef1234567890')

      expect(screen.getByText('Detected: MusicBrainz')).toBeInTheDocument()
    })

    it('should not show detected provider for invalid link', async () => {
      const user = userEvent.setup()
      render(<ManualCandidateDialog {...defaultProps} />)
      const input = await gotoLinkTab(user)
      await user.type(input, 'https://invalid-site.com/album/123')

      expect(screen.queryByText(/Detected:/)).not.toBeInTheDocument()
    })

    it('should disable submit button for invalid link', async () => {
      const user = userEvent.setup()
      render(<ManualCandidateDialog {...defaultProps} />)
      const input = await gotoLinkTab(user)
      await user.type(input, 'invalid-link')

      expect(screen.getByRole('button', { name: 'Add Candidate' })).toBeDisabled()
    })

    it('should enable submit button for valid input', async () => {
      const user = userEvent.setup()
      render(<ManualCandidateDialog {...defaultProps} />)
      const input = await gotoLinkTab(user)
      await user.type(input, 'https://open.spotify.com/album/abc123')

      expect(screen.getByRole('button', { name: 'Add Candidate' })).not.toBeDisabled()
    })
  })

  describe('Link submission', () => {
    it('should call onSubmit with trimmed link when valid', async () => {
      const user = userEvent.setup()
      const onSubmit = vi.fn()
      render(<ManualCandidateDialog {...defaultProps} onSubmit={onSubmit} />)
      const input = await gotoLinkTab(user)
      await user.type(input, '  https://open.spotify.com/album/abc123  ')

      await user.click(screen.getByRole('button', { name: 'Add Candidate' }))

      expect(onSubmit).toHaveBeenCalledWith('https://open.spotify.com/album/abc123')
    })

    it('should not call onSubmit when link is invalid', async () => {
      const user = userEvent.setup()
      const onSubmit = vi.fn()
      render(<ManualCandidateDialog {...defaultProps} onSubmit={onSubmit} />)
      const input = await gotoLinkTab(user)
      await user.type(input, 'invalid-link')

      await user.click(screen.getByRole('button', { name: 'Add Candidate' }))

      expect(onSubmit).not.toHaveBeenCalled()
    })
  })

  describe('Loading state (link tab)', () => {
    it('should show loading spinner and disable input when isLoading', async () => {
      const user = userEvent.setup()
      render(<ManualCandidateDialog {...defaultProps} isLoading />)
      await user.click(screen.getByRole('tab', { name: /paste link/i }))

      expect(screen.getByText('Resolving...')).toBeInTheDocument()
      expect(screen.getByLabelText('Link or MusicBrainz ID')).toBeDisabled()
    })
  })

  describe('Error state', () => {
    it('should display error message on the search tab', () => {
      render(<ManualCandidateDialog {...defaultProps} error="Release not found on Spotify" />)

      expect(screen.getByText('Release not found on Spotify')).toBeInTheDocument()
    })

    it('should display error message on the link tab', async () => {
      const user = userEvent.setup()
      render(<ManualCandidateDialog {...defaultProps} error="Plugin not available" />)
      await user.click(screen.getByRole('tab', { name: /paste link/i }))

      expect(screen.getByText('Plugin not available')).toBeInTheDocument()
    })
  })
})
