import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import React from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { useUnsavedChangesGuard } from './useUnsavedChangesGuard'

// ============================================================================
// Test Wrapper - uses data router for useBlocker support
// ============================================================================

function createWrapper(initialPath = '/test') {
  // Create a test component that uses our hook
  return function Wrapper({ children }: { children: React.ReactNode }) {
    const router = createMemoryRouter(
      [
        {
          path: '*',
          element: children,
        },
      ],
      { initialEntries: [initialPath] }
    )
    return React.createElement(RouterProvider, { router })
  }
}

// ============================================================================
// Tests
// ============================================================================

describe('useUnsavedChangesGuard', () => {
  let addEventListenerSpy: ReturnType<typeof vi.spyOn>
  let removeEventListenerSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    addEventListenerSpy = vi.spyOn(window, 'addEventListener')
    removeEventListenerSpy = vi.spyOn(window, 'removeEventListener')
  })

  afterEach(() => {
    addEventListenerSpy.mockRestore()
    removeEventListenerSpy.mockRestore()
  })

  describe('initial state', () => {
    it('should return isBlocked as false when isDirty is false', () => {
      const { result } = renderHook(
        () => useUnsavedChangesGuard({ isDirty: false }),
        { wrapper: createWrapper() }
      )

      expect(result.current.isBlocked).toBe(false)
    })

    it('should return isBlocked as false when isDirty is true but no navigation attempted', () => {
      const { result } = renderHook(
        () => useUnsavedChangesGuard({ isDirty: true }),
        { wrapper: createWrapper() }
      )

      expect(result.current.isBlocked).toBe(false)
    })
  })

  describe('beforeunload event handling', () => {
    it('should add beforeunload listener when isDirty is true', () => {
      renderHook(() => useUnsavedChangesGuard({ isDirty: true }), {
        wrapper: createWrapper(),
      })

      expect(addEventListenerSpy).toHaveBeenCalledWith(
        'beforeunload',
        expect.any(Function)
      )
    })

    it('should not add beforeunload listener when isDirty is false', () => {
      renderHook(() => useUnsavedChangesGuard({ isDirty: false }), {
        wrapper: createWrapper(),
      })

      expect(addEventListenerSpy).not.toHaveBeenCalledWith(
        'beforeunload',
        expect.any(Function)
      )
    })

    it('should remove beforeunload listener when isDirty changes from true to false', () => {
      const { rerender } = renderHook(
        ({ isDirty }) => useUnsavedChangesGuard({ isDirty }),
        {
          wrapper: createWrapper(),
          initialProps: { isDirty: true },
        }
      )

      // Clear mock to track only the cleanup
      removeEventListenerSpy.mockClear()

      rerender({ isDirty: false })

      expect(removeEventListenerSpy).toHaveBeenCalledWith(
        'beforeunload',
        expect.any(Function)
      )
    })

    it('should remove beforeunload listener on unmount', () => {
      const { unmount } = renderHook(
        () => useUnsavedChangesGuard({ isDirty: true }),
        { wrapper: createWrapper() }
      )

      // Clear mock to track only the cleanup
      removeEventListenerSpy.mockClear()

      unmount()

      expect(removeEventListenerSpy).toHaveBeenCalledWith(
        'beforeunload',
        expect.any(Function)
      )
    })

    it('should call preventDefault on beforeunload event when isDirty', () => {
      renderHook(() => useUnsavedChangesGuard({ isDirty: true }), {
        wrapper: createWrapper(),
      })

      // Get the registered beforeunload handler
      const beforeunloadCall = addEventListenerSpy.mock.calls.find(
        (call) => call[0] === 'beforeunload'
      )
      expect(beforeunloadCall).toBeDefined()

      const handler = beforeunloadCall![1] as (event: BeforeUnloadEvent) => void

      // Create a mock event
      const event = {
        preventDefault: vi.fn(),
        returnValue: '',
      } as unknown as BeforeUnloadEvent

      // Call the handler
      handler(event)

      expect(event.preventDefault).toHaveBeenCalled()
      expect(event.returnValue).toBe('')
    })
  })

  describe('blocker state', () => {
    // The hook was simplified away from exposing a react-router Blocker object —
    // BrowserRouter cannot use `useBlocker` — to a boolean `isBlocked` plus
    // `proceed`/`reset` no-ops. Only browser close/refresh is intercepted.
    it('should report isBlocked=false when not dirty', () => {
      const { result } = renderHook(
        () => useUnsavedChangesGuard({ isDirty: false }),
        { wrapper: createWrapper() }
      )

      expect(result.current.isBlocked).toBe(false)
      expect(typeof result.current.proceed).toBe('function')
      expect(typeof result.current.reset).toBe('function')
    })
  })

  describe('proceed and reset functions', () => {
    it('should provide proceed function', () => {
      const { result } = renderHook(
        () => useUnsavedChangesGuard({ isDirty: true }),
        { wrapper: createWrapper() }
      )

      expect(typeof result.current.proceed).toBe('function')
    })

    it('should provide reset function', () => {
      const { result } = renderHook(
        () => useUnsavedChangesGuard({ isDirty: true }),
        { wrapper: createWrapper() }
      )

      expect(typeof result.current.reset).toBe('function')
    })

    it('should not throw when calling proceed when not blocked', () => {
      const { result } = renderHook(
        () => useUnsavedChangesGuard({ isDirty: false }),
        { wrapper: createWrapper() }
      )

      expect(() => {
        act(() => {
          result.current.proceed()
        })
      }).not.toThrow()
    })

    it('should not throw when calling reset when not blocked', () => {
      const { result } = renderHook(
        () => useUnsavedChangesGuard({ isDirty: false }),
        { wrapper: createWrapper() }
      )

      expect(() => {
        act(() => {
          result.current.reset()
        })
      }).not.toThrow()
    })
  })
})
