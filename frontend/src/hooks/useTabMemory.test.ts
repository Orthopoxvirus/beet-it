import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useTabMemory, getTabMemory, setTabMemory } from './useTabMemory'

describe('useTabMemory', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  describe('library section', () => {
    it('returns default "albums" when no stored value', () => {
      const { result } = renderHook(() => useTabMemory('library'))
      expect(result.current.currentTab).toBe('albums')
    })

    it('returns stored value when valid', () => {
      localStorage.setItem('nav-tab-memory:library', 'settings')
      const { result } = renderHook(() => useTabMemory('library'))
      expect(result.current.currentTab).toBe('settings')
    })

    it('returns default when stored value is invalid', () => {
      localStorage.setItem('nav-tab-memory:library', 'invalid-tab')
      const { result } = renderHook(() => useTabMemory('library'))
      expect(result.current.currentTab).toBe('albums')
    })

    it('setTab persists valid tab to localStorage', () => {
      const { result } = renderHook(() => useTabMemory('library'))

      act(() => {
        result.current.setTab('batch-edit')
      })

      expect(localStorage.getItem('nav-tab-memory:library')).toBe('batch-edit')
    })

    it('setTab ignores invalid tab', () => {
      localStorage.setItem('nav-tab-memory:library', 'albums')
      const { result } = renderHook(() => useTabMemory('library'))

      act(() => {
        result.current.setTab('invalid-tab')
      })

      // Should not change the stored value
      expect(localStorage.getItem('nav-tab-memory:library')).toBe('albums')
    })

    it('accepts all valid library tabs', () => {
      const { result } = renderHook(() => useTabMemory('library'))

      const validTabs = ['albums', 'batch-edit', 'settings']
      for (const tab of validTabs) {
        act(() => {
          result.current.setTab(tab)
        })
        expect(localStorage.getItem('nav-tab-memory:library')).toBe(tab)
      }
    })
  })

  describe('import section', () => {
    it('returns default "beets" when no stored value', () => {
      const { result } = renderHook(() => useTabMemory('import'))
      expect(result.current.currentTab).toBe('beets')
    })

    it('returns stored value when valid', () => {
      localStorage.setItem('nav-tab-memory:import', 'beets')
      const { result } = renderHook(() => useTabMemory('import'))
      expect(result.current.currentTab).toBe('beets')
    })

    it('returns default when stored value is invalid', () => {
      localStorage.setItem('nav-tab-memory:import', 'invalid-tab')
      const { result } = renderHook(() => useTabMemory('import'))
      expect(result.current.currentTab).toBe('beets')
    })

    it('falls back to default for retired tabs (files/prepare)', () => {
      localStorage.setItem('nav-tab-memory:import', 'files')
      const { result } = renderHook(() => useTabMemory('import'))
      expect(result.current.currentTab).toBe('beets')
    })

    it('accepts all valid import tabs', () => {
      const { result } = renderHook(() => useTabMemory('import'))

      const validTabs = ['beets', 'upload']
      for (const tab of validTabs) {
        act(() => {
          result.current.setTab(tab)
        })
        expect(localStorage.getItem('nav-tab-memory:import')).toBe(tab)
      }
    })
  })

  describe('getTab imperative method', () => {
    it('returns current tab value', () => {
      localStorage.setItem('nav-tab-memory:library', 'settings')
      const { result } = renderHook(() => useTabMemory('library'))
      expect(result.current.getTab()).toBe('settings')
    })
  })
})

describe('getTabMemory (non-hook)', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('returns default for library when no stored value', () => {
    expect(getTabMemory('library')).toBe('albums')
  })

  it('returns default for import when no stored value', () => {
    expect(getTabMemory('import')).toBe('beets')
  })

  it('returns stored value when valid', () => {
    localStorage.setItem('nav-tab-memory:library', 'settings')
    expect(getTabMemory('library')).toBe('settings')
  })

  it('returns default when stored value is invalid', () => {
    localStorage.setItem('nav-tab-memory:library', 'invalid')
    expect(getTabMemory('library')).toBe('albums')
  })
})

describe('setTabMemory (non-hook)', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('stores valid library tab', () => {
    setTabMemory('library', 'batch-edit')
    expect(localStorage.getItem('nav-tab-memory:library')).toBe('batch-edit')
  })

  it('stores valid import tab', () => {
    setTabMemory('import', 'upload')
    expect(localStorage.getItem('nav-tab-memory:import')).toBe('upload')
  })

  it('ignores invalid tab', () => {
    setTabMemory('library', 'invalid')
    expect(localStorage.getItem('nav-tab-memory:library')).toBeNull()
  })
})
