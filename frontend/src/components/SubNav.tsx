import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/utils'

export interface SubNavItem {
  label: string
  to: string
}

interface SubNavProps {
  items: SubNavItem[]
  basePath: string
  collapsed?: boolean
  /** Optional callback when a link is clicked */
  onLinkClick?: () => void
}

/**
 * SubNav component for rendering sub-navigation items.
 * This is now primarily used for mobile navigation since the Sidebar
 * renders inline sub-navigation directly.
 */
export default function SubNav({ items, basePath, collapsed = false, onLinkClick }: SubNavProps) {
  if (collapsed) {
    return null
  }

  return (
    <nav className="space-y-1">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={`${basePath}/${item.to}`}
          onClick={onLinkClick}
          className={({ isActive }) =>
            cn(
              'flex h-9 items-center gap-3 rounded-md px-3 text-sm transition-colors',
              isActive
                ? 'bg-accent text-accent-foreground font-medium'
                : 'text-muted-foreground hover:bg-accent/50 hover:text-accent-foreground'
            )
          }
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  )
}
