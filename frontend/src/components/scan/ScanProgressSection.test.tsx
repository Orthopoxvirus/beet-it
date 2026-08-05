import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ScanProgressSection } from './ScanProgressSection'
import type { ScanProgressState, ScanStatus } from '@/types/scan'

describe('ScanProgressSection', () => {
  const defaultProgressState: ScanProgressState = {
    isConnected: true,
    isScanning: false,
    isQueued: false,
    isBlocked: false,
    progress: null,
    error: null,
    queuePosition: null,
    blockingOperations: [],
  }

  const defaultStatusData: ScanStatus = {
    librarySlug: 'my-library',
    currentScan: null,
    queuedScans: 0,
    blockingOperations: [],
    watcherActive: true,
    lastCompletedScan: null,
  }

  it('should render idle state when no scan activity', () => {
    render(
      <ScanProgressSection
        progressState={defaultProgressState}
        statusData={defaultStatusData}
        libraryName="My Library"
      />
    )

    expect(screen.getByText('Scanner')).toBeInTheDocument()
    expect(screen.getByText('No scan is currently running.')).toBeInTheDocument()
  })

  it('should show watcher active badge', () => {
    render(
      <ScanProgressSection
        progressState={defaultProgressState}
        statusData={defaultStatusData}
      />
    )

    expect(screen.getByText('Watcher active')).toBeInTheDocument()
  })

  it('should render scanning state with progress', () => {
    const progressState: ScanProgressState = {
      ...defaultProgressState,
      isScanning: true,
      progress: {
        libraryId: 1,
        librarySlug: 'my-library',
        scanId: 42,
        status: 'scanning',
        itemsProcessed: 50,
        itemsTotal: 100,
        percentage: 50,
        currentFile: '/import/Artist/Album/track.flac',
        startedAt: '2024-01-15T10:30:00Z',
        elapsedSeconds: 120,
      },
    }

    render(
      <ScanProgressSection
        progressState={progressState}
        statusData={defaultStatusData}
      />
    )

    expect(screen.getByText('Scan Progress')).toBeInTheDocument()
    expect(screen.getByText('Scanning files')).toBeInTheDocument()
    expect(screen.getByText('50%')).toBeInTheDocument()
    expect(screen.getByText('50 / 100')).toBeInTheDocument()
    expect(screen.getByText('Items')).toBeInTheDocument()
    expect(screen.getByText('2:00')).toBeInTheDocument() // 120 seconds
    expect(screen.getByText('Elapsed')).toBeInTheDocument()
    expect(screen.getByText('Currently processing:')).toBeInTheDocument()
  })

  it('should show extracting metadata status', () => {
    const progressState: ScanProgressState = {
      ...defaultProgressState,
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
        elapsedSeconds: 180,
      },
    }

    render(
      <ScanProgressSection
        progressState={progressState}
        statusData={defaultStatusData}
      />
    )

    expect(screen.getByText('Extracting metadata')).toBeInTheDocument()
  })

  it('should render queued state', () => {
    const progressState: ScanProgressState = {
      ...defaultProgressState,
      isQueued: true,
      queuePosition: 2,
    }

    render(
      <ScanProgressSection
        progressState={progressState}
        statusData={defaultStatusData}
      />
    )

    expect(screen.getByText('Scan Queued')).toBeInTheDocument()
    expect(screen.getByText('Position 2 in queue')).toBeInTheDocument()
  })

  it('should render blocked state with operations', () => {
    const progressState: ScanProgressState = {
      ...defaultProgressState,
      isQueued: true,
      isBlocked: true,
      blockingOperations: ['import', 'tag_modify'],
    }

    render(
      <ScanProgressSection
        progressState={progressState}
        statusData={defaultStatusData}
      />
    )

    expect(screen.getByText('Scan blocked by running operations')).toBeInTheDocument()
    expect(screen.getByText('Waiting for: import, tag_modify')).toBeInTheDocument()
  })

  it('should render error state', () => {
    const progressState: ScanProgressState = {
      ...defaultProgressState,
      error: 'Permission denied accessing /import/protected',
    }

    render(
      <ScanProgressSection
        progressState={progressState}
        statusData={defaultStatusData}
      />
    )

    expect(screen.getByText('Permission denied accessing /import/protected')).toBeInTheDocument()
  })

  it('should show Scan Now button when no activity', () => {
    const onTriggerScan = vi.fn()

    render(
      <ScanProgressSection
        progressState={defaultProgressState}
        statusData={defaultStatusData}
        onTriggerScan={onTriggerScan}
      />
    )

    const button = screen.getByRole('button', { name: /Scan Now/i })
    expect(button).toBeInTheDocument()

    fireEvent.click(button)
    expect(onTriggerScan).toHaveBeenCalled()
  })

  it('should hide Scan Now button when scanning', () => {
    const progressState: ScanProgressState = {
      ...defaultProgressState,
      isScanning: true,
      progress: {
        libraryId: 1,
        librarySlug: 'my-library',
        scanId: 42,
        status: 'scanning',
        itemsProcessed: 0,
        itemsTotal: 0,
        percentage: 0,
        currentFile: null,
        startedAt: null,
        elapsedSeconds: null,
      },
    }

    render(
      <ScanProgressSection
        progressState={progressState}
        statusData={defaultStatusData}
        onTriggerScan={() => {}}
      />
    )

    expect(screen.queryByRole('button', { name: /Scan Now/i })).not.toBeInTheDocument()
  })

  it('should disable button when triggering scan', () => {
    render(
      <ScanProgressSection
        progressState={defaultProgressState}
        statusData={defaultStatusData}
        onTriggerScan={() => {}}
        isTriggeringScan={true}
      />
    )

    const button = screen.getByRole('button', { name: /Starting/i })
    expect(button).toBeDisabled()
  })

  it('should show last completed scan info', () => {
    const statusData: ScanStatus = {
      ...defaultStatusData,
      lastCompletedScan: {
        id: 41,
        status: 'completed',
        startedAt: '2024-01-15T09:00:00Z',
        completedAt: '2024-01-15T09:05:32Z',
        itemsTotal: 200,
        itemsProcessed: 200,
        progressPercent: 100,
        currentFile: null,
        errorMessage: null,
      },
    }

    render(
      <ScanProgressSection
        progressState={defaultProgressState}
        statusData={statusData}
      />
    )

    expect(screen.getByText(/Last scan completed:/)).toBeInTheDocument()
    expect(screen.getByText(/200 items processed/)).toBeInTheDocument()
  })

  it('should show queued scans count during scanning', () => {
    const progressState: ScanProgressState = {
      ...defaultProgressState,
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
        elapsedSeconds: 60,
      },
    }

    const statusData: ScanStatus = {
      ...defaultStatusData,
      queuedScans: 3,
    }

    render(
      <ScanProgressSection
        progressState={progressState}
        statusData={statusData}
      />
    )

    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('Queued')).toBeInTheDocument()
  })

  it('should format elapsed time correctly', () => {
    // Test with hours
    const progressState: ScanProgressState = {
      ...defaultProgressState,
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
        elapsedSeconds: 3661, // 1 hour, 1 minute, 1 second
      },
    }

    render(
      <ScanProgressSection
        progressState={progressState}
        statusData={defaultStatusData}
      />
    )

    expect(screen.getByText('1:01:01')).toBeInTheDocument()
  })
})
