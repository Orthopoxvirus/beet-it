import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useScanProgress } from './useScanProgress'
import { MockEventSource } from '../__tests__/setup'

describe('useScanProgress', () => {
  beforeEach(() => {
    MockEventSource.reset()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('should return initial state when slug is undefined', () => {
    const { result } = renderHook(() => useScanProgress(undefined))

    expect(result.current).toEqual({
      isConnected: false,
      isScanning: false,
      isQueued: false,
      isBlocked: false,
      progress: null,
      error: null,
      queuePosition: null,
      blockingOperations: [],
    })
  })

  it('should connect to SSE endpoint when slug is provided', () => {
    renderHook(() => useScanProgress('my-library'))

    const eventSource = MockEventSource.getLastInstance()
    expect(eventSource).toBeDefined()
    expect(eventSource?.url).toBe('/api/libraries/my-library/scan/progress')
  })

  it('should set isConnected to true on open', async () => {
    const { result } = renderHook(() => useScanProgress('my-library'))

    const eventSource = MockEventSource.getLastInstance()
    expect(eventSource).toBeDefined()

    act(() => {
      eventSource!.simulateOpen()
    })

    expect(result.current.isConnected).toBe(true)
    expect(result.current.error).toBeNull()
  })

  it('should handle scan_started event', async () => {
    const onScanStarted = vi.fn()
    const { result } = renderHook(() =>
      useScanProgress('my-library', { onScanStarted })
    )

    const eventSource = MockEventSource.getLastInstance()

    act(() => {
      eventSource!.simulateOpen()
      eventSource!.simulateMessage('scan_started', {
        scan_id: 42,
        library_slug: 'my-library',
        started_at: '2024-01-15T10:30:00Z',
      })
    })

    expect(result.current.isScanning).toBe(true)
    expect(result.current.isQueued).toBe(false)
    expect(result.current.progress).not.toBeNull()
    expect(result.current.progress?.scanId).toBe(42)
    expect(result.current.progress?.status).toBe('scanning')

    expect(onScanStarted).toHaveBeenCalledWith({
      scanId: 42,
      librarySlug: 'my-library',
      startedAt: '2024-01-15T10:30:00Z',
    })
  })

  it('should handle scan_progress event', async () => {
    const { result } = renderHook(() => useScanProgress('my-library'))

    const eventSource = MockEventSource.getLastInstance()

    act(() => {
      eventSource!.simulateOpen()
      eventSource!.simulateMessage('scan_started', {
        scan_id: 42,
        library_slug: 'my-library',
        started_at: '2024-01-15T10:30:00Z',
      })
      eventSource!.simulateMessage('scan_progress', {
        scan_id: 42,
        status: 'extracting_metadata',
        items_total: 150,
        items_processed: 75,
        progress_percent: 50.0,
        current_file: '/import/Artist/track.flac',
        elapsed_seconds: 30,
      })
    })

    expect(result.current.isScanning).toBe(true)
    expect(result.current.progress?.status).toBe('extracting_metadata')
    expect(result.current.progress?.itemsTotal).toBe(150)
    expect(result.current.progress?.itemsProcessed).toBe(75)
    expect(result.current.progress?.percentage).toBe(50.0)
    expect(result.current.progress?.currentFile).toBe('/import/Artist/track.flac')
    expect(result.current.progress?.elapsedSeconds).toBe(30)
  })

  it('should handle scan_completed event', async () => {
    const onScanCompleted = vi.fn()
    const { result } = renderHook(() =>
      useScanProgress('my-library', { onScanCompleted })
    )

    const eventSource = MockEventSource.getLastInstance()

    act(() => {
      eventSource!.simulateOpen()
      eventSource!.simulateMessage('scan_started', {
        scan_id: 42,
        library_slug: 'my-library',
        started_at: '2024-01-15T10:30:00Z',
      })
      eventSource!.simulateMessage('scan_completed', {
        scan_id: 42,
        status: 'completed',
        items_total: 150,
        items_processed: 150,
        new_items: 45,
        modified_items: 10,
        deleted_items: 5,
        completed_at: '2024-01-15T10:35:32Z',
        duration_seconds: 332,
      })
    })

    expect(result.current.isScanning).toBe(false)
    expect(result.current.progress).toBeNull()

    expect(onScanCompleted).toHaveBeenCalledWith({
      scanId: 42,
      status: 'completed',
      itemsTotal: 150,
      itemsProcessed: 150,
      newItems: 45,
      modifiedItems: 10,
      deletedItems: 5,
      completedAt: '2024-01-15T10:35:32Z',
      durationSeconds: 332,
    })
  })

  it('should handle scan_failed event', async () => {
    const onScanFailed = vi.fn()
    const { result } = renderHook(() =>
      useScanProgress('my-library', { onScanFailed })
    )

    const eventSource = MockEventSource.getLastInstance()

    act(() => {
      eventSource!.simulateOpen()
      eventSource!.simulateMessage('scan_failed', {
        scan_id: 42,
        status: 'failed',
        error_message: 'Permission denied',
        failed_at: '2024-01-15T10:31:15Z',
      })
    })

    expect(result.current.isScanning).toBe(false)
    expect(result.current.error).toBe('Permission denied')

    expect(onScanFailed).toHaveBeenCalledWith({
      scanId: 42,
      status: 'failed',
      errorMessage: 'Permission denied',
      failedAt: '2024-01-15T10:31:15Z',
    })
  })

  it('should handle scan_queued event', async () => {
    const { result } = renderHook(() => useScanProgress('my-library'))

    const eventSource = MockEventSource.getLastInstance()

    act(() => {
      eventSource!.simulateOpen()
      eventSource!.simulateMessage('scan_queued', {
        library_slug: 'my-library',
        queue_position: 2,
        blocked_by: ['import'],
      })
    })

    expect(result.current.isScanning).toBe(false)
    expect(result.current.isQueued).toBe(true)
    expect(result.current.isBlocked).toBe(true)
    expect(result.current.queuePosition).toBe(2)
    expect(result.current.blockingOperations).toEqual(['import'])
  })

  it('should handle scan_blocked event', async () => {
    const { result } = renderHook(() => useScanProgress('my-library'))

    const eventSource = MockEventSource.getLastInstance()

    act(() => {
      eventSource!.simulateOpen()
      eventSource!.simulateMessage('scan_blocked', {
        library_slug: 'my-library',
        blocking_operations: ['import', 'tag_modify'],
      })
    })

    expect(result.current.isBlocked).toBe(true)
    expect(result.current.blockingOperations).toEqual(['import', 'tag_modify'])
  })

  it('should close connection when disabled', async () => {
    const { result, rerender } = renderHook(
      ({ enabled }) => useScanProgress('my-library', { enabled }),
      { initialProps: { enabled: true } }
    )

    const eventSource = MockEventSource.getLastInstance()
    expect(eventSource).toBeDefined()

    act(() => {
      eventSource!.simulateOpen()
    })

    expect(result.current.isConnected).toBe(true)

    rerender({ enabled: false })

    expect(result.current.isConnected).toBe(false)
    expect(result.current.isScanning).toBe(false)
  })

  it('should attempt reconnection on error', async () => {
    renderHook(() => useScanProgress('my-library'))

    let eventSource = MockEventSource.getLastInstance()
    expect(eventSource).toBeDefined()

    act(() => {
      eventSource!.simulateOpen()
    })

    act(() => {
      eventSource!.simulateError()
    })

    // Advance timers to trigger reconnection (1s initial delay)
    act(() => {
      vi.advanceTimersByTime(1000)
    })

    // A new EventSource should be created
    const newEventSource = MockEventSource.getLastInstance()
    expect(newEventSource).toBeDefined()
    expect(newEventSource).not.toBe(eventSource)
  })

  it('should cleanup on unmount', () => {
    const { unmount } = renderHook(() => useScanProgress('my-library'))

    const eventSource = MockEventSource.getLastInstance()
    expect(eventSource).toBeDefined()

    unmount()

    // After unmount, the EventSource should be closed
    expect(eventSource!.readyState).toBe(2) // CLOSED state
  })
})
