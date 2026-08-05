import { useState, useEffect } from 'react'
import {
  Folder,
  FolderOpen,
  ChevronRight,
  ChevronDown,
  FolderPlus,
  ArrowUp,
  Loader2,
  RefreshCw,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useFilesystemBrowse, useCreateDirectory } from '@/hooks/useConfig'
import type { FilesystemEntry } from '@/types/beets-config'
import FolderCreationDialog from './FolderCreationDialog'

interface FileTreeBrowserProps {
  initialPath?: string
  onSelect: (path: string) => void
  selectedPath?: string
  showFiles?: boolean
  className?: string
}

interface FolderNodeProps {
  entry: FilesystemEntry
  isSelected: boolean
  isExpanded: boolean
  onSelect: (path: string) => void
  onToggle: (path: string) => void
  depth: number
}

function FolderNode({
  entry,
  isSelected,
  isExpanded,
  onSelect,
  onToggle,
  depth,
}: FolderNodeProps) {
  const isDirectory = entry.type === 'directory'

  return (
    <div
      className={`flex items-center gap-1 py-1 px-2 cursor-pointer rounded-sm hover:bg-accent ${
        isSelected ? 'bg-accent text-accent-foreground' : ''
      }`}
      style={{ paddingLeft: `${depth * 16 + 8}px` }}
      onClick={() => {
        if (isDirectory) {
          onSelect(entry.path)
        }
      }}
    >
      {isDirectory && (
        <button
          type="button"
          className="p-0.5 hover:bg-muted rounded"
          onClick={(e) => {
            e.stopPropagation()
            onToggle(entry.path)
          }}
        >
          {isExpanded ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
        </button>
      )}
      {isDirectory ? (
        isExpanded ? (
          <FolderOpen className="h-4 w-4 text-blue-500 shrink-0" />
        ) : (
          <Folder className="h-4 w-4 text-blue-500 shrink-0" />
        )
      ) : null}
      <span className="text-sm truncate">{entry.name}</span>
    </div>
  )
}

interface ExpandedFolderContentProps {
  path: string
  selectedPath?: string
  expandedPaths: Set<string>
  onSelect: (path: string) => void
  onToggle: (path: string) => void
  depth: number
}

function ExpandedFolderContent({
  path,
  selectedPath,
  expandedPaths,
  onSelect,
  onToggle,
  depth,
}: ExpandedFolderContentProps) {
  const { data, isLoading } = useFilesystemBrowse(path)

  if (isLoading) {
    return (
      <div
        className="flex items-center gap-2 py-1 px-2 text-muted-foreground"
        style={{ paddingLeft: `${(depth + 1) * 16 + 8}px` }}
      >
        <Loader2 className="h-3 w-3 animate-spin" />
        <span className="text-xs">Loading...</span>
      </div>
    )
  }

  if (!data || data.entries.length === 0) {
    return (
      <div
        className="py-1 px-2 text-muted-foreground text-xs italic"
        style={{ paddingLeft: `${(depth + 1) * 16 + 8}px` }}
      >
        Empty folder
      </div>
    )
  }

  const directories = data.entries.filter((e) => e.type === 'directory')

  return (
    <>
      {directories.map((entry) => (
        <div key={entry.path}>
          <FolderNode
            entry={entry}
            isSelected={selectedPath === entry.path}
            isExpanded={expandedPaths.has(entry.path)}
            onSelect={onSelect}
            onToggle={onToggle}
            depth={depth + 1}
          />
          {expandedPaths.has(entry.path) && (
            <ExpandedFolderContent
              path={entry.path}
              selectedPath={selectedPath}
              expandedPaths={expandedPaths}
              onSelect={onSelect}
              onToggle={onToggle}
              depth={depth + 1}
            />
          )}
        </div>
      ))}
    </>
  )
}

export default function FileTreeBrowser({
  initialPath,
  onSelect,
  selectedPath,
  className,
}: FileTreeBrowserProps) {
  const [currentPath, setCurrentPath] = useState(initialPath || '/')
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set())
  const [showCreateDialog, setShowCreateDialog] = useState(false)

  const { data, isLoading, error, refetch } = useFilesystemBrowse(currentPath)
  const createDirectoryMutation = useCreateDirectory()

  // Update current path when initial path changes
  useEffect(() => {
    if (initialPath) {
      setCurrentPath(initialPath)
    }
  }, [initialPath])

  const handleToggle = (path: string) => {
    const newExpanded = new Set(expandedPaths)
    if (newExpanded.has(path)) {
      newExpanded.delete(path)
    } else {
      newExpanded.add(path)
    }
    setExpandedPaths(newExpanded)
  }

  const handleSelect = (path: string) => {
    onSelect(path)
  }

  const handleNavigateUp = () => {
    if (data?.parent) {
      setCurrentPath(data.parent)
    }
  }

  const handleCreateFolder = async (name: string) => {
    await createDirectoryMutation.mutateAsync({
      path: selectedPath || currentPath,
      name,
    })
    // Refresh the current directory listing
    refetch()
    // Expand the parent folder if not already expanded
    if (selectedPath && !expandedPaths.has(selectedPath)) {
      handleToggle(selectedPath)
    }
  }

  const directories = data?.entries.filter((e) => e.type === 'directory') || []

  return (
    <div className={`border rounded-md ${className || ''}`}>
      {/* Header / Toolbar */}
      <div className="flex items-center gap-2 p-2 border-b bg-muted/30">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={handleNavigateUp}
          disabled={!data?.parent}
          title="Go to parent directory"
        >
          <ArrowUp className="h-4 w-4" />
        </Button>

        <div className="flex-1 text-sm text-muted-foreground truncate px-2">
          {currentPath}
        </div>

        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => refetch()}
          disabled={isLoading}
          title="Refresh"
        >
          <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
        </Button>

        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => setShowCreateDialog(true)}
          title="Create new folder"
        >
          <FolderPlus className="h-4 w-4" />
        </Button>
      </div>

      {/* Tree View */}
      <ScrollArea className="h-64">
        <div className="p-1">
          {isLoading && (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          )}

          {error && (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <p className="text-sm text-destructive">
                Failed to load directory
              </p>
              <Button
                type="button"
                variant="link"
                size="sm"
                onClick={() => refetch()}
              >
                Try again
              </Button>
            </div>
          )}

          {!isLoading && !error && directories.length === 0 && (
            <div className="flex items-center justify-center py-8">
              <p className="text-sm text-muted-foreground">No folders found</p>
            </div>
          )}

          {!isLoading &&
            !error &&
            directories.map((entry) => (
              <div key={entry.path}>
                <FolderNode
                  entry={entry}
                  isSelected={selectedPath === entry.path}
                  isExpanded={expandedPaths.has(entry.path)}
                  onSelect={handleSelect}
                  onToggle={handleToggle}
                  depth={0}
                />
                {expandedPaths.has(entry.path) && (
                  <ExpandedFolderContent
                    path={entry.path}
                    selectedPath={selectedPath}
                    expandedPaths={expandedPaths}
                    onSelect={handleSelect}
                    onToggle={handleToggle}
                    depth={0}
                  />
                )}
              </div>
            ))}
        </div>
      </ScrollArea>

      {/* Selected Path Display */}
      {selectedPath && (
        <div className="p-2 border-t bg-muted/30">
          <p className="text-xs text-muted-foreground">Selected:</p>
          <p className="text-sm font-mono truncate" title={selectedPath}>
            {selectedPath}
          </p>
        </div>
      )}

      {/* Create Folder Dialog */}
      <FolderCreationDialog
        open={showCreateDialog}
        onOpenChange={setShowCreateDialog}
        parentPath={selectedPath || currentPath}
        onCreateFolder={handleCreateFolder}
        isCreating={createDirectoryMutation.isPending}
      />
    </div>
  )
}
