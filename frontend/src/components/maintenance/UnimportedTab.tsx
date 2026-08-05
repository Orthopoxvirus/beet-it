import { useState } from 'react'
import {
  FolderX,
  FolderInput,
  Trash2,
  Loader2,
  Power,
  ImageIcon,
  ImagePlus,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  useUnimported,
  useEnablePlugin,
  useStrayAction,
  useStrayAsCover,
} from '@/hooks/useMaintenance'
import { getStrayPreviewUrl, type StrayGroup } from '@/api/maintenance'
import { getAlbumCoverUrl } from '@/api/albums'

interface UnimportedTabProps {
  slug: string
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

export default function UnimportedTab({ slug }: UnimportedTabProps) {
  const { data, isLoading, isError, error } = useUnimported(slug)
  const enablePlugin = useEnablePlugin(slug)
  const strayAction = useStrayAction(slug)
  const strayAsCover = useStrayAsCover(slug)
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)
  const [pendingCover, setPendingCover] = useState<string | null>(null)

  if (isLoading) {
    return (
      <p className="text-sm text-muted-foreground">Scanning for stray files…</p>
    )
  }
  if (isError) {
    return (
      <p className="text-sm text-destructive">
        {error instanceof Error ? error.message : 'Failed to load'}
      </p>
    )
  }
  if (!data) return null

  if (!data.enabled) {
    return (
      <div className="rounded-md border p-6 text-center space-y-3">
        <FolderX className="h-8 w-8 mx-auto text-muted-foreground" />
        <p className="text-sm text-muted-foreground">
          Stray-file detection uses the beets <code>unimported</code> plugin,
          which isn't enabled for this library yet.
        </p>
        <Button
          onClick={() => enablePlugin.mutate('unimported')}
          disabled={enablePlugin.isPending}
        >
          {enablePlugin.isPending ? (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          ) : (
            <Power className="h-4 w-4 mr-2" />
          )}
          Enable plugin
        </Button>
        {enablePlugin.isError && (
          <p className="text-sm text-destructive">
            {enablePlugin.error instanceof Error
              ? enablePlugin.error.message
              : 'Failed to enable plugin'}
          </p>
        )}
      </div>
    )
  }

  if (data.groups.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No stray files — the library matches the beets database.
      </p>
    )
  }

  const runAction = (group: StrayGroup, action: 'delete' | 'move_to_import') => {
    strayAction.mutate(
      { paths: group.files.map((f) => f.path), action },
      { onSettled: () => setPendingDelete(null) }
    )
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        {data.total_files} stray file{data.total_files === 1 ? '' : 's'} in{' '}
        {data.groups.length} folder{data.groups.length === 1 ? '' : 's'}.
      </p>

      {data.groups.map((group) => (
        <div key={group.folder} className="rounded-md border p-3 space-y-2">
          <div className="flex items-start justify-between gap-3">
            <div className="flex min-w-0 items-start gap-3">
              {group.album_id != null && (
                <div className="shrink-0" title="Current album cover">
                  {group.cover_version != null ? (
                    <img
                      src={getAlbumCoverUrl(
                        slug,
                        group.album_id,
                        128,
                        group.cover_version
                      )}
                      alt="Current cover"
                      className="h-12 w-12 rounded object-cover border"
                      loading="lazy"
                    />
                  ) : (
                    <div className="h-12 w-12 rounded border flex items-center justify-center text-muted-foreground">
                      <ImageIcon className="h-5 w-5" />
                    </div>
                  )}
                </div>
              )}
              <div className="min-w-0">
                <p className="text-sm font-medium truncate">
                  {group.relative_folder}
                </p>
                <p className="text-xs text-muted-foreground">
                  {group.files.length} file{group.files.length === 1 ? '' : 's'} ·{' '}
                  {formatBytes(group.total_size)} ·{' '}
                  {group.fully_untracked
                    ? 'fully untracked'
                    : 'extra files in a tracked album'}
                  {group.album_id != null && group.cover_version == null && (
                    <> · no cover yet</>
                  )}
                </p>
              </div>
            </div>
            <div className="flex shrink-0 gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={strayAction.isPending}
                onClick={() => runAction(group, 'move_to_import')}
              >
                <FolderInput className="h-4 w-4 mr-1" />
                Move to import
              </Button>
              {pendingDelete === group.folder ? (
                <>
                  <Button
                    variant="destructive"
                    size="sm"
                    disabled={strayAction.isPending}
                    onClick={() => runAction(group, 'delete')}
                  >
                    {strayAction.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      'Confirm delete'
                    )}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setPendingDelete(null)}
                  >
                    Cancel
                  </Button>
                </>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPendingDelete(group.folder)}
                >
                  <Trash2 className="h-4 w-4 mr-1" />
                  Delete
                </Button>
              )}
            </div>
          </div>
          <ul className="text-xs text-muted-foreground pl-1 space-y-1">
            {group.files.slice(0, 8).map((f) => (
              <li key={f.path} className="flex items-center gap-2 min-w-0">
                {f.is_image && (
                  <img
                    src={getStrayPreviewUrl(slug, f.path)}
                    alt={f.name}
                    className="h-10 w-10 rounded object-cover border shrink-0"
                    loading="lazy"
                  />
                )}
                <span className="truncate">
                  {f.name} · {formatBytes(f.size)}
                </span>
                {f.is_image && group.album_id != null && (
                  <span className="ml-auto shrink-0">
                    {pendingCover === f.path ? (
                      <>
                        <Button
                          variant="destructive"
                          size="sm"
                          disabled={strayAsCover.isPending}
                          onClick={() =>
                            strayAsCover.mutate(f.path, {
                              onSettled: () => setPendingCover(null),
                            })
                          }
                        >
                          {strayAsCover.isPending ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : group.cover_version != null ? (
                            'Replace cover'
                          ) : (
                            'Confirm'
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setPendingCover(null)}
                        >
                          Cancel
                        </Button>
                      </>
                    ) : (
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={strayAsCover.isPending}
                        onClick={() => setPendingCover(f.path)}
                      >
                        <ImagePlus className="h-4 w-4 mr-1" />
                        Use as cover
                      </Button>
                    )}
                  </span>
                )}
              </li>
            ))}
            {group.files.length > 8 && (
              <li>…and {group.files.length - 8} more</li>
            )}
          </ul>
        </div>
      ))}

      {strayAction.isError && (
        <p className="text-sm text-destructive">
          {strayAction.error instanceof Error
            ? strayAction.error.message
            : 'Action failed'}
        </p>
      )}
      {strayAsCover.isError && (
        <p className="text-sm text-destructive">
          {strayAsCover.error instanceof Error
            ? strayAsCover.error.message
            : 'Setting cover failed'}
        </p>
      )}
    </div>
  )
}
