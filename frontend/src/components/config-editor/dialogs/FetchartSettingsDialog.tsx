import { useState, useEffect } from 'react'

import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import type { FetchartConfig } from '@/types/beets-config'
import PluginSettingsDialog from './PluginSettingsDialog'

interface FetchartSettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  config: FetchartConfig
  onSave: (config: FetchartConfig) => void
}

export default function FetchartSettingsDialog({
  open,
  onOpenChange,
  config,
  onSave,
}: FetchartSettingsDialogProps) {
  const [localConfig, setLocalConfig] = useState<FetchartConfig>(config)

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
      pluginName="fetchart"
      onSave={handleSave}
      onCancel={handleCancel}
    >
      {/* Auto Fetch Toggle */}
      <div className="flex items-center justify-between p-4 border rounded-md bg-muted/30">
        <div className="space-y-0.5">
          <Label htmlFor="fetchart-auto" className="text-base">
            Auto Fetch Artwork
          </Label>
          <p className="text-xs text-muted-foreground">
            Automatically download album artwork from online sources on import
          </p>
        </div>
        <Switch
          id="fetchart-auto"
          checked={localConfig.auto}
          onCheckedChange={(checked) =>
            setLocalConfig({ ...localConfig, auto: checked })
          }
        />
      </div>
    </PluginSettingsDialog>
  )
}
