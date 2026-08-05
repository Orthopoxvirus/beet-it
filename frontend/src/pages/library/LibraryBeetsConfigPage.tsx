import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2, Settings, AlertTriangle, CheckCircle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { UnsavedChangesDialog } from '@/components/UnsavedChangesDialog'

import { useLibraryConfig, useUpdateLibraryConfig } from '@/hooks/useConfig'
import { useUnsavedChangesGuard } from '@/hooks/useUnsavedChangesGuard'
import {
  beetsConfigSchema,
  getDefaultBeetsConfig,
  type BeetsConfig,
} from '@/types/beets-config'

import PluginManager from '@/components/config-editor/PluginManager'
import GeneralSettingsSection from '@/components/config-editor/sections/GeneralSettingsSection'
import ImportSettingsSection from '@/components/config-editor/sections/ImportSettingsSection'
import PathTemplatesSection from '@/components/config-editor/sections/PathTemplatesSection'
import ConvertSettingsSection from '@/components/config-editor/sections/ConvertSettingsSection'
import type { LibraryDetailContext } from '../LibraryDetailLayout'

export default function LibraryBeetsConfigPage() {
  const { library } = useOutletContext<LibraryDetailContext>()

  const { data: config, isLoading, error } = useLibraryConfig(library.id)
  const updateConfigMutation = useUpdateLibraryConfig()

  const [saveSuccess, setSaveSuccess] = useState(false)
  const [validationError, setValidationError] = useState<string | null>(null)

  const form = useForm<BeetsConfig>({
    resolver: zodResolver(beetsConfigSchema),
    defaultValues: getDefaultBeetsConfig(library.library_path, library.database_path),
  })

  const { reset, handleSubmit, watch, setValue, formState } = form
  const isDirty = formState.isDirty

  // Guard against navigation with unsaved changes
  const { isBlocked, proceed, reset: resetBlocker } = useUnsavedChangesGuard({ isDirty })

  // Reset form when config data is loaded
  useEffect(() => {
    if (config) {
      reset(config)
    }
  }, [config, reset])

  // Reset to defaults when page loads without config
  useEffect(() => {
    if (!config && !isLoading) {
      reset(getDefaultBeetsConfig(library.library_path, library.database_path))
    }
  }, [config, isLoading, reset, library.library_path, library.database_path])

  const onSubmit = async (data: BeetsConfig) => {
    setValidationError(null)
    setSaveSuccess(false)
    try {
      await updateConfigMutation.mutateAsync({
        libraryId: library.id,
        config: data,
      })
      // Reset form dirty state after successful save
      reset(data)
      setSaveSuccess(true)
    } catch (err) {
      // Error is handled by the mutation
      console.error('Failed to save config:', err)
    }
  }

  const onInvalid = (errors: Record<string, unknown>) => {
    console.error('Beets config validation failed:', errors)
    // Walk nested error structure and grab the first human-readable message so
    // users see *why* save did nothing instead of a silent no-op.
    const findFirstMessage = (node: unknown): string | null => {
      if (!node || typeof node !== 'object') return null
      const obj = node as Record<string, unknown>
      if (typeof obj.message === 'string' && obj.message) {
        return obj.message
      }
      for (const value of Object.values(obj)) {
        const msg = findFirstMessage(value)
        if (msg) return msg
      }
      return null
    }
    const message = findFirstMessage(errors) || 'Configuration is invalid'
    setValidationError(message)
  }

  const handleDiscard = () => {
    setValidationError(null)
    setSaveSuccess(false)
    if (config) {
      reset(config)
    } else {
      reset(getDefaultBeetsConfig(library.library_path, library.database_path))
    }
  }

  // Clear the "Saved" pill as soon as the user touches the form again.
  useEffect(() => {
    if (isDirty && saveSuccess) {
      setSaveSuccess(false)
    }
  }, [isDirty, saveSuccess])

  const plugins = watch('plugins')
  const configValues = watch()

  // Helper function to update config by key
  const handleConfigChange = <K extends keyof BeetsConfig>(key: K, value: BeetsConfig[K]) => {
    // Type assertion needed due to react-hook-form's complex typing
    setValue(key, value as any, { shouldDirty: true })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error) {
    return (
      <Card>
        <CardContent className="py-12">
          <div className="flex flex-col items-center justify-center text-center">
            <AlertTriangle className="h-12 w-12 text-destructive mb-4" />
            <h3 className="text-lg font-medium mb-2">Failed to load configuration</h3>
            <p className="text-sm text-muted-foreground">
              {error instanceof Error ? error.message : 'Unknown error'}
            </p>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <>
      <Card>
        <CardHeader>
          {/* Stack title + actions vertically on narrow viewports so the Save
              Configuration button doesn't crush the heading to two lines. */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2 min-w-0">
              <Settings className="h-5 w-5 flex-shrink-0" />
              <div className="min-w-0">
                <CardTitle>Beets Configuration</CardTitle>
                <CardDescription className="mt-1">
                  Edit the beets configuration for <strong>{library.name}</strong>
                </CardDescription>
              </div>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {isDirty && (
                <span className="text-sm text-amber-600 dark:text-amber-400">
                  Unsaved changes
                </span>
              )}
              {saveSuccess && !isDirty && (
                <span className="text-sm text-green-600 dark:text-green-400 flex items-center gap-1">
                  <CheckCircle className="h-4 w-4" />
                  Saved
                </span>
              )}
              <Button
                type="button"
                variant="outline"
                onClick={handleDiscard}
                disabled={!isDirty || updateConfigMutation.isPending}
              >
                Discard
              </Button>
              <Button
                onClick={handleSubmit(onSubmit, onInvalid)}
                disabled={!isDirty || updateConfigMutation.isPending}
              >
                {updateConfigMutation.isPending && (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                )}
                <span className="hidden sm:inline">Save Configuration</span>
                <span className="sm:hidden">Save</span>
              </Button>
            </div>
          </div>
        </CardHeader>

        <CardContent>
          <form onSubmit={handleSubmit(onSubmit, onInvalid)}>
            <Tabs defaultValue="general" className="w-full">
              <TabsList className="grid w-full grid-cols-5">
                <TabsTrigger value="general">General</TabsTrigger>
                <TabsTrigger value="plugins">Plugins</TabsTrigger>
                <TabsTrigger value="paths">Paths</TabsTrigger>
                <TabsTrigger value="import">Import</TabsTrigger>
                <TabsTrigger value="convert">Convert</TabsTrigger>
              </TabsList>

              <ScrollArea className="mt-4 h-[calc(100vh-320px)] min-h-[400px]">
                {/* The radix ScrollArea root has overflow-hidden, which clips
                    the focus ring (ring-2 + ring-offset-2 = 4px outside) of
                    any input that sits flush against the edge. Pad px-2 so
                    the ring on either side stays inside the visible area;
                    pr-4 keeps room for the vertical scrollbar. */}
                <div className="px-2 pr-4 pb-4">
                  <TabsContent value="general" className="mt-0">
                    <GeneralSettingsSection form={form} libraryId={library.id} />
                  </TabsContent>

                  <TabsContent value="plugins" className="mt-0">
                    <PluginManager
                      plugins={plugins}
                      onChange={(newPlugins) => setValue('plugins', newPlugins, { shouldDirty: true })}
                      config={configValues}
                      onConfigChange={handleConfigChange}
                      libraryId={library.id}
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

            {validationError && (
              <div className="mt-4 p-3 text-sm text-destructive bg-destructive/10 rounded-md border border-destructive/20">
                {validationError}
              </div>
            )}
            {updateConfigMutation.isError && (
              <div className="mt-4 p-3 text-sm text-destructive bg-destructive/10 rounded-md border border-destructive/20">
                {updateConfigMutation.error instanceof Error
                  ? updateConfigMutation.error.message
                  : 'Failed to save configuration'}
              </div>
            )}
          </form>
        </CardContent>
      </Card>

      {/* Unsaved Changes Dialog */}
      <UnsavedChangesDialog
        open={isBlocked}
        onStay={resetBlocker}
        onLeave={proceed}
      />
    </>
  )
}
