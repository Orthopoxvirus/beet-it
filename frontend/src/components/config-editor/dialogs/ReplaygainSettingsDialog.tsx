import { useState, useEffect } from 'react'

import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import type { ReplaygainConfig } from '@/types/beets-config'
import PluginSettingsDialog from './PluginSettingsDialog'

interface ReplaygainSettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  config: ReplaygainConfig
  onSave: (config: ReplaygainConfig) => void
}

export default function ReplaygainSettingsDialog({
  open,
  onOpenChange,
  config,
  onSave,
}: ReplaygainSettingsDialogProps) {
  const [localConfig, setLocalConfig] = useState<ReplaygainConfig>(config)

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
      pluginName="replaygain"
      onSave={handleSave}
      onCancel={handleCancel}
    >
      {/* Auto Calculate Toggle */}
      <div className="flex items-center justify-between p-4 border rounded-md bg-muted/30">
        <div className="space-y-0.5">
          <Label htmlFor="replaygain-auto" className="text-base">
            Auto Calculate ReplayGain
          </Label>
          <p className="text-xs text-muted-foreground">
            Automatically calculate volume normalization values on import
          </p>
        </div>
        <Switch
          id="replaygain-auto"
          checked={localConfig.auto}
          onCheckedChange={(checked) =>
            setLocalConfig({ ...localConfig, auto: checked })
          }
        />
      </div>

      <div className="p-3 bg-muted/50 rounded-md text-xs text-muted-foreground">
        <p>
          ReplayGain normalizes volume levels across your music library for
          consistent playback. This requires the <code>ffmpeg</code> or{' '}
          <code>bs1770gain</code> tool to be installed.
        </p>
      </div>
    </PluginSettingsDialog>
  )
}
