import { ExternalLink, Settings } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { DEFAULT_PLUGINS } from '@/types/beets-config'
import { getPluginMetadata } from '@/data/plugin-metadata'

interface PluginListItemProps {
  pluginName: string
  enabled: boolean
  onToggle: (enabled: boolean) => void
  onSettingsClick: () => void
  hasSettings: boolean
}

export default function PluginListItem({
  pluginName,
  enabled,
  onToggle,
  onSettingsClick,
  hasSettings,
}: PluginListItemProps) {
  const metadata = getPluginMetadata(pluginName)
  const isDefault = DEFAULT_PLUGINS.includes(pluginName)

  return (
    <div
      className={`flex items-center gap-4 p-3 border rounded-lg transition-colors ${
        enabled ? 'bg-background' : 'bg-muted/30'
      }`}
    >
      {/* Plugin Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-medium text-sm">{pluginName}</span>
          {isDefault && (
            <Badge variant="secondary" className="text-xs py-0 h-5">
              Default
            </Badge>
          )}
        </div>
        <p className="text-xs text-muted-foreground line-clamp-2">
          {metadata.description}
        </p>
        <a
          href={metadata.docsUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs text-primary hover:underline mt-1"
          aria-label={`View documentation for ${pluginName} plugin (opens in new tab)`}
        >
          <ExternalLink className="h-3 w-3" />
          Documentation
        </a>
      </div>

      {/* Settings Cog - only visible when enabled AND has settings */}
      <div className="w-10 flex justify-center">
        {enabled && hasSettings && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={onSettingsClick}
            aria-label={`Configure ${pluginName} plugin settings`}
          >
            <Settings className="h-4 w-4" />
          </Button>
        )}
      </div>

      {/* Enable/Disable Toggle */}
      <Switch
        checked={enabled}
        onCheckedChange={onToggle}
        aria-label={`${enabled ? 'Disable' : 'Enable'} ${pluginName} plugin`}
      />
    </div>
  )
}
