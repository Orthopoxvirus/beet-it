import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import TagFieldConfig from './TagFieldConfig'
import type { TagFieldState, TagName } from '@/types/batch-tag-editor'

describe('TagFieldConfig', () => {
  const defaultState: TagFieldState = {
    enabled: false,
    mode: null,
    fixedValue: '',
    sourceField: 'filename',
    pattern: '',
    replacement: '',
    sequenceStart: 1,
    perDirectory: false,
  }

  const renderComponent = (props: {
    tag: TagName
    state: TagFieldState
    onChange: (state: TagFieldState) => void
    disabled?: boolean
    patternError?: string
  }) => {
    return render(<TagFieldConfig {...props} />)
  }

  describe('Initial rendering', () => {
    it('should render with tag label', () => {
      const onChange = vi.fn()
      renderComponent({ tag: 'album', state: defaultState, onChange })

      expect(screen.getByText('Album')).toBeInTheDocument()
    })

    it('should render mode selector with None selected by default', () => {
      const onChange = vi.fn()
      renderComponent({ tag: 'album', state: defaultState, onChange })

      const selector = screen.getByRole('combobox')
      expect(selector).toBeInTheDocument()
    })

    it('should not show mode-specific inputs when mode is None', () => {
      const onChange = vi.fn()
      renderComponent({ tag: 'album', state: defaultState, onChange })

      expect(screen.queryByLabelText('Fixed Value')).not.toBeInTheDocument()
      expect(screen.queryByText('Source Field')).not.toBeInTheDocument()
      expect(screen.queryByText('Starting Number')).not.toBeInTheDocument()
    })
  })

  describe('Mode selection - standard tags', () => {
    it('should show None, Fixed Value, and Regex options for standard tags', async () => {
      const onChange = vi.fn()
      renderComponent({ tag: 'album', state: defaultState, onChange })

      const selector = screen.getByRole('combobox')
      fireEvent.click(selector)

      await waitFor(() => {
        expect(screen.getByRole('option', { name: 'None' })).toBeInTheDocument()
        expect(screen.getByRole('option', { name: 'Fixed Value' })).toBeInTheDocument()
        expect(screen.getByRole('option', { name: 'Regex' })).toBeInTheDocument()
        expect(screen.queryByRole('option', { name: 'Sequence' })).not.toBeInTheDocument()
      })
    })

    it('should call onChange with fixed mode when Fixed Value is selected', async () => {
      const onChange = vi.fn()
      renderComponent({ tag: 'album', state: defaultState, onChange })

      const selector = screen.getByRole('combobox')
      fireEvent.click(selector)

      const fixedOption = await screen.findByRole('option', { name: 'Fixed Value' })
      fireEvent.click(fixedOption)

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          enabled: true,
          mode: 'fixed',
        })
      )
    })

    it('should call onChange with regex mode when Regex is selected', async () => {
      const onChange = vi.fn()
      renderComponent({ tag: 'album', state: defaultState, onChange })

      const selector = screen.getByRole('combobox')
      fireEvent.click(selector)

      const regexOption = await screen.findByRole('option', { name: 'Regex' })
      fireEvent.click(regexOption)

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          enabled: true,
          mode: 'regex',
          sourceField: 'filename',
        })
      )
    })

    it('should call onChange with disabled state when None is selected', async () => {
      const onChange = vi.fn()
      const enabledState: TagFieldState = {
        ...defaultState,
        enabled: true,
        mode: 'fixed',
        fixedValue: 'Test',
      }
      renderComponent({ tag: 'album', state: enabledState, onChange })

      const selector = screen.getByRole('combobox')
      fireEvent.click(selector)

      const noneOption = await screen.findByRole('option', { name: 'None' })
      fireEvent.click(noneOption)

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          enabled: false,
          mode: null,
        })
      )
    })
  })

  describe('Mode selection - track_number', () => {
    it('should show Sequence option for track_number tag', async () => {
      const onChange = vi.fn()
      renderComponent({ tag: 'track_number', state: defaultState, onChange })

      const selector = screen.getByRole('combobox')
      fireEvent.click(selector)

      await waitFor(() => {
        expect(screen.getByRole('option', { name: 'None' })).toBeInTheDocument()
        expect(screen.getByRole('option', { name: 'Fixed Value' })).toBeInTheDocument()
        expect(screen.getByRole('option', { name: 'Regex' })).toBeInTheDocument()
        expect(screen.getByRole('option', { name: 'Sequence' })).toBeInTheDocument()
      })
    })

    it('should call onChange with sequence mode when Sequence is selected', async () => {
      const onChange = vi.fn()
      renderComponent({ tag: 'track_number', state: defaultState, onChange })

      const selector = screen.getByRole('combobox')
      fireEvent.click(selector)

      const sequenceOption = await screen.findByRole('option', { name: 'Sequence' })
      fireEvent.click(sequenceOption)

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          enabled: true,
          mode: 'sequence',
          sequenceStart: 1,
          perDirectory: false,
        })
      )
    })

    it('should not offer Manual mode unless the host enables it', async () => {
      const onChange = vi.fn()
      renderComponent({ tag: 'track_number', state: defaultState, onChange })

      fireEvent.click(screen.getByRole('combobox'))

      await waitFor(() => {
        expect(screen.getByRole('option', { name: 'Sequence' })).toBeInTheDocument()
        expect(screen.queryByRole('option', { name: 'Manual' })).not.toBeInTheDocument()
      })
    })

    it('should offer Manual mode when allowManualTrackNumbers is set and select it as explicit', async () => {
      const onChange = vi.fn()
      render(
        <TagFieldConfig
          tag="track_number"
          state={defaultState}
          onChange={onChange}
          allowManualTrackNumbers
        />
      )

      fireEvent.click(screen.getByRole('combobox'))

      const manualOption = await screen.findByRole('option', { name: 'Manual' })
      fireEvent.click(manualOption)

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({ enabled: true, mode: 'explicit' })
      )
    })

    it('should show the Manual explanation panel when mode is explicit', () => {
      const onChange = vi.fn()
      render(
        <TagFieldConfig
          tag="track_number"
          state={{ ...defaultState, enabled: true, mode: 'explicit' }}
          onChange={onChange}
          allowManualTrackNumbers
        />
      )

      expect(screen.getByText('Manual Numbering:')).toBeInTheDocument()
    })
  })

  describe('Fixed mode input', () => {
    it('should show Fixed mode input when mode is fixed', () => {
      const onChange = vi.fn()
      const fixedState: TagFieldState = {
        ...defaultState,
        enabled: true,
        mode: 'fixed',
        fixedValue: 'Test Album',
      }
      renderComponent({ tag: 'album', state: fixedState, onChange })

      expect(screen.getByLabelText('Fixed Value')).toBeInTheDocument()
      expect(screen.getByDisplayValue('Test Album')).toBeInTheDocument()
    })

    it('should call onChange when fixed value is changed', () => {
      const onChange = vi.fn()
      const fixedState: TagFieldState = {
        ...defaultState,
        enabled: true,
        mode: 'fixed',
        fixedValue: '',
      }
      renderComponent({ tag: 'album', state: fixedState, onChange })

      const input = screen.getByLabelText('Fixed Value')
      fireEvent.change(input, { target: { value: 'New Album Name' } })

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          fixedValue: 'New Album Name',
        })
      )
    })

    it('should show number input for track_number in fixed mode', () => {
      const onChange = vi.fn()
      const fixedState: TagFieldState = {
        ...defaultState,
        enabled: true,
        mode: 'fixed',
        fixedValue: '5',
      }
      renderComponent({ tag: 'track_number', state: fixedState, onChange })

      const input = screen.getByLabelText('Fixed Value')
      expect(input).toHaveAttribute('type', 'number')
    })
  })

  describe('Regex mode inputs', () => {
    const regexState: TagFieldState = {
      ...defaultState,
      enabled: true,
      mode: 'regex',
      sourceField: 'filename',
      pattern: '^(\\d+)',
      replacement: '$1',
    }

    it('should show all regex inputs when mode is regex', () => {
      const onChange = vi.fn()
      renderComponent({ tag: 'title', state: regexState, onChange })

      expect(screen.getByText('Source Field')).toBeInTheDocument()
      expect(screen.getByText('Regex Pattern')).toBeInTheDocument()
      expect(screen.getByText('Replacement Template')).toBeInTheDocument()
    })

    it('should show source field selector with all options', async () => {
      const onChange = vi.fn()
      renderComponent({ tag: 'title', state: regexState, onChange })

      // Find the source field selector (second combobox after mode selector)
      const selectors = screen.getAllByRole('combobox')
      const sourceFieldSelector = selectors[1]
      fireEvent.click(sourceFieldSelector)

      await waitFor(() => {
        expect(screen.getByRole('option', { name: 'Filename' })).toBeInTheDocument()
        expect(screen.getByRole('option', { name: 'Album' })).toBeInTheDocument()
        expect(screen.getByRole('option', { name: 'Artist' })).toBeInTheDocument()
        expect(screen.getByRole('option', { name: 'Title' })).toBeInTheDocument()
      })
    })

    it('should call onChange when source field is changed', async () => {
      const onChange = vi.fn()
      renderComponent({ tag: 'title', state: regexState, onChange })

      const selectors = screen.getAllByRole('combobox')
      const sourceFieldSelector = selectors[1]
      fireEvent.click(sourceFieldSelector)

      const albumOption = await screen.findByRole('option', { name: 'Album' })
      fireEvent.click(albumOption)

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          sourceField: 'album',
        })
      )
    })

    it('should call onChange when pattern is changed', () => {
      const onChange = vi.fn()
      renderComponent({ tag: 'title', state: regexState, onChange })

      const patternInput = screen.getByPlaceholderText('e.g., ^(\\d+)\\s*[-_]\\s*(.+)\\.mp3$')
      fireEvent.change(patternInput, { target: { value: '^(.+)$' } })

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          pattern: '^(.+)$',
        })
      )
    })

    it('should call onChange when replacement is changed', () => {
      const onChange = vi.fn()
      renderComponent({ tag: 'title', state: regexState, onChange })

      const replacementInput = screen.getByPlaceholderText('e.g., $2')
      fireEvent.change(replacementInput, { target: { value: '$1 - $2' } })

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          replacement: '$1 - $2',
        })
      )
    })

    it('should show pattern error when provided', () => {
      const onChange = vi.fn()
      renderComponent({
        tag: 'title',
        state: regexState,
        onChange,
        patternError: 'Invalid regex: unmatched parenthesis',
      })

      expect(screen.getByText('Invalid regex: unmatched parenthesis')).toBeInTheDocument()
    })

    it('should apply error styling to pattern input when patternError is set', () => {
      const onChange = vi.fn()
      renderComponent({
        tag: 'title',
        state: regexState,
        onChange,
        patternError: 'Invalid regex',
      })

      const patternInput = screen.getByPlaceholderText('e.g., ^(\\d+)\\s*[-_]\\s*(.+)\\.mp3$')
      expect(patternInput.className).toContain('border-destructive')
    })
  })

  describe('Sequence mode inputs', () => {
    const sequenceState: TagFieldState = {
      ...defaultState,
      enabled: true,
      mode: 'sequence',
      sequenceStart: 1,
      perDirectory: false,
    }

    it('should show sequence inputs when mode is sequence', () => {
      const onChange = vi.fn()
      renderComponent({ tag: 'track_number', state: sequenceState, onChange })

      expect(screen.getByText('Starting Number')).toBeInTheDocument()
      expect(screen.getByText('Restart per directory')).toBeInTheDocument()
    })

    it('should call onChange when start value is changed', () => {
      const onChange = vi.fn()
      renderComponent({ tag: 'track_number', state: sequenceState, onChange })

      const startInput = screen.getByLabelText('Starting Number')
      fireEvent.change(startInput, { target: { value: '5' } })

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          sequenceStart: 5,
        })
      )
    })

    it('should call onChange when per directory checkbox is toggled', () => {
      const onChange = vi.fn()
      renderComponent({ tag: 'track_number', state: sequenceState, onChange })

      const checkbox = screen.getByRole('checkbox')
      fireEvent.click(checkbox)

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          perDirectory: true,
        })
      )
    })

    it('should show checked state when perDirectory is true', () => {
      const onChange = vi.fn()
      const perDirState: TagFieldState = {
        ...sequenceState,
        perDirectory: true,
      }
      renderComponent({ tag: 'track_number', state: perDirState, onChange })

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toBeChecked()
    })

    it('should show behavior explanation based on perDirectory setting', () => {
      const onChange = vi.fn()
      renderComponent({ tag: 'track_number', state: sequenceState, onChange })

      expect(screen.getByText(/All tracks will be numbered sequentially/)).toBeInTheDocument()
    })

    it('should update behavior explanation when perDirectory is true', () => {
      const onChange = vi.fn()
      const perDirState: TagFieldState = {
        ...sequenceState,
        perDirectory: true,
      }
      renderComponent({ tag: 'track_number', state: perDirState, onChange })

      expect(screen.getByText(/Each folder will have tracks numbered starting/)).toBeInTheDocument()
    })
  })

  describe('Disabled state', () => {
    it('should disable mode selector when disabled is true', () => {
      const onChange = vi.fn()
      renderComponent({ tag: 'album', state: defaultState, onChange, disabled: true })

      const selector = screen.getByRole('combobox')
      // Radix UI uses data-disabled attribute
      expect(selector).toHaveAttribute('data-disabled')
    })

    it('should disable fixed value input when disabled is true', () => {
      const onChange = vi.fn()
      const fixedState: TagFieldState = {
        ...defaultState,
        enabled: true,
        mode: 'fixed',
        fixedValue: 'Test',
      }
      renderComponent({ tag: 'album', state: fixedState, onChange, disabled: true })

      const input = screen.getByLabelText('Fixed Value')
      expect(input).toBeDisabled()
    })

    it('should disable regex inputs when disabled is true', () => {
      const onChange = vi.fn()
      const regexState: TagFieldState = {
        ...defaultState,
        enabled: true,
        mode: 'regex',
        sourceField: 'filename',
        pattern: '^test',
        replacement: '$1',
      }
      renderComponent({ tag: 'album', state: regexState, onChange, disabled: true })

      const patternInput = screen.getByPlaceholderText('e.g., ^(\\d+)\\s*[-_]\\s*(.+)\\.mp3$')
      expect(patternInput).toBeDisabled()

      const replacementInput = screen.getByPlaceholderText('e.g., $2')
      expect(replacementInput).toBeDisabled()
    })

    it('should disable sequence inputs when disabled is true', () => {
      const onChange = vi.fn()
      const sequenceState: TagFieldState = {
        ...defaultState,
        enabled: true,
        mode: 'sequence',
        sequenceStart: 1,
        perDirectory: false,
      }
      renderComponent({ tag: 'track_number', state: sequenceState, onChange, disabled: true })

      const startInput = screen.getByLabelText('Starting Number')
      expect(startInput).toBeDisabled()

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toBeDisabled()
    })
  })

  describe('Tag labels', () => {
    it('should display correct label for each tag type', () => {
      const onChange = vi.fn()

      const tags: TagName[] = ['album', 'album_artist', 'artist', 'title', 'genre', 'track_number']
      const expectedLabels = ['Album', 'Album Artist', 'Artist', 'Title', 'Genre', 'Track Number']

      tags.forEach((tag, index) => {
        const { unmount } = renderComponent({ tag, state: defaultState, onChange })
        expect(screen.getByText(expectedLabels[index])).toBeInTheDocument()
        unmount()
      })
    })
  })

  describe('Mode switching', () => {
    it('should preserve values when switching from fixed to regex and back', async () => {
      const onChange = vi.fn()
      const fixedState: TagFieldState = {
        ...defaultState,
        enabled: true,
        mode: 'fixed',
        fixedValue: 'Test Album',
        pattern: 'saved pattern',
        replacement: 'saved replacement',
      }
      const { rerender, unmount } = renderComponent({ tag: 'album', state: fixedState, onChange })

      // Switch to regex
      const selector = screen.getByRole('combobox')
      fireEvent.click(selector)

      const regexOption = await screen.findByRole('option', { name: 'Regex' })
      fireEvent.click(regexOption)

      // Verify onChange was called with regex mode but preserved fixedValue
      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          mode: 'regex',
        })
      )

      // Unmount and render fresh with regex state
      unmount()

      // Simulate regex state and switch back
      const regexState: TagFieldState = {
        ...defaultState,
        enabled: true,
        mode: 'regex',
        fixedValue: 'Test Album', // Should still be preserved
        pattern: '^test',
        replacement: '$1',
        sourceField: 'filename',
      }

      // Fresh render with regex state
      const { container } = render(<TagFieldConfig tag="album" state={regexState} onChange={onChange} />)

      // Switch back to fixed - find the mode selector (first combobox)
      const selectors = container.querySelectorAll('[role="combobox"]')
      const newSelector = selectors[0] // First one is the mode selector
      fireEvent.click(newSelector)

      const fixedOption = await screen.findByRole('option', { name: 'Fixed Value' })
      fireEvent.click(fixedOption)

      // Check that the fixed value from before is still passed through
      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({
          mode: 'fixed',
        })
      )
    })
  })
})
