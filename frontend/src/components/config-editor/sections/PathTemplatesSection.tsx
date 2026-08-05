import { useRef, useState, useCallback } from 'react'
import { UseFormReturn } from 'react-hook-form'

import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { PATH_TEMPLATE_VARIABLES, BeetsConfig } from '@/types/beets-config'
import { cn } from '@/lib/utils'

interface PathTemplatesSectionProps {
  form: UseFormReturn<BeetsConfig>
}

interface PathTemplateFieldProps {
  id: string
  label: string
  description: string
  value: string
  onChange: (value: string) => void
  placeholder: string
  inputRef: (el: HTMLInputElement | null) => void
  onFocus: () => void
  onBlur: () => void
  isFocused: boolean
}

function PathTemplateField({
  id,
  label,
  description,
  value,
  onChange,
  placeholder,
  inputRef,
  onFocus,
  onBlur,
  isFocused,
}: PathTemplateFieldProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Label htmlFor={id}>{label}</Label>
      </div>
      <p className="text-xs text-muted-foreground">{description}</p>
      <Input
        id={id}
        ref={inputRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={onFocus}
        onBlur={onBlur}
        placeholder={placeholder}
        className={cn(
          'font-mono text-sm',
          isFocused && 'ring-2 ring-primary ring-offset-2'
        )}
      />
    </div>
  )
}

