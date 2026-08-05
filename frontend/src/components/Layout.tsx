import { useState, useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { useLibrary } from '@/hooks/useLibraries'
import Sidebar, { getSidebarCollapsed, setSidebarCollapsed } from './Sidebar'
import MobileNav from './MobileNav'
import { cn } from '@/lib/utils'

export default function Layout() {
  const location = useLocation()
  const [sidebarCollapsed, setSidebarCollapsedState] = useState(getSidebarCollapsed)

  // Sync collapsed state to localStorage
  useEffect(() => {
    setSidebarCollapsed(sidebarCollapsed)
  }, [sidebarCollapsed])

  const handleToggleCollapse = () => {
    setSidebarCollapsedState((prev) => !prev)
  }

  // Detect library detail pages via route matching
  const librarySlugMatch = location.pathname.match(/^\/libraries\/([^/]+)$/)
  const librarySlug = librarySlugMatch?.[1]

  // Detect import detail pages via route matching
  const importSlugMatch = location.pathname.match(/^\/import\/([^/]+)$/)
  const importSlug = importSlugMatch?.[1]

  // Determine which slug to use for fetching library data
  const slug = librarySlug || importSlug

  // Fetch library data when on a library detail page or import detail page (exclude 'create')
  const { data: library } = useLibrary(slug || '', {
    enabled: !!slug && slug !== 'create',
  })

  // Build header title
  let headerTitle = 'beet it'
  if (library) {
    if (importSlug) {
      headerTitle = `Import: ${library.name}`
    } else if (librarySlug) {
      headerTitle = `Library: ${library.name}`
    }
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Desktop Sidebar - hidden below lg breakpoint */}
      <div className="hidden lg:block">
        <Sidebar
          collapsed={sidebarCollapsed}
          onToggleCollapse={handleToggleCollapse}
        />
      </div>

      {/* Mobile Navigation - visible below lg breakpoint */}
      <div className="lg:hidden">
        <MobileNav headerTitle={headerTitle} />
      </div>

      {/* Main Content Area */}
      <main
        className={cn(
          'transition-all duration-300 ease-in-out',
          // Desktop: shift content based on sidebar state
          'lg:ml-60',
          sidebarCollapsed && 'lg:ml-16',
          // Mobile: add top padding for fixed header
          'pt-16 lg:pt-0'
        )}
      >
        <div className="container mx-auto px-4 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
