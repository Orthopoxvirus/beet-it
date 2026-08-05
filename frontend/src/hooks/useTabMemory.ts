import { useCallback, useMemo } from 'react'

type NavSection = 'library' | 'import'

const TAB_MEMORY_PREFIX = 'nav-tab-memory:'

// Default tabs for each section
const DEFAULT_TABS: Record<NavSection, string> = {
  library: 'albums',
  import: 'beets',
}

// Valid tabs for each section
const VALID_TABS: Record<NavSection, string[]> = {
  library: ['albums', 'titles', 'batch-edit', 'beets-config', 'downloads', 'maintenance', 'settings'],
  import: ['beets', 'upload'],
}

function getStorageKey(section: NavSection): string {
  return `${TAB_MEMORY_PREFIX}${section}`
}

/**
 * Hook for managing tab memory persistence in localStorage.
 * Remembers the last visited sub-tab for each navigation section.
 */
export function useTabMemory(section: NavSection) {
  const getTab = useCallback((): string => {
    const stored = localStorage.getItem(getStorageKey(section))
    // Validate that stored value is a valid tab
    if (stored && VALID_TABS[section].includes(stored)) {
      return stored
    }
    return DEFAULT_TABS[section]
  }, [section])

  const setTab = useCallback(
    (tab: string) => {
      // Only store if it's a valid tab
      if (VALID_TABS[section].includes(tab)) {
        localStorage.setItem(getStorageKey(section), tab)
      }
    },
    [section]
  )

  // Get current tab value (call on each render for fresh value)
  const currentTab = useMemo(() => getTab(), [getTab])

  return {
    /** Current remembered tab for this section */
    currentTab,
    /** Set the remembered tab for this section */
    setTab,
    /** Get the remembered tab (can be called imperatively) */
    getTab,
  }
}

/**
 * Get tab memory for a section without using hooks (for redirect components).
 * This reads directly from localStorage.
 */
export function getTabMemory(section: NavSection): string {
  const stored = localStorage.getItem(getStorageKey(section))
  if (stored && VALID_TABS[section].includes(stored)) {
    return stored
  }
  return DEFAULT_TABS[section]
}

/**
 * Set tab memory for a section without using hooks.
 */
export function setTabMemory(section: NavSection, tab: string): void {
  if (VALID_TABS[section].includes(tab)) {
    localStorage.setItem(getStorageKey(section), tab)
  }
}