export default function PathTemplatesSection({
  form,
}: PathTemplatesSectionProps) {
  const { watch, setValue } = form
  const paths = watch('paths')

  // Track which field is currently focused for click-to-insert
  const [focusedFieldId, setFocusedFieldId] = useState<string | null>(null)

  // Store refs to all input elements
  const inputRefs = useRef<Map<string, HTMLInputElement | null>>(new Map())

  // Create a ref callback for each field
  const createInputRef = useCallback(
    (fieldId: string) => (el: HTMLInputElement | null) => {
      if (el) {
        inputRefs.current.set(fieldId, el)
      } else {
        inputRefs.current.delete(fieldId)
      }
    },
    []
  )

  // Handle focus - track which field is focused
  const handleFocus = useCallback((fieldId: string) => {
    setFocusedFieldId(fieldId)
  }, [])

  // Handle blur - clear focus state with delay to allow click events on variables
  const handleBlur = useCallback(() => {
    // Use a small delay to allow click events on the variable buttons to fire first
    setTimeout(() => {
      setFocusedFieldId(() => {
        // Only clear if the focus hasn't moved to another tracked field
        const activeElement = document.activeElement
        for (const [id, input] of inputRefs.current.entries()) {
          if (input === activeElement) {
            return id
          }
        }
        return null
      })
    }, 150)
  }, [])

  // Insert text at caret position in the focused input
  const insertAtCaret = useCallback(
    (text: string) => {
      if (!focusedFieldId) return

      const input = inputRefs.current.get(focusedFieldId)
      if (!input) return

      const start = input.selectionStart ?? input.value.length
      const end = input.selectionEnd ?? input.value.length
      const currentValue = input.value

      // Create new value with text inserted at caret position
      const newValue =
        currentValue.substring(0, start) + text + currentValue.substring(end)

      // Get the field path from the field ID
      const fieldPath = getFieldPathFromId(focusedFieldId)
      if (fieldPath) {
        setValue(fieldPath as any, newValue, { shouldDirty: true })
      }

      // Restore focus and position caret after inserted text
      requestAnimationFrame(() => {
        input.focus()
        const newPosition = start + text.length
        input.setSelectionRange(newPosition, newPosition)
      })
    },
    [focusedFieldId, setValue]
  )

  // Map field IDs to their form paths
  const getFieldPathFromId = (fieldId: string): string | null => {
    const mapping: Record<string, string> = {
      'paths-default': 'paths.default',
      'paths-singleton': 'paths.singleton',
      'paths-comp': 'paths.comp',
      'paths-soundtrack': 'paths.albumtype_soundtrack',
    }
    return mapping[fieldId] || null
  }

  // Handle click on a variable in the reference panel
  const handleVariableClick = useCallback(
    (variable: string) => {
      if (focusedFieldId) {
        insertAtCaret(variable)
      }
    },
    [focusedFieldId, insertAtCaret]
  )

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h4 className="text-sm font-medium">Path Templates</h4>
        <p className="text-xs text-muted-foreground">
          Configure how music files are organized in your library. Use template
          variables to create dynamic folder structures.
        </p>
      </div>

      <PathTemplateField
        id="paths-default"
        label="Default Path"
        description="Template for regular album tracks"
        value={paths.default}
        onChange={(value) => setValue('paths.default', value, { shouldDirty: true })}
        placeholder="$albumartist/$album%aunique{}/$track - $title"
        inputRef={createInputRef('paths-default')}
        onFocus={() => handleFocus('paths-default')}
        onBlur={handleBlur}
        isFocused={focusedFieldId === 'paths-default'}
      />

      <PathTemplateField
        id="paths-singleton"
        label="Singleton Path"
        description="Template for non-album single tracks"
        value={paths.singleton}
        onChange={(value) => setValue('paths.singleton', value, { shouldDirty: true })}
        placeholder="Singles/$artist - $title"
        inputRef={createInputRef('paths-singleton')}
        onFocus={() => handleFocus('paths-singleton')}
        onBlur={handleBlur}
        isFocused={focusedFieldId === 'paths-singleton'}
      />

      <PathTemplateField
        id="paths-comp"
        label="Compilation Path"
        description="Template for compilation albums"
        value={paths.comp}
        onChange={(value) => setValue('paths.comp', value, { shouldDirty: true })}
        placeholder="Compilations/$album%aunique{}/$track - $title"
        inputRef={createInputRef('paths-comp')}
        onFocus={() => handleFocus('paths-comp')}
        onBlur={handleBlur}
        isFocused={focusedFieldId === 'paths-comp'}
      />

      <PathTemplateField
        id="paths-soundtrack"
        label="Soundtrack Path"
        description="Template for soundtrack albums"
        value={paths.albumtype_soundtrack}
        onChange={(value) => setValue('paths.albumtype_soundtrack', value, { shouldDirty: true })}
        placeholder="Soundtracks/$album/$track $title"
        inputRef={createInputRef('paths-soundtrack')}
        onFocus={() => handleFocus('paths-soundtrack')}
        onBlur={handleBlur}
        isFocused={focusedFieldId === 'paths-soundtrack'}
      />

      {/* Template Variables Reference - Always Visible */}
      <div className="pt-4 border-t">
        <div className="space-y-4">
          <h5 className="text-sm font-medium">Template Variables Reference</h5>
          <p className="text-xs text-muted-foreground">
            {focusedFieldId
              ? 'Click a variable to insert it at the cursor position.'
              : 'Focus an input field above, then click a variable to insert it.'}
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {PATH_TEMPLATE_VARIABLES.map((item) => (
              <div
                key={item.variable}
                onClick={() => handleVariableClick(item.variable)}
                className={cn(
                  'flex items-start gap-2 p-2 rounded-md bg-muted/30 transition-colors',
                  focusedFieldId
                    ? 'cursor-pointer hover:bg-muted/60 hover:ring-1 hover:ring-primary/50'
                    : 'opacity-60 cursor-not-allowed'
                )}
                role="button"
                tabIndex={focusedFieldId ? 0 : -1}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    handleVariableClick(item.variable)
                  }
                }}
              >
                <code
                  className={cn(
                    'text-xs bg-muted px-1.5 py-0.5 rounded font-semibold shrink-0 transition-colors',
                    focusedFieldId && 'group-hover:bg-primary/20'
                  )}
                >
                  {item.variable}
                </code>
                <span className="text-xs text-muted-foreground">
                  {item.description}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
