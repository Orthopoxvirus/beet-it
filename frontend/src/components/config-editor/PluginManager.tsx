import { useState, useMemo } from 'react'
import { Search, RotateCcw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

import {
  AVAILABLE_PLUGINS,
  DEFAULT_PLUGINS,
  getDefaultBeetsConfig,
  type BeetsConfig,
  type ConvertConfig,
  type LastgenreConfig,
  type EmbedartConfig,
  type FetchartConfig,
  type ReplaygainConfig,
  type ScrubConfig,
  type EmbyConfig,
  type DiscogsConfig,
  type MatchConfig,
  type ReplaceRule,
} from '@/types/beets-config'
import { getPluginMetadata, PLUGINS_WITH_SETTINGS } from '@/data/plugin-metadata'
import PluginListItem from './PluginListItem'
import {
  ConvertSettingsDialog,
  LastgenreSettingsDialog,
  EmbedartSettingsDialog,
  FetchartSettingsDialog,
  ReplaygainSettingsDialog,
  ScrubSettingsDialog,
  EmbySettingsDialog,
  DiscogsSettingsDialog,
  MatchSettingsDialog,
  PermissionsSettingsDialog,
  ReplaceSettingsDialog,
} from './dialogs'

interface PluginManagerProps {
  plugins: string[]
  onChange: (plugins: string[]) => void
  config: BeetsConfig
  onConfigChange: <K extends keyof BeetsConfig>(key: K, value: BeetsConfig[K]) => void
  libraryId: number
}

type OpenDialog =
  | 'convert'
  | 'lastgenre'
  | 'embedart'
  | 'fetchart'
  | 'replaygain'
  | 'scrub'
  | 'embyupdate'
  | 'discogs'
  | 'match'
  | 'permissions'
  | 'replace'
  | null

export default function PluginManager({
  plugins,
  onChange,
  config,
  onConfigChange,
  libraryId,
}: PluginManagerProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [openDialog, setOpenDialog] = useState<OpenDialog>(null)
  const [showResetConfirm, setShowResetConfirm] = useState(false)

  // Sort plugins: enabled first (sorted alphabetically), then disabled (sorted alphabetically)
  const sortedPlugins = useMemo(() => {
    const enabledSet = new Set(plugins)

    return [...AVAILABLE_PLUGINS].sort((a, b) => {
      const aEnabled = enabledSet.has(a)
      const bEnabled = enabledSet.has(b)

      // Enabled plugins come first
      if (aEnabled && !bEnabled) return -1
      if (!aEnabled && bEnabled) return 1

      // Within enabled/disabled groups, sort alphabetically
      return a.localeCompare(b)
    })
  }, [plugins])

  // Filter plugins based on search query
  const filteredPlugins = useMemo(() => {
    if (!searchQuery.trim()) return sortedPlugins

    const query = searchQuery.toLowerCase()
    return sortedPlugins.filter((plugin) => {
      const metadata = getPluginMetadata(plugin)
      return (
        plugin.toLowerCase().includes(query) ||
        metadata.description.toLowerCase().includes(query)
      )
    })
  }, [sortedPlugins, searchQuery])

  const handleTogglePlugin = (pluginName: string, enabled: boolean) => {
    if (enabled) {
      if (!plugins.includes(pluginName)) {
        onChange([...plugins, pluginName])
      }
    } else {
      onChange(plugins.filter((p) => p !== pluginName))
    }
  }

  const handleSettingsClick = (pluginName: string) => {
    // Map plugin names to dialog types
    const dialogMap: Record<string, OpenDialog> = {
      convert: 'convert',
      lastgenre: 'lastgenre',
      embedart: 'embedart',
      fetchart: 'fetchart',
      replaygain: 'replaygain',
      scrub: 'scrub',
      embyupdate: 'embyupdate',
      discogs: 'discogs',
      match: 'match',
      permissions: 'permissions',
      replace: 'replace',
    }

    const dialog = dialogMap[pluginName]
    if (dialog) {
      setOpenDialog(dialog)
    }
  }

  const handleResetPlugins = () => {
    // Reset to default plugins
    onChange([...DEFAULT_PLUGINS])

    // Reset plugin-specific settings to defaults
    const defaults = getDefaultBeetsConfig(config.directory, config.library)
    onConfigChange('convert', defaults.convert)
    onConfigChange('lastgenre', defaults.lastgenre)
    onConfigChange('embedart', defaults.embedart)
    onConfigChange('fetchart', defaults.fetchart)
    onConfigChange('replaygain', defaults.replaygain)
    onConfigChange('scrub', defaults.scrub)
    onConfigChange('emby', defaults.emby)
    onConfigChange('discogs', defaults.discogs)
    onConfigChange('match', defaults.match)
    onConfigChange('permissions', defaults.permissions)
    onConfigChange('replace', defaults.replace)

    setShowResetConfirm(false)
  }

  const enabledCount = plugins.length

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium">Available Plugins</h3>
          <p className="text-xs text-muted-foreground">
            {enabledCount} of {AVAILABLE_PLUGINS.length} plugins enabled
          </p>
        </div>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search plugins..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-9"
          aria-label="Search plugins"
        />
      </div>

      {/* Plugin List */}
      <ScrollArea className="h-[calc(100%-180px)] min-h-[300px]">
        <div className="space-y-2 pr-4">
          {filteredPlugins.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground text-sm">
              No plugins match your search
            </div>
          ) : (
            filteredPlugins.map((pluginName) => {
              const isEnabled = plugins.includes(pluginName)
              const hasSettings = PLUGINS_WITH_SETTINGS.includes(pluginName)

              return (
                <PluginListItem
                  key={pluginName}
                  pluginName={pluginName}
                  enabled={isEnabled}
                  onToggle={(enabled) => handleTogglePlugin(pluginName, enabled)}
                  onSettingsClick={() => handleSettingsClick(pluginName)}
                  hasSettings={hasSettings}
                />
              )
            })
          )}
        </div>
      </ScrollArea>

      {/* Reset Button */}
      <div className="pt-4 border-t">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setShowResetConfirm(true)}
          className="w-full"
        >
          <RotateCcw className="h-4 w-4 mr-2" />
          Reset plugins to default
        </Button>
      </div>

      {/* Reset Confirmation Dialog */}
      <AlertDialog open={showResetConfirm} onOpenChange={setShowResetConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Reset plugins to default?</AlertDialogTitle>
            <AlertDialogDescription>
              This will reset the enabled plugins to the default set and restore
              all plugin settings to their default values. This action cannot be
              undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleResetPlugins}>
              Reset to defaults
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Plugin Settings Dialogs */}
      <ConvertSettingsDialog
        open={openDialog === 'convert'}
        onOpenChange={(open) => !open && setOpenDialog(null)}
        config={config.convert}
        onSave={(newConfig: ConvertConfig) => {
          onConfigChange('convert', newConfig)
          setOpenDialog(null)
        }}
      />

      <LastgenreSettingsDialog
        open={openDialog === 'lastgenre'}
        onOpenChange={(open) => !open && setOpenDialog(null)}
        config={config.lastgenre}
        onSave={(newConfig: LastgenreConfig) => {
          onConfigChange('lastgenre', newConfig)
          setOpenDialog(null)
        }}
      />

      <EmbedartSettingsDialog
        open={openDialog === 'embedart'}
        onOpenChange={(open) => !open && setOpenDialog(null)}
        config={config.embedart}
        onSave={(newConfig: EmbedartConfig) => {
          onConfigChange('embedart', newConfig)
          setOpenDialog(null)
        }}
      />

      <FetchartSettingsDialog
        open={openDialog === 'fetchart'}
        onOpenChange={(open) => !open && setOpenDialog(null)}
        config={config.fetchart}
        onSave={(newConfig: FetchartConfig) => {
          onConfigChange('fetchart', newConfig)
          setOpenDialog(null)
        }}
      />

      <ReplaygainSettingsDialog
        open={openDialog === 'replaygain'}
        onOpenChange={(open) => !open && setOpenDialog(null)}
        config={config.replaygain}
        onSave={(newConfig: ReplaygainConfig) => {
          onConfigChange('replaygain', newConfig)
          setOpenDialog(null)
        }}
      />

      <ScrubSettingsDialog
        open={openDialog === 'scrub'}
        onOpenChange={(open) => !open && setOpenDialog(null)}
        config={config.scrub}
        onSave={(newConfig: ScrubConfig) => {
          onConfigChange('scrub', newConfig)
          setOpenDialog(null)
        }}
      />

      <EmbySettingsDialog
        open={openDialog === 'embyupdate'}
        onOpenChange={(open) => !open && setOpenDialog(null)}
        config={config.emby}
        libraryId={libraryId}
        onSave={(newConfig: EmbyConfig) => {
          onConfigChange('emby', newConfig)
          setOpenDialog(null)
        }}
      />

      <DiscogsSettingsDialog
        open={openDialog === 'discogs'}
        onOpenChange={(open) => !open && setOpenDialog(null)}
        config={config.discogs}
        onSave={(newConfig: DiscogsConfig) => {
          onConfigChange('discogs', newConfig)
          setOpenDialog(null)
        }}
      />

      <MatchSettingsDialog
        open={openDialog === 'match'}
        onOpenChange={(open) => !open && setOpenDialog(null)}
        config={config.match}
        onSave={(newConfig: MatchConfig) => {
          onConfigChange('match', newConfig)
          setOpenDialog(null)
        }}
      />

      <PermissionsSettingsDialog
        open={openDialog === 'permissions'}
        onOpenChange={(open) => !open && setOpenDialog(null)}
        config={config.permissions}
        onSave={() => {
          // Permissions are read-only, just close
          setOpenDialog(null)
        }}
      />

      <ReplaceSettingsDialog
        open={openDialog === 'replace'}
        onOpenChange={(open) => !open && setOpenDialog(null)}
        config={config.replace}
        onSave={(newConfig: ReplaceRule[]) => {
          onConfigChange('replace', newConfig)
          setOpenDialog(null)
        }}
      />
    </div>
  )
}
