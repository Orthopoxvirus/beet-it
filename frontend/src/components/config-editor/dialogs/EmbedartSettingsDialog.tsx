import { useState, useEffect } from 'react'

import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import type { EmbedartConfig } from '@/types/beets-config'
import PluginSettingsDialog from './PluginSettingsDialog'

interface EmbedartSettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  config: EmbedartConfig
  onSave: (config: EmbedartConfig) => void
}

export default function EmbedartSettingsDialog({
  open,
  onOpenChange,
  config,
  onSave,
}: EmbedartSettingsDialogProps) {
  const [localConfig, setLocalConfig] = useState<EmbedartConfig>(config)

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
      pluginName="embedart"
      onSave={handleSave}
      onCancel={handleCancel}
    >
      {/* Auto Embed Toggle */}
      <div className="flex items-center justify-between p-4 border rounded-md bg-muted/30">
        <div className="space-y-0.5">
          <Label htmlFor="embedart-auto" className="text-base">
            Auto Embed Artwork
          </Label>
          <p className="text-xs text-muted-foreground">
            Automatically embed album artwork into audio files on import
          </p>
        </div>
        <Switch
          id="embedart-auto"
          checked={localConfig.auto}
          onCheckedChange={(checked) =>
            setLocalConfig({ ...localConfig, auto: checked })
          }
        />
      </div>
    </PluginSettingsDialog>
  )
}
