import { Copy, ArrowRightLeft } from 'lucide-react'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { useLibraryConfigBySlug, getImportMode } from '@/hooks/useConfig'
import { cn } from '@/lib/utils'

interface ImportModeMenuIconProps {
  /** Library slug to fetch the import config for */
  librarySlug: string
  /** Tooltip placement — defaults to 'right' (sidebar); use 'top' on mobile */
  side?: 'top' | 'right' | 'bottom' | 'left'
  /** Optional CSS class on the icon wrapper */
  className?: string
}

const modeDisplay = {
  copy: {
    icon: Copy,
    label: 'Copy Mode',
    description: 'Original files are preserved',
  },
  move: {
    icon: ArrowRightLeft,
    label: 'Move Mode',
    description: 'Original files are removed after import',
  },
} as const

/**
 * Compact import-mode indicator for the main menu's "Import" entry.
 *
 * Shows only an icon (Copy or Move) for the active library; the descriptive
 * text is revealed on hover via tooltip. Renders nothing while the config is
 * loading, on error, or when the mode can't be determined — keeping the menu
 * calm rather than flashing a placeholder.
 */
export default function ImportModeMenuIcon({
  librarySlug,
  side = 'right',
  className,
}: ImportModeMenuIconProps) {
  const { data: config, isLoading, error } = useLibraryConfigBySlug(librarySlug)

  if (isLoading || error) return null

  const mode = getImportMode(config)
  if (mode !== 'copy' && mode !== 'move') return null

  const { icon: Icon, label, description } = modeDisplay[mode]

  return (
    <Tooltip delayDuration={0}>
      <TooltipTrigger asChild>
        <span
          className={cn('inline-flex items-center opacity-70', className)}
          data-testid={`import-mode-icon-${mode}`}
          aria-label={label}
        >
          <Icon className="h-4 w-4 shrink-0" />
        </span>
      </TooltipTrigger>
      <TooltipContent side={side} sideOffset={8}>
        <span className="font-medium">{label}</span> — {description}
      </TooltipContent>
    </Tooltip>
  )
}
