import { useState, useEffect } from 'react'
import { Link, useLocation, NavLink, useNavigate } from 'react-router-dom'
import { Library, Upload, Settings, Menu } from "lucide-react"
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import LibrarySelectorDropdown from '@/components/LibrarySelectorDropdown'
import ImportModeMenuIcon from '@/components/ImportModeMenuIcon'
import { useActiveLibrary } from '@/contexts/ActiveLibraryContext'
import { getTabMemory, setTabMemory } from '@/hooks/useTabMemory'
import { cn } from '@/lib/utils'

interface SubNavItem {
  label: string
  to: string
}

interface NavItem {
  to: string
  icon: React.ElementType
  label: string
  subNav?: SubNavItem[]
  section?: 'library' | 'import'
}

const librarySubNavItems: SubNavItem[] = [
  { label: 'Albums', to: 'albums' },
  { label: 'Titles', to: 'titles' },
  { label: 'Batch Edit', to: 'batch-edit' },
  { label: 'Beets Config', to: 'beets-config' },
  { label: 'Download Center', to: 'downloads' },
  { label: 'Maintenance', to: 'maintenance' },
  { label: 'Settings', to: 'settings' },
]

const importSubNavItems: SubNavItem[] = [
  { label: 'Beets', to: 'beets' },
  { label: 'Upload', to: 'upload' },
]

const navItems: NavItem[] = [
  { to: '/libraries', icon: Library, label: 'Library', subNav: librarySubNavItems, section: 'library' },
  { to: '/import', icon: Upload, label: 'Import', subNav: importSubNavItems, section: 'import' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

interface MobileNavProps {
  headerTitle: string
}

export default function MobileNav({ headerTitle }: MobileNavProps) {
  const [open, setOpen] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const { activeLibrary } = useActiveLibrary()

  // Update tab memory when navigating to a sub-tab
  useEffect(() => {
    const libraryMatch = location.pathname.match(/^\/libraries\/[^/]+\/([^/]+)/)
    const importMatch = location.pathname.match(/^\/import\/[^/]+\/([^/]+)/)

    if (libraryMatch) {
      setTabMemory('library', libraryMatch[1])
    } else if (importMatch) {
      setTabMemory('import', importMatch[1])
    }
  }, [location.pathname])

  const isActive = (path: string) => {
    if (path === '/libraries') {
      return location.pathname === '/libraries' || location.pathname.startsWith('/libraries/')
    }
    if (path === '/import') {
      return location.pathname === '/import' || location.pathname.startsWith('/import/')
    }
    return location.pathname === path || location.pathname.startsWith(path + '/')
  }

  const handleLinkClick = () => {
    setOpen(false)
  }

  const handleMainNavClick = (item: NavItem, e: React.MouseEvent) => {
    if (!item.section || !activeLibrary) return

    e.preventDefault()
    const tab = getTabMemory(item.section)
    const basePath = item.to === '/libraries' ? '/libraries' : '/import'
    navigate(`${basePath}/${activeLibrary.slug}/${tab}`)
    setOpen(false)
  }

  const getSubNavBasePath = (item: NavItem) => {
    if (!activeLibrary) return item.to
    const basePath = item.to === '/libraries' ? '/libraries' : '/import'
    return `${basePath}/${activeLibrary.slug}`
  }

  return (
    <>
      {/* Mobile Header Bar */}
      <header className="fixed left-0 right-0 top-0 z-40 flex h-16 items-center gap-4 border-b bg-background px-4">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setOpen(true)}
          aria-label="Open menu"
        >
          <Menu className="h-6 w-6" />
        </Button>
        <Link to="/" className="flex items-center gap-2 font-bold text-lg">
          <img src="/beet-logo.svg" alt="" className="h-7 w-7" />
          <span className="truncate">{headerTitle}</span>
        </Link>
      </header>

      {/* Slide-out Sheet Menu */}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="w-64 p-0 overflow-y-auto">
          <SheetHeader className="h-16 flex-row items-center border-b pl-4 pr-14">
            <SheetTitle className="flex items-center gap-3 text-left">
              <img src="/beet-logo.svg" alt="" className="h-7 w-7 shrink-0" />
              <span>beet it</span>
            </SheetTitle>
          </SheetHeader>
          <nav className="flex flex-col space-y-1 p-2">
            {/* Library Selector Dropdown */}
            <div className="mb-3">
              <LibrarySelectorDropdown onSelect={handleLinkClick} />
            </div>

            {navItems.map((item) => {
              const Icon = item.icon
              const active = isActive(item.to)
              const hasSubNav = item.subNav && item.subNav.length > 0
              const basePath = hasSubNav ? getSubNavBasePath(item) : item.to

              return (
                <div key={item.to}>
                  {/* Main nav item */}
                  {hasSubNav && activeLibrary ? (
                    <button
                      onClick={(e) => handleMainNavClick(item, e)}
                      className={cn(
                        'flex h-12 w-full items-center gap-3 rounded-md px-3 transition-colors',
                        active
                          ? 'bg-primary text-primary-foreground'
                          : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                      )}
                    >
                      <Icon className="h-5 w-5 shrink-0" />
                      <span>{item.label}</span>
                      {item.to === '/import' && activeLibrary && (
                        <ImportModeMenuIcon
                          librarySlug={activeLibrary.slug}
                          side="bottom"
                          className="ml-auto"
                        />
                      )}
                    </button>
                  ) : (
                    <Link
                      to={item.to}
                      onClick={handleLinkClick}
                      className={cn(
                        'flex h-12 items-center gap-3 rounded-md px-3 transition-colors',
                        active
                          ? 'bg-primary text-primary-foreground'
                          : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                      )}
                    >
                      <Icon className="h-5 w-5 shrink-0" />
                      <span>{item.label}</span>
                    </Link>
                  )}

                  {/* Inline sub-navigation */}
                  {hasSubNav && activeLibrary && (
                    <div className="ml-4 mt-1 space-y-1 border-l pl-3">
                      {item.subNav!.map((subItem) => (
                        <NavLink
                          key={subItem.to}
                          to={`${basePath}/${subItem.to}`}
                          onClick={handleLinkClick}
                          className={({ isActive: isSubActive }) =>
                            cn(
                              'flex h-10 items-center rounded-md px-2 text-sm transition-colors',
                              isSubActive
                                ? 'bg-accent text-accent-foreground font-medium'
                                : 'text-muted-foreground hover:bg-accent/50 hover:text-accent-foreground'
                            )
                          }
                        >
                          {subItem.label}
                        </NavLink>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </nav>
        </SheetContent>
      </Sheet>
    </>
  )
}
