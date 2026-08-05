import { useState, useEffect } from 'react'
import { Eye, EyeOff } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { DiscogsConfig } from '@/types/beets-config'
import PluginSettingsDialog from './PluginSettingsDialog'

interface DiscogsSettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  config: DiscogsConfig
  onSave: (config: DiscogsConfig) => void
}

export default function DiscogsSettingsDialog({
  open,
  onOpenChange,
  config,
  onSave,
}: DiscogsSettingsDialogProps) {
  const [localConfig, setLocalConfig] = useState<DiscogsConfig>(config)
  const [showToken, setShowToken] = useState(false)

  // Reset local state when dialog opens
  useEffect(() => {
    if (open) {
      setLocalConfig(config)
      setShowToken(false)
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
      pluginName="discogs"
      onSave={handleSave}
      onCancel={handleCancel}
    >
      {/* Personal Access Token */}
      <div className="space-y-2">
        <Label htmlFor="discogs-token">Personal Access Token</Label>
        <p className="text-xs text-muted-foreground">
          Generate a personal access token at{' '}
          <a
            href="https://www.discogs.com/settings/developers"
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline"
          >
            discogs.com/settings/developers
          </a>
        </p>
        <div className="flex gap-2">
          <Input
            id="discogs-token"
            type={showToken ? 'text' : 'password'}
            value={localConfig.user_token}
            onChange={(e) =>
              setLocalConfig({ ...localConfig, user_token: e.target.value })
            }
            placeholder="Your Discogs personal access token"
            className="font-mono text-sm"
          />
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={() => setShowToken(!showToken)}
            aria-label={showToken ? 'Hide token' : 'Show token'}
          >
            {showToken ? (
              <EyeOff className="h-4 w-4" />
            ) : (
              <Eye className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>

      <div className="p-3 bg-muted/50 rounded-md text-xs text-muted-foreground">
        <p>
          The Discogs plugin provides additional metadata from the Discogs
          database, which is especially useful for vinyl records and rare
          releases. A personal access token is required to use the Discogs API.
        </p>
      </div>
    </PluginSettingsDialog>
  )
}
