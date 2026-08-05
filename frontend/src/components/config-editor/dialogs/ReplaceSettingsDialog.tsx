import { useState, useEffect } from 'react'
import { Plus, Trash2, RotateCcw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { DEFAULT_REPLACE_RULES, type ReplaceRule } from '@/types/beets-config'
import PluginSettingsDialog from './PluginSettingsDialog'

interface ReplaceSettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  config: ReplaceRule[]
  onSave: (config: ReplaceRule[]) => void
}

interface ReplaceRuleRowProps {
  rule: ReplaceRule
  index: number
  onChange: (index: number, field: 'pattern' | 'replacement', value: string) => void
  onRemove: (index: number) => void
}

function ReplaceRuleRow({ rule, index, onChange, onRemove }: ReplaceRuleRowProps) {
  return (
    <div className="flex items-center gap-2 py-1">
      <div className="flex-1">
        <Input
          value={rule.pattern}
          onChange={(e) => onChange(index, 'pattern', e.target.value)}
          placeholder="Regex pattern"
          className="font-mono text-sm"
          aria-label={`Pattern for rule ${index + 1}`}
        />
      </div>
      <span className="text-muted-foreground">-&gt;</span>
      <div className="flex-1">
        <Input
          value={rule.replacement}
          onChange={(e) => onChange(index, 'replacement', e.target.value)}
          placeholder="Replacement"
          className="font-mono text-sm"
          aria-label={`Replacement for rule ${index + 1}`}
        />
      </div>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-8 w-8 shrink-0"
        onClick={() => onRemove(index)}
        aria-label={`Remove rule ${index + 1}`}
      >
        <Trash2 className="h-4 w-4 text-destructive" />
      </Button>
    </div>
  )
}

export default function ReplaceSettingsDialog({
  open,
  onOpenChange,
  config,
  onSave,
}: ReplaceSettingsDialogProps) {
  const [localRules, setLocalRules] = useState<ReplaceRule[]>(config)

  // Reset local state when dialog opens
  useEffect(() => {
    if (open) {
      setLocalRules(config)
    }
  }, [open, config])

  const handleSave = () => {
    onSave(localRules)
  }

  const handleCancel = () => {
    setLocalRules(config)
  }

  const handleRuleChange = (
    index: number,
    field: 'pattern' | 'replacement',
    value: string
  ) => {
    const newRules = [...localRules]
    newRules[index] = { ...newRules[index], [field]: value }
    setLocalRules(newRules)
  }

  const handleRemoveRule = (index: number) => {
    const newRules = localRules.filter((_, i) => i !== index)
    setLocalRules(newRules)
  }

  const handleAddRule = () => {
    setLocalRules([...localRules, { pattern: '', replacement: '' }])
  }

  const handleResetToDefaults = () => {
    setLocalRules([...DEFAULT_REPLACE_RULES])
  }

  return (
    <PluginSettingsDialog
      open={open}
      onOpenChange={onOpenChange}
      pluginName="replace"
      onSave={handleSave}
      onCancel={handleCancel}
    >
      {/* Header with actions */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">Character Replacement Rules</p>
          <p className="text-xs text-muted-foreground">
            Regex patterns applied to file paths during import
          </p>
        </div>
        <div className="flex gap-2">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleResetToDefaults}
                >
                  <RotateCcw className="h-4 w-4 mr-1" />
                  Reset
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                Reset to default character replacement rules
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleAddRule}
          >
            <Plus className="h-4 w-4 mr-1" />
            Add
          </Button>
        </div>
      </div>

      {/* Column headers */}
      <div className="flex items-center gap-2 py-1 text-xs text-muted-foreground border-b">
        <div className="flex-1">
          <Label className="text-xs">Pattern (Regex)</Label>
        </div>
        <span className="w-6"></span>
        <div className="flex-1">
          <Label className="text-xs">Replacement</Label>
        </div>
        <div className="w-8"></div>
      </div>

      {/* Rules List */}
      <ScrollArea className="h-56">
        <div className="space-y-1">
          {localRules.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground text-sm">
              No replacement rules defined
            </div>
          ) : (
            localRules.map((rule, index) => (
              <ReplaceRuleRow
                key={index}
                rule={rule}
                index={index}
                onChange={handleRuleChange}
                onRemove={handleRemoveRule}
              />
            ))
          )}
        </div>
      </ScrollArea>

      {/* Reference */}
      <details className="group text-xs text-muted-foreground pt-2 border-t">
        <summary className="cursor-pointer">Default rules reference</summary>
        <div className="mt-2 space-y-1 pl-4">
          <p>
            <code>^.</code> Hidden files (leading dot)
          </p>
          <p>
            <code>[\x00-\x1f]</code> Control characters
          </p>
          <p>
            <code>[&lt;&gt;:&quot;\?\*\|]</code> Windows-illegal characters
          </p>
          <p>
            <code>[\xE8-\xEB]</code> Accented e characters
          </p>
          <p>
            <code>[\xEC-\xEF]</code> Accented i characters
          </p>
          <p>
            <code>[\xE2-\xE6]</code> Accented a characters
          </p>
          <p>
            <code>[\xF2-\xF6]</code> Accented o characters
          </p>
          <p>
            <code>\.$</code> Trailing period
          </p>
          <p>
            <code>\s+$</code> Trailing whitespace
          </p>
        </div>
      </details>
    </PluginSettingsDialog>
  )
}
