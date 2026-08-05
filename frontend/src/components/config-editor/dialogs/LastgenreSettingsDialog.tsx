import { useState, useEffect } from 'react'

import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { LastgenreConfig } from '@/types/beets-config'
import PluginSettingsDialog from './PluginSettingsDialog'

interface LastgenreSettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  config: LastgenreConfig
  onSave: (config: LastgenreConfig) => void
}

export default function LastgenreSettingsDialog({
  open,
  onOpenChange,
  config,
  onSave,
}: LastgenreSettingsDialogProps) {
  const [localConfig, setLocalConfig] = useState<LastgenreConfig>(config)

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
      pluginName="lastgenre"
      onSave={handleSave}
      onCancel={handleCancel}
    >
      {/* Auto Fetch Toggle */}
      <div className="flex items-center justify-between p-4 border rounded-md bg-muted/30">
        <div className="space-y-0.5">
          <Label htmlFor="lastgenre-auto" className="text-base">
            Auto Fetch Genres
          </Label>
          <p className="text-xs text-muted-foreground">
            Automatically fetch genres from Last.fm on import
          </p>
        </div>
        <Switch
          id="lastgenre-auto"
          checked={localConfig.auto}
          onCheckedChange={(checked) =>
            setLocalConfig({ ...localConfig, auto: checked })
          }
        />
      </div>

      {/* Genre Source Selector */}
      <div className="space-y-2">
        <Label htmlFor="lastgenre-source">Genre Source</Label>
        <p className="text-xs text-muted-foreground">
          Fetch genre from album or individual tracks
        </p>
        <Select
          value={localConfig.source}
          onValueChange={(value: 'album' | 'track') =>
            setLocalConfig({ ...localConfig, source: value })
          }
        >
          <SelectTrigger id="lastgenre-source" className="w-48">
            <SelectValue placeholder="Select source" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="album">Album</SelectItem>
            <SelectItem value="track">Track</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </PluginSettingsDialog>
  )
}
