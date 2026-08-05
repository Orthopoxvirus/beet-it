import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import PluginManager from '../PluginManager'
import {
  DEFAULT_PLUGINS,
  getDefaultBeetsConfig,
  type BeetsConfig,
} from '@/types/beets-config'

// Mock the useTestEmbyConnection hook
vi.mock('@/hooks/useConfig', () => ({
  useTestEmbyConnection: () => ({
    mutateAsync: vi.fn().mockResolvedValue({ success: true, message: 'OK' }),
    isPending: false,
  }),
}))

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe('PluginManager', () => {
  const defaultConfig: BeetsConfig = getDefaultBeetsConfig('/music', '/music/library.db')

  const defaultProps = {
    plugins: [...DEFAULT_PLUGINS],
    onChange: vi.fn(),
    config: defaultConfig,
    onConfigChange: vi.fn(),
    libraryId: 1,
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('rendering', () => {
    it('should render header with plugin count', () => {
      render(<PluginManager {...defaultProps} />, { wrapper: createWrapper() })
      expect(screen.getByText('Available Plugins')).toBeInTheDocument()
      expect(
        screen.getByText(new RegExp(`${DEFAULT_PLUGINS.length} of \\d+ plugins enabled`))
      ).toBeInTheDocument()
    })

    it('should render search input', () => {
      render(<PluginManager {...defaultProps} />, { wrapper: createWrapper() })
      expect(
        screen.getByPlaceholderText('Search plugins...')
      ).toBeInTheDocument()
    })

    it('should render reset button', () => {
      render(<PluginManager {...defaultProps} />, { wrapper: createWrapper() })
      expect(
        screen.getByRole('button', { name: /reset plugins to default/i })
      ).toBeInTheDocument()
    })

    it('should render all available plugins', () => {
      render(<PluginManager {...defaultProps} />, { wrapper: createWrapper() })
      // Check for some default plugins
      expect(screen.getByText('web')).toBeInTheDocument()
      expect(screen.getByText('fetchart')).toBeInTheDocument()
      expect(screen.getByText('convert')).toBeInTheDocument()
      // Check for some non-default plugins
      expect(screen.getByText('badfiles')).toBeInTheDocument()
      expect(screen.getByText('lyrics')).toBeInTheDocument()
    })
  })

  describe('plugin sorting', () => {
    it('should show enabled plugins before disabled plugins', () => {
      const { container } = render(
        <PluginManager {...defaultProps} plugins={['web', 'convert']} />,
        { wrapper: createWrapper() }
      )

      // Get all plugin name elements
      const pluginItems = container.querySelectorAll('[class*="rounded-lg"]')
      const pluginNames = Array.from(pluginItems).map(
        (item) => item.querySelector('.font-medium')?.textContent
      )

      // First two should be enabled plugins (web and convert)
      // They should appear before disabled plugins
      const webIndex = pluginNames.indexOf('web')
      const convertIndex = pluginNames.indexOf('convert')
      const badfilesIndex = pluginNames.indexOf('badfiles')

      expect(webIndex).toBeLessThan(badfilesIndex)
      expect(convertIndex).toBeLessThan(badfilesIndex)
    })
  })

  describe('search/filter', () => {
    it('should filter plugins by name', async () => {
      render(<PluginManager {...defaultProps} />, { wrapper: createWrapper() })

      const searchInput = screen.getByPlaceholderText('Search plugins...')
      fireEvent.change(searchInput, { target: { value: 'convert' } })

      await waitFor(() => {
        expect(screen.getByText('convert')).toBeInTheDocument()
        expect(screen.queryByText('web')).not.toBeInTheDocument()
      })
    })

    it('should filter plugins by description', async () => {
      render(<PluginManager {...defaultProps} />, { wrapper: createWrapper() })

      const searchInput = screen.getByPlaceholderText('Search plugins...')
      fireEvent.change(searchInput, { target: { value: 'artwork' } })

      await waitFor(() => {
        expect(screen.getByText('fetchart')).toBeInTheDocument()
        expect(screen.getByText('embedart')).toBeInTheDocument()
      })
    })

    it('should show empty message when no plugins match', async () => {
      render(<PluginManager {...defaultProps} />, { wrapper: createWrapper() })

      const searchInput = screen.getByPlaceholderText('Search plugins...')
      fireEvent.change(searchInput, { target: { value: 'xyznonexistent' } })

      await waitFor(() => {
        expect(
          screen.getByText('No plugins match your search')
        ).toBeInTheDocument()
      })
    })
  })

  describe('toggle functionality', () => {
    it('should call onChange when enabling a plugin', async () => {
      const onChange = vi.fn()
      render(
        <PluginManager {...defaultProps} plugins={['web']} onChange={onChange} />,
        { wrapper: createWrapper() }
      )

      // Find the convert plugin toggle (which is disabled)
      const searchInput = screen.getByPlaceholderText('Search plugins...')
      fireEvent.change(searchInput, { target: { value: 'convert' } })

      await waitFor(() => {
        const toggles = screen.getAllByRole('switch')
        // Click the toggle for convert
        fireEvent.click(toggles[0])
      })

      expect(onChange).toHaveBeenCalledWith(['web', 'convert'])
    })

    it('should call onChange when disabling a plugin', async () => {
      const onChange = vi.fn()
      render(
        <PluginManager
          {...defaultProps}
          plugins={['web', 'convert']}
          onChange={onChange}
        />,
        { wrapper: createWrapper() }
      )

      // Find convert plugin
      const searchInput = screen.getByPlaceholderText('Search plugins...')
      fireEvent.change(searchInput, { target: { value: 'convert' } })

      await waitFor(() => {
        const toggles = screen.getAllByRole('switch')
        // Click the enabled toggle for convert
        fireEvent.click(toggles[0])
      })

      expect(onChange).toHaveBeenCalledWith(['web'])
    })
  })

  describe('reset functionality', () => {
    it('should show confirmation dialog when reset button clicked', async () => {
      render(<PluginManager {...defaultProps} plugins={['web']} />, {
        wrapper: createWrapper(),
      })

      const resetButton = screen.getByRole('button', {
        name: /reset plugins to default/i,
      })
      fireEvent.click(resetButton)

      await waitFor(() => {
        expect(
          screen.getByText('Reset plugins to default?')
        ).toBeInTheDocument()
      })
    })

    it('should reset plugins when confirmed', async () => {
      const onChange = vi.fn()
      const onConfigChange = vi.fn()
      render(
        <PluginManager
          {...defaultProps}
          plugins={['web']}
          onChange={onChange}
          onConfigChange={onConfigChange}
        />,
        { wrapper: createWrapper() }
      )

      const resetButton = screen.getByRole('button', {
        name: /reset plugins to default/i,
      })
      fireEvent.click(resetButton)

      await waitFor(() => {
        const confirmButton = screen.getByRole('button', {
          name: /reset to defaults/i,
        })
        fireEvent.click(confirmButton)
      })

      expect(onChange).toHaveBeenCalledWith(DEFAULT_PLUGINS)
    })

    it('should cancel reset when cancelled', async () => {
      const onChange = vi.fn()
      render(
        <PluginManager {...defaultProps} plugins={['web']} onChange={onChange} />,
        { wrapper: createWrapper() }
      )

      const resetButton = screen.getByRole('button', {
        name: /reset plugins to default/i,
      })
      fireEvent.click(resetButton)

      await waitFor(() => {
        const cancelButton = screen.getByRole('button', { name: /cancel/i })
        fireEvent.click(cancelButton)
      })

      expect(onChange).not.toHaveBeenCalled()
    })
  })

  describe('settings dialogs', () => {
    it('should open convert settings dialog when cog clicked', async () => {
      render(<PluginManager {...defaultProps} />, { wrapper: createWrapper() })

      // Filter to convert plugin
      const searchInput = screen.getByPlaceholderText('Search plugins...')
      fireEvent.change(searchInput, { target: { value: 'convert' } })

      await waitFor(() => {
        const settingsButton = screen.getByRole('button', {
          name: /configure convert plugin settings/i,
        })
        fireEvent.click(settingsButton)
      })

      await waitFor(() => {
        expect(screen.getByText('convert Settings')).toBeInTheDocument()
      })
    })

    it('should update config when dialog is saved', async () => {
      const onConfigChange = vi.fn()
      render(
        <PluginManager {...defaultProps} onConfigChange={onConfigChange} />,
        { wrapper: createWrapper() }
      )

      // Filter to convert plugin
      const searchInput = screen.getByPlaceholderText('Search plugins...')
      fireEvent.change(searchInput, { target: { value: 'convert' } })

      await waitFor(() => {
        const settingsButton = screen.getByRole('button', {
          name: /configure convert plugin settings/i,
        })
        fireEvent.click(settingsButton)
      })

      await waitFor(() => {
        // Change auto setting
        const autoToggle = screen.getByRole('switch', {
          name: /auto convert on import/i,
        })
        fireEvent.click(autoToggle)
      })

      // Click Apply button
      const applyButton = screen.getByRole('button', { name: /apply/i })
      fireEvent.click(applyButton)

      expect(onConfigChange).toHaveBeenCalledWith('convert', expect.any(Object))
    })
  })
})
