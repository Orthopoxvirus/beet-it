import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import StageIndicator from '../StageIndicator'

describe('StageIndicator', () => {
  describe('Stage rendering', () => {
    it('should render a single muted disc when stage is none', () => {
      render(<StageIndicator stage="none" />)

      const analyzeButton = screen.getByRole('button', { name: 'Analyze album' })
      expect(analyzeButton).toBeInTheDocument()

      // Only one disc is rendered — the old chosen/imported discs are gone
      expect(screen.queryByLabelText('Candidate not chosen')).not.toBeInTheDocument()
      expect(screen.queryByLabelText('Not imported')).not.toBeInTheDocument()
      expect(screen.getAllByRole('button')).toHaveLength(1)
    })

    it('should label the disc as re-analyze when stage is analyzed', () => {
      render(<StageIndicator stage="analyzed" />)

      const reanalyzeButton = screen.getByRole('button', { name: 'Re-analyze album' })
      expect(reanalyzeButton).toBeInTheDocument()
    })

    it('should label the disc as re-analyze when stage is chosen', () => {
      render(<StageIndicator stage="chosen" />)

      expect(screen.getByRole('button', { name: 'Re-analyze album' })).toBeInTheDocument()
    })

    it('should label the disc as re-analyze when stage is imported', () => {
      render(<StageIndicator stage="imported" />)

      expect(screen.getByRole('button', { name: 'Re-analyze album' })).toBeInTheDocument()
    })
  })

  describe('Click handler', () => {
    it('should call onAnalyzeClick when the disc is clicked', () => {
      const handleClick = vi.fn()
      render(<StageIndicator stage="none" onAnalyzeClick={handleClick} />)

      const analyzeButton = screen.getByRole('button', { name: 'Analyze album' })
      fireEvent.click(analyzeButton)

      expect(handleClick).toHaveBeenCalledTimes(1)
    })

    it('should call onAnalyzeClick when re-analyzing (clicking on analyzed album)', () => {
      const handleClick = vi.fn()
      render(<StageIndicator stage="analyzed" onAnalyzeClick={handleClick} />)

      const reanalyzeButton = screen.getByRole('button', { name: 'Re-analyze album' })
      fireEvent.click(reanalyzeButton)

      expect(handleClick).toHaveBeenCalledTimes(1)
    })

    it('should not call onAnalyzeClick when isAnalyzing is true', () => {
      const handleClick = vi.fn()
      render(<StageIndicator stage="none" onAnalyzeClick={handleClick} isAnalyzing />)

      // When analyzing, the spinner is shown instead of the button
      expect(screen.queryByRole('button', { name: 'Analyze album' })).not.toBeInTheDocument()
    })

    it('should stop event propagation when clicking the disc', () => {
      const handleClick = vi.fn()
      const handleParentClick = vi.fn()

      render(
        <div onClick={handleParentClick}>
          <StageIndicator stage="none" onAnalyzeClick={handleClick} />
        </div>
      )

      const analyzeButton = screen.getByRole('button', { name: 'Analyze album' })
      fireEvent.click(analyzeButton)

      expect(handleClick).toHaveBeenCalledTimes(1)
      expect(handleParentClick).not.toHaveBeenCalled()
    })
  })

  describe('Loading state', () => {
    it('should show spinner when isAnalyzing is true', () => {
      render(<StageIndicator stage="none" isAnalyzing />)

      expect(screen.getByLabelText('Analyzing...')).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Analyze album' })).not.toBeInTheDocument()
    })

    it('should show spinner instead of disc button during analysis', () => {
      render(<StageIndicator stage="analyzed" isAnalyzing />)

      expect(screen.getByLabelText('Analyzing...')).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Re-analyze album' })).not.toBeInTheDocument()
    })
  })

  describe('Styling', () => {
    it('should apply custom className', () => {
      const { container } = render(
        <StageIndicator stage="none" className="custom-class" />
      )

      expect(container.firstChild).toHaveClass('custom-class')
    })

    it('should render as flex container with gap', () => {
      const { container } = render(<StageIndicator stage="none" />)

      expect(container.firstChild).toHaveClass('flex')
      expect(container.firstChild).toHaveClass('items-center')
    })
  })

  describe('Accessibility', () => {
    it('should have proper button type to prevent form submission', () => {
      render(<StageIndicator stage="none" onAnalyzeClick={() => {}} />)

      const button = screen.getByRole('button', { name: 'Analyze album' })
      expect(button).toHaveAttribute('type', 'button')
    })

    it('should have title for hover tooltip', () => {
      render(<StageIndicator stage="none" />)

      const button = screen.getByRole('button', { name: 'Analyze album' })
      expect(button).toHaveAttribute('title', 'Click to analyze')
    })

    it('should have different title when already analyzed', () => {
      render(<StageIndicator stage="analyzed" />)

      const button = screen.getByRole('button', { name: 'Re-analyze album' })
      expect(button).toHaveAttribute('title', 'Click to re-analyze')
    })
  })

  describe('Without onAnalyzeClick handler', () => {
    it('should render button without hover styling when no click handler', () => {
      render(<StageIndicator stage="none" />)

      const button = screen.getByRole('button', { name: 'Analyze album' })
      expect(button).toHaveClass('cursor-default')
    })

    it('should not throw when clicking without handler', () => {
      render(<StageIndicator stage="none" />)

      const button = screen.getByRole('button', { name: 'Analyze album' })
      expect(() => fireEvent.click(button)).not.toThrow()
    })
  })

  describe('Queued state', () => {
    it('should show queued badge when isQueued is true', () => {
      render(<StageIndicator stage="none" isQueued queuePosition={3} />)

      const queueBadge = screen.getByTestId('queue-badge')
      expect(queueBadge).toBeInTheDocument()
      expect(queueBadge).toHaveTextContent('#3')
    })

    it('should display queue position correctly', () => {
      render(<StageIndicator stage="none" isQueued queuePosition={1} />)

      const queueBadge = screen.getByTestId('queue-badge')
      expect(queueBadge).toHaveTextContent('#1')
    })

    it('should show question mark when queue position is undefined', () => {
      render(<StageIndicator stage="none" isQueued />)

      const queueBadge = screen.getByTestId('queue-badge')
      expect(queueBadge).toHaveTextContent('#?')
    })

    it('should not show analyze button when queued', () => {
      render(<StageIndicator stage="none" isQueued queuePosition={2} onAnalyzeClick={() => {}} />)

      expect(screen.queryByRole('button', { name: 'Analyze album' })).not.toBeInTheDocument()
    })

    it('should have amber styling for queue badge', () => {
      render(<StageIndicator stage="none" isQueued queuePosition={5} />)

      const queueBadge = screen.getByTestId('queue-badge')
      expect(queueBadge).toHaveClass('bg-amber-500/10')
      expect(queueBadge).toHaveClass('border-amber-500/30')
    })

    it('should have proper aria label for queued state', () => {
      render(<StageIndicator stage="none" isQueued queuePosition={4} />)

      const queueBadge = screen.getByTestId('queue-badge')
      expect(queueBadge).toHaveAttribute('aria-label', 'Queued at position 4')
    })

    it('should not call onAnalyzeClick when clicking while queued', () => {
      const handleClick = vi.fn()
      render(<StageIndicator stage="none" isQueued queuePosition={1} onAnalyzeClick={handleClick} />)

      const queueBadge = screen.getByTestId('queue-badge')
      fireEvent.click(queueBadge)

      expect(handleClick).not.toHaveBeenCalled()
    })
  })
})
