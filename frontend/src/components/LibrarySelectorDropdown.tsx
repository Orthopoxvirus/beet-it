import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Layers, ChevronDown, Plus, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { useActiveLibrary } from '@/contexts/ActiveLibraryContext'
import { getTabMemory } from '@/hooks/useTabMemory'
import { cn } from '@/lib/utils'

interface LibrarySelectorDropdownProps {
  collapsed?: boolean
  onSelect?: () => void
}

export default function LibrarySelectorDropdown({
  collapsed = false,
  onSelect,
}: LibrarySelectorDropdownProps) {
  const { activeLibrary, setActiveLibrary, libraries, isLoading } = useActiveLibrary()
  const location = useLocation()
  const navigate = useNavigate()

  const handleLibrarySelect = (library: typeof activeLibrary) => {
    if (!library) return

    setActiveLibrary(library)

    // Determine which section we're in and navigate with tab memory
    const isInLibrary = location.pathname.startsWith('/libraries')
    const isInImport = location.pathname.startsWith('/import')

    if (isInLibrary) {
      const tab = getTabMemory('library')
      navigate(`/libraries/${library.slug}/${tab}`)
    } else if (isInImport) {
      const tab = getTabMemory('import')
      navigate(`/import/${library.slug}/${tab}`)
    }
    // If not in either section, just update context without navigating

    onSelect?.()
  }

  if (isLoading) {
    return (
      <div
        className={cn(
          'flex items-center rounded-md px-3 py-2 text-muted-foreground',
          collapsed ? 'justify-center' : 'gap-2'
        )}
      >
        <Layers className="h-5 w-5 animate-pulse" />
        {!collapsed && <span className="text-sm">Loading...</span>}
      </div>
    )
  }

  // Empty state - no libraries
  if (libraries.length === 0) {
    if (collapsed) {
      return (
        <Tooltip delayDuration={0}>
          <TooltipTrigger asChild>
            <Button
              variant="outline"
              size="icon"
              className="w-10 h-10"
              asChild
            >
              <Link to="/libraries/create">
                <Plus className="h-5 w-5" />
              </Link>
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={10}>
            Create Library
          </TooltipContent>
        </Tooltip>
      )
    }

    return (
      <Button variant="outline" className="w-full justify-start gap-2" asChild>
        <Link to="/libraries/create">
          <Plus className="h-4 w-4" />
          <span>Create Library</span>
        </Link>
      </Button>
    )
  }

  // Collapsed mode - icon button with dropdown
  if (collapsed) {
    return (
      <DropdownMenu>
        <Tooltip delayDuration={0}>
          <TooltipTrigger asChild>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="icon" className="w-10 h-10">
                <Layers className="h-5 w-5" />
              </Button>
            </DropdownMenuTrigger>
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={10}>
            {activeLibrary?.name || 'Select Library'}
          </TooltipContent>
        </Tooltip>
        <DropdownMenuContent side="right" align="start" className="w-56">
          <DropdownMenuLabel>Select Library</DropdownMenuLabel>
          <DropdownMenuSeparator />
          {libraries.map((library) => (
            <DropdownMenuItem
              key={library.id}
              onClick={() => handleLibrarySelect(library)}
              className="flex items-center gap-2"
            >
              {library.slug === activeLibrary?.slug && (
                <Check className="h-4 w-4" />
              )}
              <span className={cn(library.slug !== activeLibrary?.slug && 'ml-6')}>
                {library.name}
              </span>
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem asChild>
            <Link to="/libraries/create" className="flex items-center gap-2">
              <Plus className="h-4 w-4" />
              <span>Create Library</span>
            </Link>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    )
  }

  // Expanded mode - full dropdown button
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          className="w-full justify-between gap-2 px-3"
        >
          <div className="flex items-center gap-2 truncate">
            <Layers className="h-4 w-4 shrink-0" />
            <span className="truncate">{activeLibrary?.name || 'Select Library'}</span>
          </div>
          <ChevronDown className="h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-[--radix-dropdown-menu-trigger-width]">
        <DropdownMenuLabel>Select Library</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {libraries.map((library) => (
          <DropdownMenuItem
            key={library.id}
            onClick={() => handleLibrarySelect(library)}
            className="flex items-center gap-2"
          >
            {library.slug === activeLibrary?.slug && (
              <Check className="h-4 w-4" />
            )}
            <span className={cn(library.slug !== activeLibrary?.slug && 'ml-6')}>
              {library.name}
            </span>
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/libraries/create" className="flex items-center gap-2">
            <Plus className="h-4 w-4" />
            <span>Create Library</span>
          </Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
