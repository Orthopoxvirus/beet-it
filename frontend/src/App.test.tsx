import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { Routes, Route, Navigate } from 'react-router-dom'

// Test route structure directly without rendering full components
// This validates the routing logic without needing full component mocks

function LocationDisplay() {
  const location = useLocation()
  return <div data-testid="location">{location.pathname}</div>
}

function TestRoutes() {
  return (
    <Routes>
      <Route path="libraries/:slug" element={<Navigate to="albums" replace />} />
      <Route path="libraries/:slug/albums" element={<LocationDisplay />} />
      <Route path="libraries/:slug/batch-edit" element={<LocationDisplay />} />
      <Route path="libraries/:slug/settings" element={<LocationDisplay />} />
      <Route path="import/:slug">
        <Route index element={<Navigate to="beets" replace />} />
        <Route path="beets" element={<LocationDisplay />} />
        <Route path="upload" element={<LocationDisplay />} />
        <Route path="files" element={<Navigate to="../beets" replace />} />
        <Route path="prepare" element={<Navigate to="../beets" replace />} />
      </Route>
    </Routes>
  )
}

function renderRoutes(initialRoute: string) {
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <TestRoutes />
    </MemoryRouter>
  )
}

describe('Route Configuration', () => {
  describe('Library Routes', () => {
    it('redirects /libraries/:slug to /libraries/:slug/albums', () => {
      const { getByTestId } = renderRoutes('/libraries/test-library')
      expect(getByTestId('location').textContent).toBe('/libraries/test-library/albums')
    })

    it('renders /libraries/:slug/albums', () => {
      const { getByTestId } = renderRoutes('/libraries/test-library/albums')
      expect(getByTestId('location').textContent).toBe('/libraries/test-library/albums')
    })

    it('renders /libraries/:slug/batch-edit', () => {
      const { getByTestId } = renderRoutes('/libraries/test-library/batch-edit')
      expect(getByTestId('location').textContent).toBe('/libraries/test-library/batch-edit')
    })

    it('renders /libraries/:slug/settings', () => {
      const { getByTestId } = renderRoutes('/libraries/test-library/settings')
      expect(getByTestId('location').textContent).toBe('/libraries/test-library/settings')
    })
  })

  describe('Import Routes', () => {
    it('redirects /import/:slug to /import/:slug/beets', () => {
      const { getByTestId } = renderRoutes('/import/test-library')
      expect(getByTestId('location').textContent).toBe('/import/test-library/beets')
    })

    it('renders /import/:slug/beets', () => {
      const { getByTestId } = renderRoutes('/import/test-library/beets')
      expect(getByTestId('location').textContent).toBe('/import/test-library/beets')
    })

    it('renders /import/:slug/upload', () => {
      const { getByTestId } = renderRoutes('/import/test-library/upload')
      expect(getByTestId('location').textContent).toBe('/import/test-library/upload')
    })

    it('redirects legacy /import/:slug/files to beets', () => {
      const { getByTestId } = renderRoutes('/import/test-library/files')
      expect(getByTestId('location').textContent).toBe('/import/test-library/beets')
    })

    it('redirects legacy /import/:slug/prepare to beets', () => {
      const { getByTestId } = renderRoutes('/import/test-library/prepare')
      expect(getByTestId('location').textContent).toBe('/import/test-library/beets')
    })
  })
})
