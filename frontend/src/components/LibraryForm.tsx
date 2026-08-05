import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { ArrowLeft, Loader2, FileText, Database, Folder, Upload, Trash2, AlertTriangle, Zap } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card'
import DeleteLibraryDialog from '@/components/DeleteLibraryDialog'

import {
  libraryCreateSchema,
  SLUG_REGEX,
  type LibraryCreate,
  type Library,
  LibraryApiError,
} from '@/api/libraries'
import { useCreateLibrary, useUpdateLibrary } from '@/hooks/useLibraries'
import { useAutoAnalyzeSetting, useSetAutoAnalyzeSetting } from '@/hooks/useBeetsAnalysis'

/**
 * Converts a string to a URL-safe slug.
 * - Converts to lowercase
 * - Replaces non-alphanumeric characters with hyphens
 * - Removes leading/trailing hyphens
 * - Collapses consecutive hyphens
 */
const slugify = (text: string): string =>
  text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')

interface LibraryFormProps {
  library?: Library
  mode: 'create' | 'edit'
  /** Hide the back button (for use in embedded contexts like tabs) */
  hideBackButton?: boolean
  /** Custom callback after successful save (if not provided, navigates to /libraries) */
  onSuccess?: () => void
  /** Custom callback when cancel is clicked (if not provided, navigates to /libraries) */
  onCancel?: () => void
}

