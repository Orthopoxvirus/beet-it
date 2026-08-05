import { useOutletContext, useNavigate } from 'react-router-dom'
import { SettingsTab } from '@/components/library'
import type { LibraryDetailContext } from '../LibraryDetailLayout'

export default function LibrarySettingsPage() {
  const { library } = useOutletContext<LibraryDetailContext>()
  const navigate = useNavigate()

  const handleSuccess = () => {
    // Navigate back to albums after successful save
    navigate(`/libraries/${library.slug}/albums`)
  }

  return <SettingsTab library={library} onSuccess={handleSuccess} />
}
