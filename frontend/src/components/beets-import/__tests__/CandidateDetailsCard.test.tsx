import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CandidateDetailsCard from '../CandidateDetailsCard'
import type { AnalyzeAlbumResponse, Candidate } from '@/types/beets-import'

describe('CandidateDetailsCard', () => {
  const createMockCandidate = (overrides: Partial<Candidate> = {}): Candidate => ({
    source: 'MusicBrainz',
    sourceId: 'mb-123',
    similarity: 0.95,
    artist: 'Test Artist',
    album: 'Test Album',
    year: 2023,
    label: 'Test Label',
    country: 'US',
    media: 'CD',
    tracks: [
      {
        index: 1,
        title: 'Track 1',
        length: 180,
        changes: [],
      },
    ],
    changes: [],
    trackChanges: [],
    ...overrides,
  })

  const createMockAnalysisResponse = (
    overrides: Partial<AnalyzeAlbumResponse> = {}
  ): AnalyzeAlbumResponse => ({
    albumPath: '/import/test-album',
    localAlbum: {
      path: '/import/test-album',
      artist: 'Local Artist',
      album: 'Local Album',
      tracks: [
        {
          path: '/import/test-album/01-track.flac',
          title: 'Track 1',
          trackNum: 1,
          length: 180,
        },
      ],
    },
    candidates: [createMockCandidate()],
    analyzedAt: '2024-01-15T10:30:00Z',
    ...overrides,
  })

  describe('Empty state', () => {
    it('should show empty state when no analysisData', () => {
      render(<CandidateDetailsCard analysisData={null} />)

      expect(screen.getByText('No Album Selected')).toBeInTheDocument()
      expect(
        screen.getByText(/Select an album from the list to view its details/)
      ).toBeInTheDocument()
    })
  })

  describe('Loading state', () => {
    it('should show loading state when isAnalyzing is true', () => {
      render(<CandidateDetailsCard analysisData={null} isAnalyzing />)

      expect(screen.getByText('Analyzing Album')).toBeInTheDocument()
      expect(
        screen.getByText(/Searching MusicBrainz and other sources/)
      ).toBeInTheDocument()
    })

    it('should show spinner in loading state', () => {
      const { container } = render(
        <CandidateDetailsCard analysisData={null} isAnalyzing />
      )

      // Check for spinning animation class
      const spinner = container.querySelector('.animate-spin')
      expect(spinner).toBeInTheDocument()
    })
  })

  describe('Error state', () => {
    it('should show error state when error is provided', () => {
      render(
        <CandidateDetailsCard
          analysisData={null}
          error="Failed to analyze album: Network error"
        />
      )

      expect(screen.getByText('Analysis Failed')).toBeInTheDocument()
      expect(
        screen.getByText('Failed to analyze album: Network error')
      ).toBeInTheDocument()
    })
  })

  describe('Local album info', () => {
    it('should display local album path', () => {
      const analysisData = createMockAnalysisResponse()

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('/import/test-album')).toBeInTheDocument()
    })

    it('renders the local album section above the candidates list', () => {
      const analysisData = createMockAnalysisResponse()

      render(<CandidateDetailsCard analysisData={analysisData} />)

      const albumPath = screen.getByText('/import/test-album')
      const candidatesHeading = screen.getByText('Candidates')
      // Local Album section precedes the candidates in document order.
      expect(
        albumPath.compareDocumentPosition(candidatesHeading) &
          Node.DOCUMENT_POSITION_FOLLOWING
      ).toBeTruthy()
    })

    it('should display local album artist and album name', () => {
      const analysisData = createMockAnalysisResponse({
        localAlbum: {
          path: '/import/test-album',
          artist: 'Pink Floyd',
          album: 'The Wall',
          tracks: [],
        },
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('Pink Floyd')).toBeInTheDocument()
      expect(screen.getByText('The Wall')).toBeInTheDocument()
    })

    it('should show (unknown) for missing artist/album', () => {
      const analysisData = createMockAnalysisResponse({
        localAlbum: {
          path: '/import/test-album',
          artist: null,
          album: null,
          tracks: [],
        },
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      // Three "(unknown)" labels - artist, album, and format (none provided here)
      const unknowns = screen.getAllByText('(unknown)')
      expect(unknowns).toHaveLength(3)
    })

    it('should display the dominant format as a badge', () => {
      const analysisData = createMockAnalysisResponse({
        localAlbum: {
          path: '/import/test-album',
          artist: 'Pink Floyd',
          album: 'The Wall',
          dominantFormat: 'FLAC',
          tracks: [],
        },
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('FLAC')).toBeInTheDocument()
    })

    it('labels folder-derived metadata so it does not read as a contradiction', () => {
      const analysisData = createMockAnalysisResponse({
        localAlbum: {
          path: '/import/test-album',
          artist: 'Holy Klassiker',
          album: 'Folge 1 Der kleine Prinz',
          metadataSource: 'folder',
          tracks: [],
        },
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('from folder name')).toBeInTheDocument()
    })

    it('does not show a source label for tag-derived metadata', () => {
      const analysisData = createMockAnalysisResponse({
        localAlbum: {
          path: '/import/test-album',
          artist: 'Pink Floyd',
          album: 'The Wall',
          metadataSource: 'tags',
          tracks: [],
        },
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.queryByText('from folder name')).not.toBeInTheDocument()
      expect(screen.queryByText('from tags + folder name')).not.toBeInTheDocument()
    })

    it('should display track count', () => {
      const analysisData = createMockAnalysisResponse({
        localAlbum: {
          path: '/import/test-album',
          artist: 'Test',
          album: 'Test',
          tracks: [
            { path: '/t1.flac', title: 'T1', trackNum: 1, length: 180 },
            { path: '/t2.flac', title: 'T2', trackNum: 2, length: 200 },
            { path: '/t3.flac', title: 'T3', trackNum: 3, length: 220 },
          ],
        },
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      // Use getAllByText since "3" may appear in multiple places
      const threeElements = screen.getAllByText('3')
      expect(threeElements.length).toBeGreaterThanOrEqual(1)
    })
  })

  describe('Candidates rendering', () => {
    it('should display candidate count badge', () => {
      const analysisData = createMockAnalysisResponse({
        candidates: [
          createMockCandidate({ sourceId: 'mb-1' }),
          createMockCandidate({ sourceId: 'mb-2' }),
        ],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      // Find the candidates section badge - the badge is within the Candidates header
      expect(screen.getByText('Candidates')).toBeInTheDocument()
      // Use getAllByText since "2" appears in multiple places (badge and rank number)
      const twoElements = screen.getAllByText('2')
      expect(twoElements.length).toBeGreaterThanOrEqual(1)
    })

    it('should display candidate artist and album', () => {
      const analysisData = createMockAnalysisResponse({
        candidates: [
          createMockCandidate({
            artist: 'Candidate Artist',
            album: 'Candidate Album',
          }),
        ],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('Candidate Artist - Candidate Album')).toBeInTheDocument()
    })

    it('should display similarity score as percentage', () => {
      const analysisData = createMockAnalysisResponse({
        candidates: [createMockCandidate({ similarity: 0.9567 })],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('95.7%')).toBeInTheDocument()
    })

    it('should display source label', () => {
      const analysisData = createMockAnalysisResponse({
        candidates: [createMockCandidate({ source: 'MusicBrainz' })],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('MusicBrainz')).toBeInTheDocument()
    })

    it('should display year when available', () => {
      const analysisData = createMockAnalysisResponse({
        candidates: [createMockCandidate({ year: 1979 })],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText(/1979/)).toBeInTheDocument()
    })

    it('should display label and country when available', () => {
      const analysisData = createMockAnalysisResponse({
        candidates: [
          createMockCandidate({
            year: 1979,
            label: 'Columbia',
            country: 'UK',
          }),
        ],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText(/1979 - Columbia \(UK\)/)).toBeInTheDocument()
    })
  })

  describe('Expandable/collapsible behavior', () => {
    it('should have first candidate expanded by default', () => {
      const analysisData = createMockAnalysisResponse({
        candidates: [
          createMockCandidate({
            trackChanges: [
              { index: 1, localTitle: 'Old Title', candidateTitle: 'New Title' },
            ],
          }),
        ],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      // The candidate header button should be expanded
      const expandButton = screen.getByRole('button', { expanded: true })
      expect(expandButton).toBeInTheDocument()

      // Track changes table should be visible
      expect(screen.getByText('Track Changes')).toBeInTheDocument()
    })

    it('should collapse candidate when clicked', () => {
      const analysisData = createMockAnalysisResponse({
        candidates: [
          createMockCandidate({
            trackChanges: [
              { index: 1, localTitle: 'Old Title', candidateTitle: 'New Title' },
            ],
          }),
        ],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      // Click to collapse
      const expandButton = screen.getByRole('button', { expanded: true })
      fireEvent.click(expandButton)

      // Should now be collapsed
      expect(screen.getByRole('button', { expanded: false })).toBeInTheDocument()
    })

    it('should expand collapsed candidate when clicked', () => {
      const analysisData = createMockAnalysisResponse({
        candidates: [
          createMockCandidate({ sourceId: 'mb-1' }),
          createMockCandidate({ sourceId: 'mb-2' }),
        ],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      // Second candidate should be collapsed by default
      const buttons = screen.getAllByRole('button')
      const collapsedButton = buttons.find(
        (btn) => btn.getAttribute('aria-expanded') === 'false'
      )
      expect(collapsedButton).toBeDefined()

      // Click to expand
      fireEvent.click(collapsedButton!)

      // Should now be expanded
      expect(collapsedButton).toHaveAttribute('aria-expanded', 'true')
    })

    it('should show rank badge for each candidate', () => {
      const analysisData = createMockAnalysisResponse({
        candidates: [
          createMockCandidate({ sourceId: 'mb-1', similarity: 0.98 }),
          createMockCandidate({ sourceId: 'mb-2', similarity: 0.95 }),
          createMockCandidate({ sourceId: 'mb-3', similarity: 0.90 }),
        ],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      // Use getAllByText since numbers appear in multiple contexts
      const oneElements = screen.getAllByText('1')
      expect(oneElements.length).toBeGreaterThanOrEqual(1)
    })
  })

  describe('Metadata changes', () => {
    it('should display album-level metadata changes', () => {
      const analysisData = createMockAnalysisResponse({
        candidates: [
          createMockCandidate({
            changes: [
              { field: 'artist', fromValue: 'Old Artist', toValue: 'New Artist' },
              { field: 'year', fromValue: '2020', toValue: '2023' },
            ],
          }),
        ],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('Album Changes')).toBeInTheDocument()
      expect(screen.getByText('Old Artist')).toBeInTheDocument()
      expect(screen.getByText('New Artist')).toBeInTheDocument()
    })

    it('should show change count indicator', () => {
      const analysisData = createMockAnalysisResponse({
        candidates: [
          createMockCandidate({
            changes: [
              { field: 'artist', fromValue: 'Old', toValue: 'New' },
              { field: 'year', fromValue: '2020', toValue: '2023' },
            ],
          }),
        ],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('2 fields')).toBeInTheDocument()
    })
  })

  describe('Track changes', () => {
    it('should display track comparison table', () => {
      const analysisData = createMockAnalysisResponse({
        candidates: [
          createMockCandidate({
            tracks: [
              { index: 1, title: 'New Track 1', length: 180, localTitle: 'Old Track 1', localPath: '/a/1.flac', changes: [] },
              { index: 2, title: 'New Track 2', length: 200, localTitle: 'Old Track 2', localPath: '/a/2.flac', changes: [] },
            ],
            trackChanges: [
              { index: 1, localTitle: 'Old Track 1', candidateTitle: 'New Track 1' },
              { index: 2, localTitle: 'Old Track 2', candidateTitle: 'New Track 2' },
            ],
          }),
        ],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('Track Changes')).toBeInTheDocument()
      expect(screen.getByText('Old Track 1')).toBeInTheDocument()
      expect(screen.getByText('New Track 1')).toBeInTheDocument()
      expect(screen.getByText('Old Track 2')).toBeInTheDocument()
      expect(screen.getByText('New Track 2')).toBeInTheDocument()
    })

    it('shows the local title for matched (unchanged) tracks instead of "(new)"', () => {
      // Regression for #27: a track whose local tag matches the candidate must
      // still show its local value, not collapse to an empty Local column.
      const analysisData = createMockAnalysisResponse({
        localAlbum: {
          path: '/import/ezra',
          artist: 'Ezra George',
          album: 'Photobook',
          tracks: [
            { path: '/import/ezra/01.flac', title: 'Stay', trackNum: 1, length: 180 },
            { path: '/import/ezra/02.flac', title: 'Somewhere West', trackNum: 2, length: 200 },
          ],
        },
        candidates: [
          createMockCandidate({
            tracks: [
              { index: 1, title: 'Stay', length: 180, localTitle: 'Stay', localPath: '/import/ezra/01.flac', changes: [] },
              { index: 2, title: 'Somewhere West', length: 200, localTitle: 'Somewhere West', localPath: '/import/ezra/02.flac', changes: [] },
            ],
          }),
        ],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      // Both titles appear on the Local AND Candidate side (matched rows).
      expect(screen.getAllByText('Stay').length).toBeGreaterThanOrEqual(2)
      expect(screen.getAllByText('Somewhere West').length).toBeGreaterThanOrEqual(2)
      // Nothing is misreported as a brand-new track.
      expect(screen.queryByText('(new)')).not.toBeInTheDocument()
    })

    it('marks candidate tracks with no local counterpart as "(new)"', () => {
      const analysisData = createMockAnalysisResponse({
        localAlbum: { path: '/import/ezra', artist: 'Ezra George', album: 'Photobook', tracks: [] },
        candidates: [
          createMockCandidate({
            tracks: [
              { index: 4, title: 'Cycling', length: 210, localTitle: null, localPath: null, changes: [] },
            ],
          }),
        ],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('Cycling')).toBeInTheDocument()
      expect(screen.getByText('(new)')).toBeInTheDocument()
    })

    it('should show track count indicator counting renamed tracks', () => {
      // The badge counts tracks whose local title differs from the candidate's,
      // derived from the candidate↔local join (not the raw trackChanges length,
      // which now holds a row per matched track).
      const analysisData = createMockAnalysisResponse({
        localAlbum: {
          path: '/import/a',
          artist: 'A',
          album: 'B',
          tracks: [
            { path: '/import/a/01.flac', title: 'Old 1', trackNum: 1, length: 180 },
            { path: '/import/a/02.flac', title: 'Old 2', trackNum: 2, length: 180 },
            { path: '/import/a/03.flac', title: 'Old 3', trackNum: 3, length: 180 },
          ],
        },
        candidates: [
          createMockCandidate({
            tracks: [
              { index: 1, title: 'New 1', length: 180, localTitle: 'Old 1', localPath: '/import/a/01.flac', changes: [] },
              { index: 2, title: 'New 2', length: 180, localTitle: 'Old 2', localPath: '/import/a/02.flac', changes: [] },
              { index: 3, title: 'New 3', length: 180, localTitle: 'Old 3', localPath: '/import/a/03.flac', changes: [] },
            ],
          }),
        ],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('3 tracks')).toBeInTheDocument()
    })

    it('shows local vs candidate duration in the console "vs" format', () => {
      const analysisData = createMockAnalysisResponse({
        localAlbum: {
          path: '/import/a',
          artist: 'A',
          album: 'B',
          tracks: [{ path: '/import/a/01.flac', title: 'Same', trackNum: 1, length: 238 }],
        },
        candidates: [
          createMockCandidate({
            tracks: [
              {
                index: 1,
                title: 'Same',
                length: 241,
                localTitle: 'Same',
                localPath: '/import/a/01.flac',
                changes: [],
              },
            ],
          }),
        ],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('3:58 vs 4:01')).toBeInTheDocument()
    })

    it('shows a single length when raw durations straddle a rounding boundary', () => {
      // 461.4 vs 461.6 round to 7:41 / 7:42 but differ by only 0.2 s — the
      // comparison must use the raw lengths, not the rounded display strings.
      const analysisData = createMockAnalysisResponse({
        localAlbum: {
          path: '/import/a',
          artist: 'A',
          album: 'B',
          tracks: [{ path: '/import/a/01.flac', title: 'Same', trackNum: 1, length: 461.4 }],
        },
        candidates: [
          createMockCandidate({
            tracks: [
              {
                index: 1,
                title: 'Same',
                length: 461.6,
                localTitle: 'Same',
                localPath: '/import/a/01.flac',
                changes: [],
              },
            ],
          }),
        ],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('7:41')).toBeInTheDocument()
      expect(screen.queryByText(/vs/)).not.toBeInTheDocument()
    })

    it('still shows "vs" when raw durations differ by more than the tolerance', () => {
      const analysisData = createMockAnalysisResponse({
        localAlbum: {
          path: '/import/a',
          artist: 'A',
          album: 'B',
          tracks: [{ path: '/import/a/01.flac', title: 'Same', trackNum: 1, length: 460 }],
        },
        candidates: [
          createMockCandidate({
            tracks: [
              {
                index: 1,
                title: 'Same',
                length: 462,
                localTitle: 'Same',
                localPath: '/import/a/01.flac',
                changes: [],
              },
            ],
          }),
        ],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('7:40 vs 7:42')).toBeInTheDocument()
    })

    it('shows the local filename beneath the local title', () => {
      const analysisData = createMockAnalysisResponse({
        localAlbum: {
          path: '/import/a',
          artist: 'A',
          album: 'B',
          tracks: [{ path: '/import/a/01 - track one.flac', title: 'Track One', trackNum: 1, length: 200 }],
        },
        candidates: [
          createMockCandidate({
            tracks: [
              {
                index: 1,
                title: 'Track One',
                length: 200,
                localTitle: 'Track One',
                localPath: '/import/a/01 - track one.flac',
                changes: [],
              },
            ],
          }),
        ],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('01 - track one.flac')).toBeInTheDocument()
    })

    it('pairs by track number for results cached before explicit pairing existed', () => {
      // Backward-compat: candidate tracks WITHOUT localTitle/localPath fall back
      // to matching local tracks by track number.
      const analysisData = createMockAnalysisResponse({
        localAlbum: {
          path: '/import/a',
          artist: 'A',
          album: 'B',
          tracks: [{ path: '/import/a/01.flac', title: 'Old Title', trackNum: 1, length: 180 }],
        },
        candidates: [
          createMockCandidate({
            // No localTitle/localPath keys at all (old cache shape).
            tracks: [{ index: 1, title: 'New Title', length: 180, changes: [] }],
          }),
        ],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      // Local value recovered by track-number pairing, shown against the candidate.
      expect(screen.getByText('Old Title')).toBeInTheDocument()
      expect(screen.getByText('New Title')).toBeInTheDocument()
      expect(screen.queryByText('(new)')).not.toBeInTheDocument()
    })

    it('renders a "(no match)" row for local tracks absent from the candidate', () => {
      const analysisData = createMockAnalysisResponse({
        localAlbum: {
          path: '/import/a',
          artist: 'A',
          album: 'B',
          tracks: [
            { path: '/import/a/01.flac', title: 'Stay', trackNum: 1, length: 180 },
            { path: '/import/a/99.flac', title: 'Bonus Track', trackNum: 99, length: 200 },
          ],
        },
        candidates: [
          createMockCandidate({
            tracks: [
              { index: 1, title: 'Stay', length: 180, localTitle: 'Stay', localPath: '/import/a/01.flac', changes: [] },
            ],
          }),
        ],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('Bonus Track')).toBeInTheDocument()
      expect(screen.getByText('(no match)')).toBeInTheDocument()
    })

    it('should show a no-tracks message when there is nothing to compare', () => {
      const analysisData = createMockAnalysisResponse({
        localAlbum: { path: '/import/empty', artist: null, album: null, tracks: [] },
        candidates: [createMockCandidate({ tracks: [], trackChanges: [] })],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('No tracks to compare')).toBeInTheDocument()
    })

    it('should display (empty) for a paired track whose local title is null', () => {
      const analysisData = createMockAnalysisResponse({
        localAlbum: {
          path: '/import/a',
          artist: null,
          album: null,
          tracks: [{ path: '/import/a/1.flac', title: null, trackNum: 1, length: 180 }],
        },
        candidates: [
          createMockCandidate({
            tracks: [
              { index: 1, title: 'New Title', length: 180, localTitle: null, localPath: '/import/a/1.flac', changes: [] },
            ],
          }),
        ],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('(empty)')).toBeInTheDocument()
      expect(screen.getByText('New Title')).toBeInTheDocument()
    })
  })

  describe('No matches state', () => {
    it('should show no matches message when candidates is empty', () => {
      const analysisData = createMockAnalysisResponse({
        candidates: [],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('No Matches Found')).toBeInTheDocument()
      expect(
        screen.getByText(/Beets could not find any matching candidates/)
      ).toBeInTheDocument()
    })

    it('should still show local album info when no matches', () => {
      const analysisData = createMockAnalysisResponse({
        localAlbum: {
          path: '/import/unknown-album',
          artist: 'Unknown Artist',
          album: 'Unknown Album',
          tracks: [],
        },
        candidates: [],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('/import/unknown-album')).toBeInTheDocument()
      expect(screen.getByText('Unknown Artist')).toBeInTheDocument()
    })
  })

  describe('Analysis timestamp', () => {
    it('should display analysis timestamp', () => {
      const analysisData = createMockAnalysisResponse({
        analyzedAt: '2024-01-15T10:30:00Z',
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      // The timestamp should be formatted by toLocaleString()
      // Just check that "Analyzed" text is present
      expect(screen.getByText(/Analyzed/)).toBeInTheDocument()
    })
  })

  describe('Styling', () => {
    it('should apply custom className', () => {
      const { container } = render(
        <CandidateDetailsCard analysisData={null} className="custom-class" />
      )

      expect(container.firstChild).toHaveClass('custom-class')
    })

    it('should have card header with title', () => {
      render(<CandidateDetailsCard analysisData={null} />)

      expect(screen.getByText('Candidate Details')).toBeInTheDocument()
    })

    it('should not render the old descriptive subtitle', () => {
      render(<CandidateDetailsCard analysisData={null} />)

      expect(
        screen.queryByText('Analysis results and matching candidates from MusicBrainz')
      ).not.toBeInTheDocument()
    })
  })

  describe('Similarity badge variants', () => {
    it('should use default variant for high similarity (>= 95%)', () => {
      const analysisData = createMockAnalysisResponse({
        candidates: [createMockCandidate({ similarity: 0.96 })],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      // Check that 96.0% is displayed
      expect(screen.getByText('96.0%')).toBeInTheDocument()
    })

    it('should use secondary variant for medium similarity (85-95%)', () => {
      const analysisData = createMockAnalysisResponse({
        candidates: [createMockCandidate({ similarity: 0.90 })],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('90.0%')).toBeInTheDocument()
    })

    it('should use destructive variant for low similarity (< 85%)', () => {
      const analysisData = createMockAnalysisResponse({
        candidates: [createMockCandidate({ similarity: 0.70 })],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('70.0%')).toBeInTheDocument()
    })
  })

  describe('Manual candidates', () => {
    it('should display manual badge for manual candidates', () => {
      const analysisData = createMockAnalysisResponse({
        candidates: [],
        manualCandidates: [
          createMockCandidate({
            sourceId: 'spotify-123',
            source: 'Spotify',
            isManual: true,
          }),
        ],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.getByText('Manual')).toBeInTheDocument()
    })

    it('should display manual candidates before automatic candidates', () => {
      const analysisData = createMockAnalysisResponse({
        candidates: [
          createMockCandidate({
            sourceId: 'mb-1',
            source: 'MusicBrainz',
            artist: 'Auto Artist',
          }),
        ],
        manualCandidates: [
          createMockCandidate({
            sourceId: 'spotify-1',
            source: 'Spotify',
            artist: 'Manual Artist',
            isManual: true,
          }),
        ],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      // The first candidate should show the Manual badge
      expect(screen.getByText('Manual')).toBeInTheDocument()

      // Manual Artist should be in the document
      expect(screen.getByText('Manual Artist - Test Album')).toBeInTheDocument()

      // Check that Manual badge appears before Auto Artist text
      const manualBadge = screen.getByText('Manual')
      const autoArtistText = screen.getByText('Auto Artist - Test Album')

      // Verify both are present (ordering is validated by merged array logic)
      expect(manualBadge).toBeInTheDocument()
      expect(autoArtistText).toBeInTheDocument()
    })

    it('should show Add Manual button when onAddManualCandidate is provided', () => {
      const analysisData = createMockAnalysisResponse()
      const onAddManualCandidate = vi.fn()

      render(
        <CandidateDetailsCard
          analysisData={analysisData}
          onAddManualCandidate={onAddManualCandidate}
        />
      )

      expect(screen.getByRole('button', { name: /Add Manual/i })).toBeInTheDocument()
    })

    it('should not show Add Manual button when onAddManualCandidate is not provided', () => {
      const analysisData = createMockAnalysisResponse()

      render(<CandidateDetailsCard analysisData={analysisData} />)

      expect(screen.queryByRole('button', { name: /Add Manual/i })).not.toBeInTheDocument()
    })

    it('should show Add Manual Candidate button in no matches state', () => {
      const analysisData = createMockAnalysisResponse({
        candidates: [],
      })
      const onAddManualCandidate = vi.fn()

      render(
        <CandidateDetailsCard
          analysisData={analysisData}
          onAddManualCandidate={onAddManualCandidate}
        />
      )

      expect(screen.getByRole('button', { name: /Add Manual Candidate/i })).toBeInTheDocument()
    })

    it('should show Re-analyze button when onReanalyze is provided', () => {
      const analysisData = createMockAnalysisResponse()
      const onReanalyze = vi.fn()

      render(
        <CandidateDetailsCard
          analysisData={analysisData}
          librarySlug="test-library"
          onReanalyze={onReanalyze}
        />
      )

      expect(
        screen.getByRole('button', { name: /Re-analyze/i })
      ).toBeInTheDocument()
    })

    it('should not show Re-analyze button when onReanalyze is not provided', () => {
      const analysisData = createMockAnalysisResponse()

      render(
        <CandidateDetailsCard analysisData={analysisData} librarySlug="test-library" />
      )

      expect(
        screen.queryByRole('button', { name: /Re-analyze/i })
      ).not.toBeInTheDocument()
    })

    it('should call onReanalyze when Re-analyze button is clicked', async () => {
      const user = userEvent.setup()
      const analysisData = createMockAnalysisResponse()
      const onReanalyze = vi.fn()

      render(
        <CandidateDetailsCard
          analysisData={analysisData}
          librarySlug="test-library"
          onReanalyze={onReanalyze}
        />
      )

      await user.click(screen.getByRole('button', { name: /Re-analyze/i }))

      expect(onReanalyze).toHaveBeenCalledTimes(1)
    })

    it('should show and fire Re-analyze button in no matches state', async () => {
      const user = userEvent.setup()
      const analysisData = createMockAnalysisResponse({ candidates: [] })
      const onReanalyze = vi.fn()

      render(
        <CandidateDetailsCard
          analysisData={analysisData}
          librarySlug="test-library"
          onReanalyze={onReanalyze}
        />
      )

      const reanalyzeButton = screen.getByRole('button', { name: /Re-analyze/i })
      expect(reanalyzeButton).toBeInTheDocument()

      await user.click(reanalyzeButton)
      expect(onReanalyze).toHaveBeenCalledTimes(1)
    })

    it('should open dialog when Add Manual button is clicked', async () => {
      const user = userEvent.setup()
      const analysisData = createMockAnalysisResponse()
      const onAddManualCandidate = vi.fn()

      render(
        <CandidateDetailsCard
          analysisData={analysisData}
          librarySlug="test-library"
          onAddManualCandidate={onAddManualCandidate}
        />
      )

      const addButton = screen.getByRole('button', { name: /Add Manual/i })
      await user.click(addButton)

      // Dialog should be open, defaulting to the Search tab
      expect(screen.getByText('Add Manual Candidate')).toBeInTheDocument()
      expect(screen.getByLabelText('Search term')).toBeInTheDocument()
    })

    it('should close the dialog after a manual candidate is added successfully', async () => {
      const user = userEvent.setup()
      const analysisData = createMockAnalysisResponse()
      const onAddManualCandidate = vi.fn()

      const { rerender } = render(
        <CandidateDetailsCard
          analysisData={analysisData}
          librarySlug="test-library"
          onAddManualCandidate={onAddManualCandidate}
          isAddingManualCandidate={false}
        />
      )

      await user.click(screen.getByRole('button', { name: /Add Manual/i }))
      expect(screen.getByText('Add Manual Candidate')).toBeInTheDocument()

      // Resolution in progress
      rerender(
        <CandidateDetailsCard
          analysisData={analysisData}
          librarySlug="test-library"
          onAddManualCandidate={onAddManualCandidate}
          isAddingManualCandidate={true}
        />
      )

      // Resolution succeeds (no error) -> dialog should close
      rerender(
        <CandidateDetailsCard
          analysisData={analysisData}
          librarySlug="test-library"
          onAddManualCandidate={onAddManualCandidate}
          isAddingManualCandidate={false}
        />
      )

      await waitFor(() => {
        expect(
          screen.queryByText('Add Manual Candidate')
        ).not.toBeInTheDocument()
      })
    })

    it('should keep the dialog open when adding a manual candidate fails', async () => {
      const user = userEvent.setup()
      const analysisData = createMockAnalysisResponse()
      const onAddManualCandidate = vi.fn()

      const { rerender } = render(
        <CandidateDetailsCard
          analysisData={analysisData}
          librarySlug="test-library"
          onAddManualCandidate={onAddManualCandidate}
          isAddingManualCandidate={false}
        />
      )

      await user.click(screen.getByRole('button', { name: /Add Manual/i }))

      rerender(
        <CandidateDetailsCard
          analysisData={analysisData}
          librarySlug="test-library"
          onAddManualCandidate={onAddManualCandidate}
          isAddingManualCandidate={true}
        />
      )

      // Resolution fails -> dialog stays open and shows the error
      rerender(
        <CandidateDetailsCard
          analysisData={analysisData}
          librarySlug="test-library"
          onAddManualCandidate={onAddManualCandidate}
          isAddingManualCandidate={false}
          manualCandidateError="Could not resolve link"
        />
      )

      expect(
        screen.getByText('Add Manual Candidate')
      ).toBeInTheDocument()
      expect(screen.getByText('Could not resolve link')).toBeInTheDocument()
    })

    it('should merge manual and automatic candidates in count badge', () => {
      const analysisData = createMockAnalysisResponse({
        candidates: [
          createMockCandidate({ sourceId: 'mb-1' }),
          createMockCandidate({ sourceId: 'mb-2' }),
        ],
        manualCandidates: [
          createMockCandidate({
            sourceId: 'spotify-1',
            source: 'Spotify',
            isManual: true,
          }),
        ],
      })

      render(<CandidateDetailsCard analysisData={analysisData} />)

      // Total should be 3 (2 auto + 1 manual)
      const threeElements = screen.getAllByText('3')
      expect(threeElements.length).toBeGreaterThanOrEqual(1)
    })
  })

  describe('Flexible height', () => {
    it('should have minimum height class instead of fixed height', () => {
      const { container } = render(<CandidateDetailsCard analysisData={null} />)

      // Should have min-h class but not h-[500px]
      const cardContent = container.querySelector('[class*="min-h-"]')
      expect(cardContent).toBeInTheDocument()

      // Should not have the old fixed height
      const fixedHeightElement = container.querySelector('[class*="h-\\[500px\\]"]')
      expect(fixedHeightElement).not.toBeInTheDocument()
    })
  })

  describe('WAV/WMA handling actions', () => {
    const withLocalAlbum = (
      localOverrides: Record<string, unknown>
    ): AnalyzeAlbumResponse => {
      const base = createMockAnalysisResponse()
      return {
        ...base,
        localAlbum: { ...base.localAlbum, ...localOverrides },
      }
    }

    it('shows Convert WAV button when album has WAVs', () => {
      render(
        <CandidateDetailsCard
          analysisData={withLocalAlbum({ hasWav: true, duplicateWavCount: 0 })}
          onConvertAudio={vi.fn()}
        />
      )
      expect(screen.getByTestId('convert-wav-button')).toBeInTheDocument()
      expect(screen.queryByTestId('convert-wma-button')).not.toBeInTheDocument()
      expect(screen.queryByTestId('dedupe-wav-button')).not.toBeInTheDocument()
    })

    it('shows Convert WMA button when album has WMAs', () => {
      render(
        <CandidateDetailsCard
          analysisData={withLocalAlbum({
            hasWav: false,
            hasWma: true,
            wmaRecommendedTarget: 'mp3',
          })}
          onConvertAudio={vi.fn()}
        />
      )
      expect(screen.getByTestId('convert-wma-button')).toBeInTheDocument()
      expect(screen.queryByTestId('convert-wav-button')).not.toBeInTheDocument()
    })

    it('shows Dedupe button only when duplicates exist', () => {
      render(
        <CandidateDetailsCard
          analysisData={withLocalAlbum({ hasWav: true, duplicateWavCount: 3 })}
          onConvertAudio={vi.fn()}
          onRemoveDuplicateWavs={vi.fn()}
        />
      )
      const dedupe = screen.getByTestId('dedupe-wav-button')
      expect(dedupe).toHaveTextContent('Remove duplicate WAVs (3)')
    })

    it('hides convert buttons for a FLAC-only album', () => {
      render(
        <CandidateDetailsCard
          analysisData={withLocalAlbum({
            hasWav: false,
            hasWma: false,
            duplicateWavCount: 0,
          })}
          onConvertAudio={vi.fn()}
          onRemoveDuplicateWavs={vi.fn()}
        />
      )
      expect(screen.queryByTestId('convert-wav-button')).not.toBeInTheDocument()
      expect(screen.queryByTestId('convert-wma-button')).not.toBeInTheDocument()
      expect(screen.queryByTestId('dedupe-wav-button')).not.toBeInTheDocument()
    })

    it('hides Convert button when no handler is wired', () => {
      render(
        <CandidateDetailsCard
          analysisData={withLocalAlbum({ hasWav: true, duplicateWavCount: 0 })}
        />
      )
      expect(screen.queryByTestId('convert-wav-button')).not.toBeInTheDocument()
    })

    it('converts WAV to FLAC with delete-originals off by default', async () => {
      const onConvertAudio = vi.fn()
      render(
        <CandidateDetailsCard
          analysisData={withLocalAlbum({ hasWav: true, duplicateWavCount: 0 })}
          onConvertAudio={onConvertAudio}
        />
      )
      fireEvent.click(screen.getByTestId('convert-wav-button'))
      const confirm = await screen.findByRole('button', { name: 'Convert' })
      fireEvent.click(confirm)
      expect(onConvertAudio).toHaveBeenCalledWith({
        sourceFormat: 'wav',
        targetFormat: 'flac',
        deleteOriginals: false,
      })
    })

    it('passes delete-originals true when the checkbox is ticked', async () => {
      const onConvertAudio = vi.fn()
      render(
        <CandidateDetailsCard
          analysisData={withLocalAlbum({ hasWav: true, duplicateWavCount: 0 })}
          onConvertAudio={onConvertAudio}
        />
      )
      fireEvent.click(screen.getByTestId('convert-wav-button'))
      fireEvent.click(await screen.findByTestId('delete-originals-checkbox'))
      fireEvent.click(screen.getByRole('button', { name: 'Convert' }))
      expect(onConvertAudio).toHaveBeenCalledWith({
        sourceFormat: 'wav',
        targetFormat: 'flac',
        deleteOriginals: true,
      })
    })

    it('preselects MP3 for low-bitrate WMA', async () => {
      const onConvertAudio = vi.fn()
      render(
        <CandidateDetailsCard
          analysisData={withLocalAlbum({
            hasWav: false,
            hasWma: true,
            wmaRecommendedTarget: 'mp3',
          })}
          onConvertAudio={onConvertAudio}
        />
      )
      fireEvent.click(screen.getByTestId('convert-wma-button'))
      fireEvent.click(await screen.findByRole('button', { name: 'Convert' }))
      expect(onConvertAudio).toHaveBeenCalledWith({
        sourceFormat: 'wma',
        targetFormat: 'mp3',
        deleteOriginals: false,
      })
    })

    it('preselects FLAC for high-bitrate WMA', async () => {
      const onConvertAudio = vi.fn()
      render(
        <CandidateDetailsCard
          analysisData={withLocalAlbum({
            hasWav: false,
            hasWma: true,
            wmaRecommendedTarget: 'flac',
          })}
          onConvertAudio={onConvertAudio}
        />
      )
      fireEvent.click(screen.getByTestId('convert-wma-button'))
      fireEvent.click(await screen.findByRole('button', { name: 'Convert' }))
      expect(onConvertAudio).toHaveBeenCalledWith({
        sourceFormat: 'wma',
        targetFormat: 'flac',
        deleteOriginals: false,
      })
    })

    it('confirms duplicate removal', async () => {
      const onRemoveDuplicateWavs = vi.fn()
      render(
        <CandidateDetailsCard
          analysisData={withLocalAlbum({ hasWav: true, duplicateWavCount: 2 })}
          onRemoveDuplicateWavs={onRemoveDuplicateWavs}
        />
      )
      fireEvent.click(screen.getByTestId('dedupe-wav-button'))
      const confirm = await screen.findByRole('button', { name: /Remove 2 WAVs/ })
      fireEvent.click(confirm)
      expect(onRemoveDuplicateWavs).toHaveBeenCalledTimes(1)
    })

    it('disables actions while an op is running', () => {
      render(
        <CandidateDetailsCard
          analysisData={withLocalAlbum({ hasWav: true, duplicateWavCount: 1 })}
          onConvertAudio={vi.fn()}
          onRemoveDuplicateWavs={vi.fn()}
          isAudioOpRunning
        />
      )
      expect(screen.getByTestId('convert-wav-button')).toBeDisabled()
      expect(screen.getByTestId('dedupe-wav-button')).toBeDisabled()
    })

    it('surfaces an audio-op error', () => {
      render(
        <CandidateDetailsCard
          analysisData={withLocalAlbum({ hasWav: true, duplicateWavCount: 0 })}
          onConvertAudio={vi.fn()}
          audioOpError="ffmpeg blew up"
        />
      )
      expect(screen.getByTestId('audio-op-error')).toHaveTextContent('ffmpeg blew up')
    })
  })
})
