import { useEffect } from 'react'

export interface UseUnsavedChangesGuardOptions {
  /**
   * Whether the form has unsaved changes
   */
  isDirty: boolean
}

export interface UseUnsavedChangesGuardResult {
  /**
   * Whether navigation is currently blocked (always false — in-app blocking
   * requires a Data Router; only browser close/refresh is intercepted)
   */
  isBlocked: boolean
  /**
   * Proceed with navigation (no-op without a blocker)
   */
  proceed: () => void
  /**
   * Reset / stay on current page (no-op without a blocker)
   */
  reset: () => void
}

/**
 * Hook for guarding against unsaved changes when navigating away.
 *
 * Uses a beforeunload event listener to warn the user when they try to
 * close or refresh the browser tab with unsaved changes.
 *
 * Note: In-app navigation blocking via useBlocker requires a Data Router
 * (createBrowserRouter). This app uses BrowserRouter, so only browser-level
 * close/refresh is intercepted.
 */
export function useUnsavedChangesGuard({
  isDirty,
}: UseUnsavedChangesGuardOptions): UseUnsavedChangesGuardResult {
  // Handle browser refresh/close with beforeunload event
  useEffect(() => {
    if (!isDirty) {
      return
    }

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      // For older browsers
      event.returnValue = ''
    }

    window.addEventListener('beforeunload', handleBeforeUnload)

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload)
    }
  }, [isDirty])

  return {
    isBlocked: false,
    proceed: () => {},
    reset: () => {},
  }
}
