import { Link, useLocation, NavLink, useNavigate } from 'react-router-dom'
import { Library, Upload, Settings, PanelLeftClose, PanelLeft, Activity } from "lucide-react"
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import LibrarySelectorDropdown from '@/components/LibrarySelectorDropdown'
import ImportModeMenuIcon from '@/components/ImportModeMenuIcon'
import { useActiveLibrary } from '@/contexts/ActiveLibraryContext'
import { useActivityCount, ACTIVITY_BADGE_CLASSES } from '@/hooks/useActivity'
import { getTabMemory, setTabMemory } from '@/hooks/useTabMemory'
import { cn } from '@/lib/utils'
import { useEffect } from 'react'

const SIDEBAR_COLLAPSED_KEY = 'sidebar-collapsed'

interface SidebarProps {
  collapsed: boolean
  onToggleCollapse: () => void
}

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
  { to: '/activity', icon: Activity, label: 'Activity' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export function getSidebarCollapsed(): boolean {
  const stored = localStorage.getItem(SIDEBAR_COLLAPSED_KEY)
  return stored === 'true'
}

export function setSidebarCollapsed(collapsed: boolean): void {
  localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(collapsed))
}

export default function Sidebar({ collapsed, onToggleCollapse }: SidebarProps) {
  const location = useLocation()
  const navigate = useNavigate()
  const { activeLibrary } = useActiveLibrary()
  const { severity: activitySeverity, badgeCount: activityBadgeCount } = useActivityCount()

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

  const handleMainNavClick = (item: NavItem, e: React.MouseEvent) => {
    if (!item.section || !activeLibrary) return

    e.preventDefault()
    const tab = getTabMemory(item.section)
    const basePath = item.to === '/libraries' ? '/libraries' : '/import'
    navigate(`${basePath}/${activeLibrary.slug}/${tab}`)
  }

  const getSubNavBasePath = (item: NavItem) => {
    if (!activeLibrary) return item.to
    const basePath = item.to === '/libraries' ? '/libraries' : '/import'
    return `${basePath}/${activeLibrary.slug}`
  }

  return (
    <aside
      className={cn(
        'fixed left-0 top-0 z-40 h-screen border-r bg-background transition-all duration-300 ease-in-out',
        collapsed ? 'w-16' : 'w-60'
      )}
    >
      <div className="flex h-full flex-col">
        {/* Branding / Logo */}
        <div className={cn(
          'flex h-16 items-center border-b px-4',
          collapsed ? 'justify-center' : 'gap-2'
        )}>
          <Link to="/" className="flex items-center gap-2">
            <img src="/beet-logo.svg" alt="" className="h-7 w-7 shrink-0" />
            {!collapsed && (
              <span className="font-bold text-lg whitespace-nowrap overflow-hidden">
                beet it
              </span>
            )}
          </Link>
        </div>

        {/* Navigation Links */}
        <nav className="flex-1 space-y-1 p-2 overflow-y-auto">
          {/* Library Selector Dropdown */}
          <div className={cn('mb-3', collapsed ? 'flex justify-center' : '')}>
            <LibrarySelectorDropdown collapsed={collapsed} />
          </div>

          {navItems.map((item) => {
            const Icon = item.icon
            const active = isActive(item.to)
            const hasSubNav = item.subNav && item.subNav.length > 0
            const basePath = hasSubNav ? getSubNavBasePath(item) : item.to

            if (collapsed) {
              return (
                <div key={item.to}>
                  <Tooltip delayDuration={0}>
                    <TooltipTrigger asChild>
                      {hasSubNav && activeLibrary ? (
                        <button
                          onClick={(e) => handleMainNavClick(item, e)}
                          className={cn(
                            'flex h-10 w-full items-center justify-center rounded-md transition-colors',
                            active
                              ? 'bg-primary text-primary-foreground'
                              : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                          )}
                        >
                          <Icon className="h-5 w-5" />
                        </button>
                      ) : (
                        <Link
                          to={item.to}
                          className={cn(
                            'relative flex h-10 w-full items-center justify-center rounded-md transition-colors',
                            active
                              ? 'bg-primary text-primary-foreground'
                              : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                          )}
                        >
                          <Icon className="h-5 w-5" />
                          {/* Activity badge in collapsed mode — colored by most severe status */}
                          {item.to === '/activity' && activitySeverity !== 'none' && (
                            <span
                              className={cn(
                                'absolute -top-0.5 -right-0.5',
                                'flex h-4 min-w-4 items-center justify-center',
                                'rounded-full px-1 text-[10px] font-semibold',
                                ACTIVITY_BADGE_CLASSES[activitySeverity]
                              )}
                            >
                              {activityBadgeCount > 9 ? '9+' : activityBadgeCount}
                            </span>
                          )}
                        </Link>
                      )}
                    </TooltipTrigger>
                    <TooltipContent side="right" sideOffset={10}>
                      {item.label}
                    </TooltipContent>
                  </Tooltip>
                </div>
              )
            }

            return (
              <div key={item.to}>
                {/* Main nav item */}
                {hasSubNav && activeLibrary ? (
                  <button
                    onClick={(e) => handleMainNavClick(item, e)}
                    className={cn(
                      'flex h-10 w-full items-center gap-3 rounded-md px-3 transition-colors',
                      active
                        ? 'bg-primary text-primary-foreground'
                        : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                    )}
                  >
                    <Icon className="h-5 w-5 shrink-0" />
                    <span className="truncate">{item.label}</span>
                    {item.to === '/import' && activeLibrary && (
                      <ImportModeMenuIcon
                        librarySlug={activeLibrary.slug}
                        side="right"
                        className="ml-auto"
                      />
                    )}
                  </button>
                ) : (
                  <Link
                    to={item.to}
                    className={cn(
                      'flex h-10 items-center gap-3 rounded-md px-3 transition-colors',
                      active
                        ? 'bg-primary text-primary-foreground'
                        : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                    )}
                  >
                    <Icon className="h-5 w-5 shrink-0" />
                    <span className="truncate flex-1">{item.label}</span>
                    {/* Activity badge — colored by most severe status */}
                    {item.to === '/activity' && activitySeverity !== 'none' && (
                      <span
                        className={cn(
                          'flex h-5 min-w-5 items-center justify-center',
                          'rounded-full px-1.5 text-xs font-semibold',
                          ACTIVITY_BADGE_CLASSES[activitySeverity]
                        )}
                      >
                        {activityBadgeCount > 99 ? '99+' : activityBadgeCount}
                      </span>
                    )}
                  </Link>
                )}

                {/* Inline sub-navigation */}
                {hasSubNav && activeLibrary && (
                  <div className="ml-4 mt-1 space-y-1 border-l pl-3">
                    {item.subNav!.map((subItem) => (
                      <NavLink
                        key={subItem.to}
                        to={`${basePath}/${subItem.to}`}
                        className={({ isActive: isSubActive }) =>
                          cn(
                            'flex h-8 items-center rounded-md px-2 text-sm transition-colors',
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

        {/* Collapse Toggle Button */}
        <div className="border-t p-2">
          {collapsed ? (
            <Tooltip delayDuration={0}>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={onToggleCollapse}
                  className="w-full"
                >
                  <PanelLeft className="h-5 w-5" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right" sideOffset={10}>
                Expand sidebar
              </TooltipContent>
            </Tooltip>
          ) : (
            <Button
              variant="ghost"
              onClick={onToggleCollapse}
              className="w-full justify-start gap-3 px-3"
            >
              <PanelLeftClose className="h-5 w-5 shrink-0" />
              <span>Collapse</span>
            </Button>
          )}
        </div>
      </div>
    </aside>
  )
}
