import LibraryForm from '@/components/LibraryForm'

import type { Library } from '@/api/libraries'

// ============================================================================
// Settings Tab Component
// ============================================================================

interface SettingsTabProps {
  library: Library
  onSuccess?: () => void
}

export default function SettingsTab({ library, onSuccess }: SettingsTabProps) {
  return (
    <LibraryForm
      library={library}
      mode="edit"
      hideBackButton
      onSuccess={onSuccess}
    />
  )
}
