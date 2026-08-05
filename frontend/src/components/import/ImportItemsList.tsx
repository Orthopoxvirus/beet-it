import { useState } from 'react'
import { FileAudio, FolderOpen, RefreshCw, ChevronDown, ChevronRight } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

import { useImportItems } from '@/hooks/useScanStatus'

interface ImportItemsListProps {
  slug: string
  defaultCollapsed?: boolean
}

/** "Discovered Items" card: the items found by the last import-folder scan. */
export default function ImportItemsList({ slug, defaultCollapsed = true }: ImportItemsListProps) {
  const [isCollapsed, setIsCollapsed] = useState(defaultCollapsed)
  const { data, isLoading, error, refetch, isFetching } = useImportItems(slug, {
    limit: 50,
    itemType: null,
    status: null,
  })

  const items = data?.items || []
  const total = data?.total || 0

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <button
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="flex items-center gap-2 hover:text-foreground transition-colors"
          >
            {isCollapsed ? (
              <ChevronRight className="h-4 w-4" />
            ) : (
              <ChevronDown className="h-4 w-4" />
            )}
            <CardTitle className="text-lg">
              Discovered Items
              {total > 0 && (
                <Badge variant="secondary" className="ml-2">
                  {total.toLocaleString()}
                </Badge>
              )}
            </CardTitle>
          </button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${isFetching ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
        {data?.scanCompletedAt && (
          <p className="text-xs text-muted-foreground">
            From scan completed {new Date(data.scanCompletedAt).toLocaleString()}
          </p>
        )}
      </CardHeader>

      {!isCollapsed && (
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
            </div>
          ) : error ? (
            <div className="text-center py-8">
              <p className="text-destructive text-sm">Failed to load import items</p>
            </div>
          ) : items.length === 0 ? (
            <div className="text-center py-8">
              <FileAudio className="h-12 w-12 mx-auto text-muted-foreground/50" />
              <p className="mt-3 text-muted-foreground">
                No items found. Run a scan to discover files in the import folder.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {items.map((item) => (
                <div
                  key={item.id}
                  className="flex items-start gap-3 p-3 rounded-lg border bg-card hover:bg-muted/50 transition-colors"
                >
                  {item.itemType === 'folder' ? (
                    <FolderOpen className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
                  ) : (
                    <FileAudio className="h-5 w-5 text-primary flex-shrink-0 mt-0.5" />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium truncate" title={item.filename}>
                        {item.filename}
                      </span>
                      <Badge
                        variant={
                          item.status === 'new'
                            ? 'default'
                            : item.status === 'modified'
                            ? 'secondary'
                            : item.status === 'deleted'
                            ? 'destructive'
                            : 'outline'
                        }
                        className="text-xs flex-shrink-0"
                      >
                        {item.status}
                      </Badge>
                    </div>
                    {item.itemType === 'file' && (item.artist || item.title || item.album) && (
                      <p className="text-sm text-muted-foreground mt-1">
                        {[item.artist, item.title, item.album].filter(Boolean).join(' - ')}
                      </p>
                    )}
                    <p
                      className="text-xs text-muted-foreground mt-1 truncate"
                      title={item.directory}
                    >
                      {item.directory}
                    </p>
                  </div>
                </div>
              ))}

              {total > items.length && (
                <div className="text-center pt-4">
                  <p className="text-sm text-muted-foreground">
                    Showing {items.length} of {total.toLocaleString()} items
                  </p>
                </div>
              )}
            </div>
          )}
        </CardContent>
      )}
    </Card>
  )
}
