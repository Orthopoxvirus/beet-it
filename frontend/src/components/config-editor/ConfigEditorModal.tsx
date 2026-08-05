import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2, Settings } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'

import { useLibraryConfig, useUpdateLibraryConfig } from '@/hooks/useConfig'
import {
  beetsConfigSchema,
  getDefaultBeetsConfig,
  type BeetsConfig,
} from '@/types/beets-config'

import PluginManager from './PluginManager'
import GeneralSettingsSection from './sections/GeneralSettingsSection'
import ImportSettingsSection from './sections/ImportSettingsSection'
import PathTemplatesSection from './sections/PathTemplatesSection'
import ConvertSettingsSection from './sections/ConvertSettingsSection'

interface ConfigEditorModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  libraryId: number
  libraryName: string
  libraryPath: string
  databasePath: string
}

export default function ConfigEditorModal({
  open,
  onOpenChange,
  libraryId,
  libraryName,
  libraryPath,
  databasePath,
}: ConfigEditorModalProps) {
  const { data: config, isLoading, error } = useLibraryConfig(libraryId)
  const updateConfigMutation = useUpdateLibraryConfig()

  const form = useForm<BeetsConfig>({
    resolver: zodResolver(beetsConfigSchema),
    defaultValues: getDefaultBeetsConfig(libraryPath, databasePath),
  })

  const { reset, handleSubmit, watch, setValue } = form

  // Reset form when config data is loaded
  useEffect(() => {
    if (config) {
      reset(config)
    }
  }, [config, reset])

  // Reset to defaults when modal opens without config
  useEffect(() => {
    if (open && !config && !isLoading) {
      reset(getDefaultBeetsConfig(libraryPath, databasePath))
    }
  }, [open, config, isLoading, reset, libraryPath, databasePath])

  const onSubmit = async (data: BeetsConfig) => {
    try {
      await updateConfigMutation.mutateAsync({
        libraryId,
        config: data,
      })
      onOpenChange(false)
    } catch (error) {
      // Error is handled by the mutation
      console.error('Failed to save config:', error)
    }
  }

  const handleCancel = () => {
    if (config) {
      reset(config)
    } else {
      reset(getDefaultBeetsConfig(libraryPath, databasePath))
    }
    onOpenChange(false)
  }

  const plugins = watch('plugins')
  const configValues = watch()

  // Helper function to update config by key
  const handleConfigChange = <K extends keyof BeetsConfig>(key: K, value: BeetsConfig[K]) => {
    // Type assertion needed due to react-hook-form's complex typing
    setValue(key, value as any)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col">
        <DialogHeader className="shrink-0">
          <DialogTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Configure Beets Library
          </DialogTitle>
          <DialogDescription>
            Edit the beets configuration for <strong>{libraryName}</strong>
          </DialogDescription>
        </DialogHeader>

        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        )}

        {error && (
          <div className="flex flex-col items-center justify-center py-12">
            <p className="text-destructive mb-2">Failed to load configuration</p>
            <p className="text-sm text-muted-foreground">
              {error instanceof Error ? error.message : 'Unknown error'}
            </p>
          </div>
        )}

        {!isLoading && !error && (
          <form
            onSubmit={handleSubmit(onSubmit)}
            className="flex flex-col flex-1 min-h-0"
          >
            <Tabs defaultValue="general" className="flex flex-col flex-1 min-h-0">
              <TabsList className="grid w-full grid-cols-5 shrink-0">
                <TabsTrigger value="general">General</TabsTrigger>
                <TabsTrigger value="plugins">Plugins</TabsTrigger>
                <TabsTrigger value="paths">Paths</TabsTrigger>
                <TabsTrigger value="import">Import</TabsTrigger>
                <TabsTrigger value="convert">Convert</TabsTrigger>
              </TabsList>

              <ScrollArea className="flex-1 min-h-0 mt-4 h-[calc(90vh-220px)]">
                <div className="pr-4 pb-4">
                  <TabsContent value="general" className="mt-0">
                    <GeneralSettingsSection form={form} libraryId={libraryId} />
                  </TabsContent>

                  <TabsContent value="plugins" className="mt-0">
                    <PluginManager
                      plugins={plugins}
                      onChange={(newPlugins) => setValue('plugins', newPlugins)}
                      config={configValues}
                      onConfigChange={handleConfigChange}
                      libraryId={libraryId}
                    />
                  </TabsContent>

                  <TabsContent value="paths" className="mt-0">
                    <PathTemplatesSection form={form} />
                  </TabsContent>

                  <TabsContent value="import" className="mt-0">
                    <ImportSettingsSection form={form} />
                  </TabsContent>

                  <TabsContent value="convert" className="mt-0">
                    <ConvertSettingsSection form={form} />
                  </TabsContent>
                </div>
              </ScrollArea>
            </Tabs>

            <DialogFooter className="mt-4 pt-4 border-t shrink-0">
              {updateConfigMutation.isError && (
                <p className="text-sm text-destructive mr-auto">
                  {updateConfigMutation.error instanceof Error
                    ? updateConfigMutation.error.message
                    : 'Failed to save configuration'}
                </p>
              )}
              <Button type="button" variant="outline" onClick={handleCancel}>
                Cancel
              </Button>
              <Button type="submit" disabled={updateConfigMutation.isPending}>
                {updateConfigMutation.isPending && (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                )}
                Save Configuration
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}
