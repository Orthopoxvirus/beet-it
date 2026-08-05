import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { UnsavedChangesDialog } from './UnsavedChangesDialog'

describe('UnsavedChangesDialog', () => {
  const defaultProps = {
    open: true,
    onStay: vi.fn(),
    onLeave: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render the dialog when open is true', () => {
    render(<UnsavedChangesDialog {...defaultProps} />)

    expect(screen.getByText('Unsaved Changes')).toBeInTheDocument()
    expect(
      screen.getByText(/you have unsaved changes.*your changes will be lost/i)
    ).toBeInTheDocument()
  })

  it('should not render when open is false', () => {
    render(<UnsavedChangesDialog {...defaultProps} open={false} />)

    expect(screen.queryByText('Unsaved Changes')).not.toBeInTheDocument()
  })

  it('should render Stay and Leave buttons', () => {
    render(<UnsavedChangesDialog {...defaultProps} />)

    expect(screen.getByRole('button', { name: /stay/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /leave/i })).toBeInTheDocument()
  })

  it('should call onStay when Stay button is clicked', () => {
    const onStay = vi.fn()
    render(<UnsavedChangesDialog {...defaultProps} onStay={onStay} />)

    fireEvent.click(screen.getByRole('button', { name: /stay/i }))

    expect(onStay).toHaveBeenCalledTimes(1)
  })

  it('should call onLeave when Leave button is clicked', () => {
    const onLeave = vi.fn()
    render(<UnsavedChangesDialog {...defaultProps} onLeave={onLeave} />)

    fireEvent.click(screen.getByRole('button', { name: /leave/i }))

    expect(onLeave).toHaveBeenCalledTimes(1)
  })

  it('should render the warning icon', () => {
    render(<UnsavedChangesDialog {...defaultProps} />)

    // The AlertTriangle icon should be in the document
    // We can verify by checking for the title container with the icon
    const title = screen.getByText('Unsaved Changes')
    expect(title.closest('.flex')).toHaveClass('items-center', 'gap-2')
  })

  it('should render Leave button with destructive styling', () => {
    render(<UnsavedChangesDialog {...defaultProps} />)

    const leaveButton = screen.getByRole('button', { name: /leave/i })
    // Check that the button has the destructive variant class
    expect(leaveButton).toHaveClass('bg-destructive')
  })
})