export default function LibraryForm({ library, mode, hideBackButton = false, onSuccess, onCancel }: LibraryFormProps) {
  const navigate = useNavigate()
  const createMutation = useCreateLibrary()
  const updateMutation = useUpdateLibrary()
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  // Track if user has manually edited the slug (to disable auto-generation)
  const [slugManuallyEdited, setSlugManuallyEdited] = useState(false)

  const isEdit = mode === 'edit'
  const mutation = isEdit ? updateMutation : createMutation

  // Auto-analyze setting (only for edit mode)
  const { data: autoAnalyzeData, isLoading: isLoadingAutoAnalyze } = useAutoAnalyzeSetting(
    library?.slug ?? '',
    { enabled: isEdit && !!library?.slug }
  )
  const setAutoAnalyzeMutation = useSetAutoAnalyzeSetting(library?.slug ?? '')

  const {
    register,
    handleSubmit,
    setError,
    reset,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<LibraryCreate>({
    resolver: zodResolver(libraryCreateSchema),
    defaultValues: {
      name: library?.name || '',
      description: library?.description || '',
      slug: library?.slug || '',
    },
  })

  // Watch the name field for auto-slug generation
  const nameValue = watch('name')
  const slugValue = watch('slug')

  // Auto-generate slug from name when name changes (only if slug hasn't been manually edited)
  useEffect(() => {
    if (!slugManuallyEdited && nameValue && !isEdit) {
      const generatedSlug = slugify(nameValue)
      setValue('slug', generatedSlug, { shouldValidate: true })
    }
  }, [nameValue, slugManuallyEdited, setValue, isEdit])

  // Reset form when library data changes (for edit mode)
  useEffect(() => {
    if (library) {
      reset({
        name: library.name,
        description: library.description || '',
        slug: library.slug,
      })
      // In edit mode, start with manual edit flag true since we're loading existing slug
      setSlugManuallyEdited(true)
    }
  }, [library, reset])

  // Validate slug format for preview
  const isSlugValid = slugValue ? SLUG_REGEX.test(slugValue) : true

  const onSubmit = async (data: LibraryCreate) => {
    try {
      if (isEdit && library) {
        await updateMutation.mutateAsync({ slug: library.slug, data })
      } else {
        await createMutation.mutateAsync(data)
      }
      // Use custom callback if provided, otherwise navigate to libraries
      if (onSuccess) {
        onSuccess()
      } else {
        navigate('/libraries')
      }
    } catch (error) {
      if (error instanceof LibraryApiError) {
        if (error.code === 'SLUG_COLLISION') {
          setError('slug', {
            type: 'manual',
            message: error.message || 'This slug is already in use',
          })
        } else if (error.code === 'DUPLICATE_NAME' || error.status === 409) {
          setError('name', {
            type: 'manual',
            message: error.message || 'A library with this name already exists',
          })
        } else {
          setError('root', {
            type: 'manual',
            message: error.message,
          })
        }
      } else {
        setError('root', {
          type: 'manual',
          message: 'An unexpected error occurred. Please try again.',
        })
      }
    }
  }

  return (
    <div className={hideBackButton ? '' : 'max-w-2xl mx-auto'}>
      {!hideBackButton && (
        <Button
          variant="ghost"
          onClick={() => navigate('/libraries')}
          className="mb-6"
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Libraries
        </Button>
      )}

      <Card>
        <CardHeader>
          <CardTitle>{isEdit ? 'Edit Library' : 'Create Library'}</CardTitle>
          <CardDescription>
            {isEdit
              ? 'Update the library name and description. Paths cannot be changed.'
              : 'Create a new beets library. The system will automatically create the configuration file and directories.'}
          </CardDescription>
        </CardHeader>

        <form onSubmit={handleSubmit(onSubmit)}>
          <CardContent className="space-y-6">
            {/* Root error message */}
            {errors.root && (
              <div className="p-3 text-sm text-destructive bg-destructive/10 rounded-md border border-destructive/20">
                {errors.root.message}
              </div>
            )}

            {/* Name field */}
            <div className="space-y-2">
              <Label htmlFor="name">
                Name <span className="text-destructive">*</span>
              </Label>
              <Input
                id="name"
                placeholder="My Music Library"
                {...register('name')}
                aria-invalid={errors.name ? 'true' : 'false'}
              />
              {errors.name && (
                <p className="text-sm text-destructive">{errors.name.message}</p>
              )}
            </div>

            {/* Slug field */}
            <div className="space-y-2">
              <Label htmlFor="slug">
                Slug {!isEdit && <span className="text-muted-foreground text-xs font-normal">(auto-generated from name)</span>}
              </Label>
              <Input
                id="slug"
                placeholder="my-music-library"
                {...register('slug', {
                  onChange: () => setSlugManuallyEdited(true),
                })}
                aria-invalid={errors.slug ? 'true' : 'false'}
              />
              {errors.slug && (
                <p className="text-sm text-destructive">{errors.slug.message}</p>
              )}
              {/* Slug preview */}
              {slugValue && (
                <div className="text-xs text-muted-foreground">
                  {isSlugValid ? (
                    <span>
                      URL preview: <code className="px-1 py-0.5 bg-muted rounded">/libraries/{slugValue}</code>
                    </span>
                  ) : (
                    <span className="text-amber-600 dark:text-amber-400">
                      Slug must contain only lowercase letters, numbers, and hyphens (no leading/trailing hyphens)
                    </span>
                  )}
                </div>
              )}
            </div>

            {/* Description field */}
            <div className="space-y-2">
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                placeholder="Optional description for your library..."
                rows={3}
                {...register('description')}
              />
              {errors.description && (
                <p className="text-sm text-destructive">
                  {errors.description.message}
                </p>
              )}
            </div>

            {/* Read-only paths section (only in edit mode) */}
            {isEdit && library && (
              <div className="space-y-4 pt-4 border-t">
                <div>
                  <h3 className="text-sm font-medium text-muted-foreground">
                    Library Paths (Read-only)
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    These paths were generated when the library was created and cannot be changed.
                  </p>
                </div>

                <div className="space-y-3">
                  <div className="flex items-start gap-3 p-3 bg-muted/50 rounded-md">
                    <FileText className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-muted-foreground">Config Path</p>
                      <p className="text-sm truncate" title={library.config_path}>
                        {library.config_path}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-start gap-3 p-3 bg-muted/50 rounded-md">
                    <Database className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-muted-foreground">Database Path</p>
                      <p className="text-sm truncate" title={library.database_path}>
                        {library.database_path}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-start gap-3 p-3 bg-muted/50 rounded-md">
                    <Folder className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-muted-foreground">Library Path</p>
                      <p className="text-sm truncate" title={library.library_path}>
                        {library.library_path}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-start gap-3 p-3 bg-muted/50 rounded-md">
                    <Upload className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-muted-foreground">Import Path</p>
                      <p className="text-sm truncate" title={library.import_path}>
                        {library.import_path}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Auto-analyze after scan toggle (only in edit mode) */}
            {isEdit && library && (
              <div className="space-y-4 pt-4 border-t">
                <div>
                  <h3 className="text-sm font-medium text-muted-foreground">
                    Analysis Settings
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Configure automatic analysis behavior for this library.
                  </p>
                </div>

                <div className="flex items-center justify-between p-4 rounded-md border bg-muted/30">
                  <div className="flex items-start gap-3">
                    <Zap className="h-5 w-5 mt-0.5 text-amber-500 shrink-0" />
                    <div>
                      <Label
                        htmlFor="auto-analyze"
                        className="text-sm font-medium cursor-pointer"
                      >
                        Auto-analyze after scan
                      </Label>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Automatically enqueue analysis for all newly discovered albums when a folder scan completes.
                      </p>
                    </div>
                  </div>
                  <Switch
                    id="auto-analyze"
                    checked={autoAnalyzeData?.autoAnalyzeAfterScan ?? false}
                    disabled={isLoadingAutoAnalyze || setAutoAnalyzeMutation.isPending}
                    onCheckedChange={(checked) => {
                      setAutoAnalyzeMutation.mutate(checked)
                    }}
                    aria-label="Auto-analyze after scan"
                    data-testid="auto-analyze-toggle"
                  />
                </div>
              </div>
            )}
          </CardContent>

          <CardFooter className="flex justify-end gap-3">
            {!hideBackButton && (
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  if (onCancel) {
                    onCancel()
                  } else {
                    navigate('/libraries')
                  }
                }}
              >
                Cancel
              </Button>
            )}
            <Button type="submit" disabled={isSubmitting || mutation.isPending}>
              {(isSubmitting || mutation.isPending) && (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              )}
              {isEdit ? 'Save Changes' : 'Create Library'}
            </Button>
          </CardFooter>
        </form>
      </Card>

      {/* Danger Zone - Delete Library (only in edit mode) */}
      {isEdit && library && (
        <Card className="mt-6 border-destructive/50">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg flex items-center gap-2 text-destructive">
              <AlertTriangle className="h-5 w-5" />
              Danger Zone
            </CardTitle>
            <CardDescription>
              Irreversible and destructive actions
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between p-4 rounded-md border border-destructive/30 bg-destructive/5">
              <div>
                <h4 className="text-sm font-medium">Delete this library</h4>
                <p className="text-sm text-muted-foreground mt-1">
                  Once you delete a library, there is no going back. Please be certain.
                </p>
              </div>
              <Button
                type="button"
                variant="destructive"
                onClick={() => setDeleteDialogOpen(true)}
              >
                <Trash2 className="h-4 w-4 mr-2" />
                Delete Library
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Delete Library Dialog */}
      {isEdit && library && (
        <DeleteLibraryDialog
          library={library}
          open={deleteDialogOpen}
          onOpenChange={setDeleteDialogOpen}
          onSuccess={() => navigate('/libraries')}
        />
      )}
    </div>
  )
}
