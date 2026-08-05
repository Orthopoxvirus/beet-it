import { useState, useEffect } from 'react'

import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import type { ScrubConfig } from '@/types/beets-config'
import PluginSettingsDialog from './PluginSettingsDialog'

interface ScrubSettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  config: ScrubConfig
  onSave: (config: ScrubConfig) => void
}

export default function ScrubSettingsDialog({
  open,
  onOpenChange,
  config,
  onSave,
}: ScrubSettingsDialogProps) {
  const [localConfig, setLocalConfig] = useState<ScrubConfig>(config)

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

  return (
    <PluginSettingsDialog
      open={open}
      onOpenChange={onOpenChange}
      pluginName="scrub"
      onSave={handleSave}
      onCancel={handleCancel}
    >
      {/* Auto Scrub Toggle */}
      <div className="flex items-center justify-between p-4 border rounded-md bg-muted/30">
        <div className="space-y-0.5">
          <Label htmlFor="scrub-auto" className="text-base">
            Auto Scrub Metadata
          </Label>
          <p className="text-xs text-muted-foreground">
            Automatically remove non-standard metadata tags on import
          </p>
        </div>
        <Switch
          id="scrub-auto"
          checked={localConfig.auto}
          onCheckedChange={(checked) =>
            setLocalConfig({ ...localConfig, auto: checked })
          }
        />
      </div>

      <div className="p-3 bg-muted/50 rounded-md text-xs text-muted-foreground">
        <p>
          The scrub plugin removes non-standard or extraneous metadata tags from
          your audio files, leaving only the tags that beets manages. This helps
          keep your library clean and consistent.
        </p>
      </div>
    </PluginSettingsDialog>
  )
}
