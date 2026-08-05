import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, waitFor, cleanup } from '@testing-library/react'

import ImportDragOverlay from './ImportDragOverlay'

// ============================================================================
// Helpers
// ============================================================================

function createMockFile(name: string, size = 10, type = 'audio/flac'): File {
  return new File([new ArrayBuffer(size)], name, { type })
}

/**
 * Build a drag/drop Event with a minimal DataTransfer. `hasFiles` controls the
 * `types` list the overlay inspects; `files` populate `items` for extraction.
 */
function fileDragEvent(type: string, { hasFiles = true, files = [] as File[] } = {}) {
  const event = new Event(type, { bubbles: true, cancelable: true })
  Object.defineProperty(event, 'dataTransfer', {
    value: {
      types: hasFiles ? ['Files'] : ['text/plain'],
      dropEffect: '',
      items: files.map((file) => ({ kind: 'file', getAsFile: () => file })),
    },
  })
  return event
}

function dispatch(type: string, opts?: { hasFiles?: boolean; files?: File[] }) {
  act(() => {
    window.dispatchEvent(fileDragEvent(type, opts))
  })
}

// ============================================================================
// Tests
// ============================================================================

describe('ImportDragOverlay', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    cleanup()
  })

  it('is hidden until a file drag enters the window', () => {
    render(<ImportDragOverlay onFiles={vi.fn()} />)
    expect(screen.queryByTestId('import-drag-overlay')).not.toBeInTheDocument()
  })

  it('appears while files are dragged over the page', () => {
    render(<ImportDragOverlay onFiles={vi.fn()} />)
    dispatch('dragenter')
    expect(screen.getByTestId('import-drag-overlay')).toBeInTheDocument()
    expect(screen.getByText(/max upload size/i)).toBeInTheDocument()
  })

  it('ignores drags that do not carry files', () => {
    render(<ImportDragOverlay onFiles={vi.fn()} />)
    dispatch('dragenter', { hasFiles: false })
    expect(screen.queryByTestId('import-drag-overlay')).not.toBeInTheDocument()
  })

  it('hides again when the drag leaves the window', () => {
    render(<ImportDragOverlay onFiles={vi.fn()} />)
    dispatch('dragenter')
    expect(screen.getByTestId('import-drag-overlay')).toBeInTheDocument()
    dispatch('dragleave')
    expect(screen.queryByTestId('import-drag-overlay')).not.toBeInTheDocument()
  })

  it('forwards dropped files to onFiles and hides', async () => {
    const onFiles = vi.fn()
    render(<ImportDragOverlay onFiles={onFiles} />)

    dispatch('dragenter')
    const file = createMockFile('track.flac')
    dispatch('drop', { files: [file] })

    await waitFor(() => expect(onFiles).toHaveBeenCalledTimes(1))
    expect(onFiles.mock.calls[0][0]).toHaveLength(1)
    expect(onFiles.mock.calls[0][0][0].name).toBe('track.flac')
    expect(screen.queryByTestId('import-drag-overlay')).not.toBeInTheDocument()
  })

  it('does not react to drags while disabled', () => {
    render(<ImportDragOverlay onFiles={vi.fn()} disabled />)
    dispatch('dragenter')
    expect(screen.queryByTestId('import-drag-overlay')).not.toBeInTheDocument()
  })
})
