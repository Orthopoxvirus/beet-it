import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ScanProgressBar } from './ScanProgressBar'
import type { ScanProgressState } from '@/types/scan'

describe('ScanProgressBar', () => {
  const defaultState: ScanProgressState = {
    isConnected: true,
    isScanning: false,
    isQueued: false,
    isBlocked: false,
    progress: null,
    error: null,
    queuePosition: null,
    blockingOperations: [],
  }

  it('should not render when no scan activity', () => {
    const { container } = render(<ScanProgressBar state={defaultState} />)
    expect(container.firstChild).toBeNull()
  })

  it('should render when scanning', () => {
    const state: ScanProgressState = {
      ...defaultState,
      isScanning: true,
      progress: {
        libraryId: 1,
        librarySlug: 'my-library',
        scanId: 42,
        status: 'scanning',
        itemsProcessed: 50,
        itemsTotal: 100,
        percentage: 50,
        currentFile: '/import/track.flac',
        startedAt: '2024-01-15T10:30:00Z',
        elapsedSeconds: 30,
      },
    }

    render(<ScanProgressBar state={state} />)

    expect(screen.getByText('Scanning...')).toBeInTheDocument()
    expect(screen.getByText('50%')).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })

  it('should show extracting metadata status', () => {
    const state: ScanProgressState = {
      ...defaultState,
      isScanning: true,
      progress: {
        libraryId: 1,
        librarySlug: 'my-library',
        scanId: 42,
        status: 'extracting_metadata',
        itemsProcessed: 75,
        itemsTotal: 100,
        percentage: 75,
        currentFile: '/import/track.flac',
        startedAt: '2024-01-15T10:30:00Z',
        elapsedSeconds: 60,
      },
    }

    render(<ScanProgressBar state={state} />)

    expect(screen.getByText('Extracting metadata...')).toBeInTheDocument()
    expect(screen.getByText('75%')).toBeInTheDocument()
  })

  it('should show queued state', () => {
    const state: ScanProgressState = {
      ...defaultState,
      isQueued: true,
      queuePosition: 2,
    }

    render(<ScanProgressBar state={state} />)

    expect(screen.getByText('Queued (position 2)')).toBeInTheDocument()
  })

  it('should show simple queued state when position is 1', () => {
    const state: ScanProgressState = {
      ...defaultState,
      isQueued: true,
      queuePosition: 1,
    }

    render(<ScanProgressBar state={state} />)

    expect(screen.getByText('Scan queued')).toBeInTheDocument()
  })

  it('should show blocked state with operations', () => {
    const state: ScanProgressState = {
      ...defaultState,
      isQueued: true,
      isBlocked: true,
      blockingOperations: ['import', 'tag_modify'],
    }

    render(<ScanProgressBar state={state} />)

    expect(screen.getByText('Blocked by: import, tag_modify')).toBeInTheDocument()
  })

  it('should show error state', () => {
    const state: ScanProgressState = {
      ...defaultState,
      error: 'Permission denied accessing /import/protected',
    }

    render(<ScanProgressBar state={state} />)

    expect(screen.getByText('Scan failed')).toBeInTheDocument()
  })

  it('should hide percentage when showPercentage is false', () => {
    const state: ScanProgressState = {
      ...defaultState,
      isScanning: true,
      progress: {
        libraryId: 1,
        librarySlug: 'my-library',
        scanId: 42,
        status: 'scanning',
        itemsProcessed: 50,
        itemsTotal: 100,
        percentage: 50,
        currentFile: null,
        startedAt: null,
        elapsedSeconds: null,
      },
    }

    render(<ScanProgressBar state={state} showPercentage={false} />)

    expect(screen.queryByText('50%')).not.toBeInTheDocument()
  })

  it('should apply custom className', () => {
    const state: ScanProgressState = {
      ...defaultState,
      isScanning: true,
      progress: {
        libraryId: 1,
        librarySlug: 'my-library',
        scanId: 42,
        status: 'scanning',
        itemsProcessed: 50,
        itemsTotal: 100,
        percentage: 50,
        currentFile: null,
        startedAt: null,
        elapsedSeconds: null,
      },
    }

    const { container } = render(
      <ScanProgressBar state={state} className="custom-class" />
    )

    expect(container.firstChild).toHaveClass('custom-class')
  })

  it('should show item count in non-compact mode', () => {
    const state: ScanProgressState = {
      ...defaultState,
      isScanning: true,
      progress: {
        libraryId: 1,
        librarySlug: 'my-library',
        scanId: 42,
        status: 'scanning',
        itemsProcessed: 50,
        itemsTotal: 100,
        percentage: 50,
        currentFile: null,
        startedAt: null,
        elapsedSeconds: null,
      },
    }

    render(<ScanProgressBar state={state} compact={false} />)

    expect(screen.getByText('50 / 100 items')).toBeInTheDocument()
  })
})
