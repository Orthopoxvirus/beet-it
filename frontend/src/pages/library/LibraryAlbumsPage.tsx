import { useOutletContext } from 'react-router-dom'
import { AlbumsTab } from '@/components/library'
import type { LibraryDetailContext } from '../LibraryDetailLayout'

export default function LibraryAlbumsPage() {
  const { library } = useOutletContext<LibraryDetailContext>()

  return <AlbumsTab library={library} />
}
