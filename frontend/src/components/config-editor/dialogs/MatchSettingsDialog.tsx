import { useState, useEffect } from 'react'
import { HelpCircle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import type { MatchConfig } from '@/types/beets-config'
import PluginSettingsDialog from './PluginSettingsDialog'

interface MatchSettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  config: MatchConfig
  onSave: (config: MatchConfig) => void
}

const PRESETS = [
  { value: 0.04, label: 'Strict', description: '96% similarity required' },
  { value: 0.1, label: 'Moderate', description: '90% similarity required' },
  { value: 0.2, label: 'Relaxed', description: '80% similarity required' },
]

export default function MatchSettingsDialog({
  open,
  onOpenChange,
  config,
  onSave,
}: MatchSettingsDialogProps) {
  const [localConfig, setLocalConfig] = useState<MatchConfig>(config)

  // Reset local state when dialog opens
  useEffect(() => {
    if (open) {
      setLocalConfig(config)
    }
  }, [open, config])

  const handleSave = () => {
    onSave(localConfig)
  }

  const handleCancel = () => {
    setLocalConfig(config)
  }

  const handleSliderChange = (value: number[]) => {
    setLocalConfig({ ...localConfig, strong_rec_thresh: value[0] })
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = parseFloat(e.target.value)
    if (!isNaN(value) && value >= 0 && value <= 1) {
      setLocalConfig({ ...localConfig, strong_rec_thresh: value })
    }
  }

  return (
    <PluginSettingsDialog
      open={open}
      onOpenChange={onOpenChange}
      pluginName="match"
      onSave={handleSave}
      onCancel={handleCancel}
    >
      {/* Header with help tooltip */}
      <div className="flex items-center gap-2">
        <Label className="text-base">Strong Recommendation Threshold</Label>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger>
              <HelpCircle className="h-4 w-4 text-muted-foreground" />
            </TooltipTrigger>
            <TooltipContent side="right" className="max-w-xs">
              <p>
                Autotagger tolerance [0, 1], default 0.04. For example, 0.1
                means 90% similarity required. The inbox-folder autotag setting
                &apos;auto&apos; respects this threshold.
              </p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      <p className="text-xs text-muted-foreground">
        Minimum match quality for auto-tagging (0 = accept anything, 1 = exact
        match only)
      </p>

      {/* Slider and Input */}
      <div className="flex items-center gap-4">
        <div className="flex-1">
          <Slider
            value={[localConfig.strong_rec_thresh]}
            onValueChange={handleSliderChange}
            min={0}
            max={1}
            step={0.01}
            className="w-full"
          />
        </div>
        <Input
          type="number"
          min={0}
          max={1}
          step={0.01}
          value={localConfig.strong_rec_thresh}
          onChange={handleInputChange}
          className="w-24 text-center font-mono"
        />
      </div>

      {/* Scale labels */}
      <div className="flex items-center justify-between text-xs text-muted-foreground px-1">
        <span>Accept any (0)</span>
        <span>Exact match (1)</span>
      </div>

      {/* Presets */}
      <div className="space-y-2 pt-2">
        <Label className="text-xs">Presets</Label>
        <div className="flex gap-2">
          {PRESETS.map((preset) => (
            <Button
              key={preset.value}
              type="button"
              variant={
                localConfig.strong_rec_thresh === preset.value
                  ? 'default'
                  : 'outline'
              }
              size="sm"
              onClick={() =>
                setLocalConfig({
                  ...localConfig,
                  strong_rec_thresh: preset.value,
                })
              }
              className="flex-1"
            >
              <div className="text-center">
                <div className="font-medium">{preset.label}</div>
                <div className="text-xs opacity-70">{preset.value}</div>
              </div>
            </Button>
          ))}
        </div>
      </div>

      {/* Current setting summary */}
      <div className="pt-2 text-xs text-muted-foreground bg-muted/50 p-3 rounded-md">
        <p className="font-medium mb-1">Current setting:</p>
        <p>
          {(100 - localConfig.strong_rec_thresh * 100).toFixed(0)}% similarity
          required for strong recommendations
        </p>
      </div>
    </PluginSettingsDialog>
  )
}
