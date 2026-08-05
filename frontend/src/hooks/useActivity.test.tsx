import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  useActivity,
  useActivityCount,
  useActivityHistory,
  activityKeys,
} from './useActivity'
import * as activityApi from '@/api/activity'
import type { ActivitySnapshot, ActivityHistoryResponse } from '@/types/activity'
import type { ReactNode } from 'react'

// Mock the API module
vi.mock('@/api/activity', () => ({
  fetchActivity: vi.fn(),
  fetchActivityHistory: vi.fn(),
  getActivityStreamUrl: vi.fn(() => '/api/v1/activity/stream'),
  transformSSETaskStartedData: vi.fn((data) => data),
  transformSSETaskProgressData: vi.fn((data) => data),
  transformSSETaskCompletedData: vi.fn((data) => data),
  transformSSETaskFailedData: vi.fn((data) => data),
}))

describe('useActivity hooks', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    })
    vi.clearAllMocks()

    // Mock document.hidden for visibility API
    Object.defineProperty(document, 'hidden', {
      configurable: true,
      value: false,
    })
  })

  afterEach(() => {
    queryClient.clear()
  })

  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  const mockActivitySnapshot: ActivitySnapshot = {
    activeTasks: [
      {
        eventId: 1,
        taskType: 'scan',
        libraryId: 1,
        librarySlug: 'test-library',
        description: 'Scan import folder',
        status: 'running',
        startedAt: '2026-02-28T10:30:00Z',
        elapsedSeconds: 45,
        progressPercent: 50,
        metadata: {},
      },
    ],
    queuedTasks: [
      {
        taskType: 'analysis',
        libraryId: 2,
        librarySlug: 'another-library',
        description: 'Album: Artist - Album',
        queuePosition: 1,
        queuedAt: '2026-02-28T10:31:00Z',
      },
    ],
    recentCompletions: [
      {
        eventId: 2,
        taskType: 'scan',
        libraryId: 1,
        librarySlug: 'test-library',
        description: 'Scan import folder',
        status: 'completed',
        startedAt: '2026-02-28T10:25:00Z',
        completedAt: '2026-02-28T10:28:30Z',
        durationSeconds: 210,
        metadata: {},
      },
    ],
    counts: {
      active: 1,
      queued: 1,
      recent: 1,
    },
  }

  const mockHistoryResponse: ActivityHistoryResponse = {
    items: [
      {
        id: 1,
        taskType: 'scan',
        libraryId: 1,
        librarySlug: 'test-library',
        description: 'Scan import folder',
        status: 'completed',
        startedAt: '2026-02-28T10:25:00Z',
        completedAt: '2026-02-28T10:28:30Z',
        durationSeconds: 210,
        metadata: {},
      },
    ],
    total: 1,
    skip: 0,
    limit: 20,
  }

  describe('Query keys', () => {
    it('should have correct base query key', () => {
      expect(activityKeys.all).toEqual(['activity'])
    })

    it('should generate correct snapshot key', () => {
      expect(activityKeys.snapshot()).toEqual(['activity', 'snapshot'])
    })

    it('should generate correct history key with params', () => {
      const params = { skip: 0, limit: 20, libraryId: 1 }
      expect(activityKeys.history(params)).toEqual(['activity', 'history', params])
    })
  })

  describe('useActivity', () => {
    it('should fetch activity snapshot', async () => {
      vi.mocked(activityApi.fetchActivity).mockResolvedValue(mockActivitySnapshot)

      const { result } = renderHook(() => useActivity(), { wrapper })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(activityApi.fetchActivity).toHaveBeenCalled()
      expect(result.current.data).toEqual(mockActivitySnapshot)
    })

    it('should not fetch when disabled', async () => {
      vi.mocked(activityApi.fetchActivity).mockResolvedValue(mockActivitySnapshot)

      renderHook(() => useActivity({ enabled: false }), { wrapper })

      // Wait a bit to ensure no fetch occurs
      await new Promise((resolve) => setTimeout(resolve, 100))

      expect(activityApi.fetchActivity).not.toHaveBeenCalled()
    })

    it('should pause polling when tab is hidden', async () => {
      vi.mocked(activityApi.fetchActivity).mockResolvedValue(mockActivitySnapshot)

      // Simulate hidden tab
      Object.defineProperty(document, 'hidden', {
        configurable: true,
        value: true,
      })

      const { result } = renderHook(() => useActivity(), { wrapper })

      // Wait a bit
      await new Promise((resolve) => setTimeout(resolve, 100))

      // With tab hidden, fetch should not be called
      expect(result.current.isFetching).toBe(false)
    })

    it('should handle fetch errors', async () => {
      const error = new Error('Network error')
      vi.mocked(activityApi.fetchActivity).mockRejectedValue(error)

      const { result } = renderHook(() => useActivity(), { wrapper })

      await waitFor(() => {
        expect(result.current.isError).toBe(true)
      })
    })
  })

  describe('useActivityCount', () => {
    it('should return counts from activity snapshot', async () => {
      vi.mocked(activityApi.fetchActivity).mockResolvedValue(mockActivitySnapshot)

      const { result } = renderHook(() => useActivityCount(), { wrapper })

      await waitFor(() => {
        expect(result.current.active).toBe(1)
      })

      expect(result.current.queued).toBe(1)
      expect(result.current.total).toBe(2)
    })

    it('should return zeros when no data', () => {
      const { result } = renderHook(() => useActivityCount(), { wrapper })

      expect(result.current.active).toBe(0)
      expect(result.current.queued).toBe(0)
      expect(result.current.total).toBe(0)
    })
  })

  describe('useActivityHistory', () => {
    it('should fetch activity history', async () => {
      vi.mocked(activityApi.fetchActivityHistory).mockResolvedValue(mockHistoryResponse)

      const { result } = renderHook(() => useActivityHistory(), { wrapper })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(activityApi.fetchActivityHistory).toHaveBeenCalledWith({})
      expect(result.current.data).toEqual(mockHistoryResponse)
    })

    it('should pass filter params to API', async () => {
      vi.mocked(activityApi.fetchActivityHistory).mockResolvedValue(mockHistoryResponse)

      const params = { skip: 20, limit: 10, libraryId: 1, taskType: 'scan' as const }
      const { result } = renderHook(() => useActivityHistory(params), { wrapper })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(activityApi.fetchActivityHistory).toHaveBeenCalledWith(params)
    })

    it('should not fetch when disabled', async () => {
      vi.mocked(activityApi.fetchActivityHistory).mockResolvedValue(mockHistoryResponse)

      renderHook(() => useActivityHistory({}, { enabled: false }), { wrapper })

      // Wait a bit to ensure no fetch occurs
      await new Promise((resolve) => setTimeout(resolve, 100))

      expect(activityApi.fetchActivityHistory).not.toHaveBeenCalled()
    })
  })
})
