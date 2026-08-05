import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import PluginListItem from '../PluginListItem'

describe('PluginListItem', () => {
  const defaultProps = {
    pluginName: 'fetchart',
    enabled: false,
    onToggle: vi.fn(),
    onSettingsClick: vi.fn(),
    hasSettings: true,
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('rendering', () => {
    it('should render plugin name', () => {
      render(<PluginListItem {...defaultProps} />)
      expect(screen.getByText('fetchart')).toBeInTheDocument()
    })

    it('should render plugin description', () => {
      render(<PluginListItem {...defaultProps} />)
      expect(
        screen.getByText(
          'Downloads album artwork from various online sources automatically during import.'
        )
      ).toBeInTheDocument()
    })

    it('should render documentation link', () => {
      render(<PluginListItem {...defaultProps} />)
      const docLink = screen.getByRole('link', { name: /documentation/i })
      expect(docLink).toBeInTheDocument()
      expect(docLink).toHaveAttribute('target', '_blank')
      expect(docLink).toHaveAttribute('rel', 'noopener noreferrer')
    })

    it('should show Default badge for default plugins', () => {
      render(<PluginListItem {...defaultProps} />)
      expect(screen.getByText('Default')).toBeInTheDocument()
    })

    it('should not show Default badge for non-default plugins', () => {
      render(<PluginListItem {...defaultProps} pluginName="badfiles" />)
      expect(screen.queryByText('Default')).not.toBeInTheDocument()
    })
  })

  describe('toggle switch', () => {
    it('should show unchecked toggle when disabled', () => {
      render(<PluginListItem {...defaultProps} enabled={false} />)
      const toggle = screen.getByRole('switch')
      expect(toggle).not.toBeChecked()
    })

    it('should show checked toggle when enabled', () => {
      render(<PluginListItem {...defaultProps} enabled={true} />)
      const toggle = screen.getByRole('switch')
      expect(toggle).toBeChecked()
    })

    it('should call onToggle with true when enabling', () => {
      const onToggle = vi.fn()
      render(
        <PluginListItem {...defaultProps} enabled={false} onToggle={onToggle} />
      )
      const toggle = screen.getByRole('switch')
      fireEvent.click(toggle)
      expect(onToggle).toHaveBeenCalledWith(true)
    })

    it('should call onToggle with false when disabling', () => {
      const onToggle = vi.fn()
      render(
        <PluginListItem {...defaultProps} enabled={true} onToggle={onToggle} />
      )
      const toggle = screen.getByRole('switch')
      fireEvent.click(toggle)
      expect(onToggle).toHaveBeenCalledWith(false)
    })

    it('should have proper ARIA label', () => {
      render(<PluginListItem {...defaultProps} />)
      const toggle = screen.getByRole('switch')
      expect(toggle).toHaveAttribute(
        'aria-label',
        'Enable fetchart plugin'
      )
    })
  })

  describe('settings cog icon', () => {
    it('should show settings cog when enabled and has settings', () => {
      render(
        <PluginListItem {...defaultProps} enabled={true} hasSettings={true} />
      )
      const settingsButton = screen.getByRole('button', {
        name: /configure fetchart plugin settings/i,
      })
      expect(settingsButton).toBeInTheDocument()
    })

    it('should not show settings cog when disabled', () => {
      render(
        <PluginListItem {...defaultProps} enabled={false} hasSettings={true} />
      )
      const settingsButton = screen.queryByRole('button', {
        name: /configure fetchart plugin settings/i,
      })
      expect(settingsButton).not.toBeInTheDocument()
    })

    it('should not show settings cog when enabled but no settings', () => {
      render(
        <PluginListItem {...defaultProps} enabled={true} hasSettings={false} />
      )
      const settingsButton = screen.queryByRole('button', {
        name: /configure fetchart plugin settings/i,
      })
      expect(settingsButton).not.toBeInTheDocument()
    })

    it('should call onSettingsClick when cog is clicked', () => {
      const onSettingsClick = vi.fn()
      render(
        <PluginListItem
          {...defaultProps}
          enabled={true}
          hasSettings={true}
          onSettingsClick={onSettingsClick}
        />
      )
      const settingsButton = screen.getByRole('button', {
        name: /configure fetchart plugin settings/i,
      })
      fireEvent.click(settingsButton)
      expect(onSettingsClick).toHaveBeenCalledTimes(1)
    })
  })

  describe('visual states', () => {
    it('should have active background when enabled', () => {
      const { container } = render(
        <PluginListItem {...defaultProps} enabled={true} />
      )
      const listItem = container.firstChild
      expect(listItem).toHaveClass('bg-background')
    })

    it('should have muted background when disabled', () => {
      const { container } = render(
        <PluginListItem {...defaultProps} enabled={false} />
      )
      const listItem = container.firstChild
      expect(listItem).toHaveClass('bg-muted/30')
    })
  })
})
