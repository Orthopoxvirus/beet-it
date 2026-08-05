import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { UpgradeComparison } from '../UpgradeComparison'
import type { AlbumQualityStats } from '@/types/beets-import'

const existing: AlbumQualityStats = {
  trackCount: 10,
  totalBytes: 300_000_000,
  totalDurationSeconds: 2400,
  dominantFormat: 'MP3',
  avgBitrateKbps: 320,
}

const incoming: AlbumQualityStats = {
  trackCount: 12,
  totalBytes: 700_000_000,
  totalDurationSeconds: 2700,
  dominantFormat: 'FLAC',
  avgBitrateKbps: 1000,
}

describe('UpgradeComparison', () => {
  it('renders the Incoming column before the Existing column', () => {
    render(<UpgradeComparison existing={existing} incoming={incoming} />)

    const incomingHeader = screen.getByText('Incoming')
    const existingHeader = screen.getByText('Existing')

    // Incoming must come first in DOM order.
    expect(
      incomingHeader.compareDocumentPosition(existingHeader) &
        Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy()
  })

  it('renders each row value cell with incoming before existing', () => {
    render(<UpgradeComparison existing={existing} incoming={incoming} />)

    // FLAC = incoming, MP3 = existing — incoming value must precede existing.
    const incomingFormat = screen.getByText('FLAC')
    const existingFormat = screen.getByText('MP3')

    expect(
      incomingFormat.compareDocumentPosition(existingFormat) &
        Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy()
  })
})
