import { useOutletContext } from 'react-router-dom'
import { BatchEditTab } from '@/components/library'
import type { LibraryDetailContext } from '../LibraryDetailLayout'

export default function LibraryBatchEditPage() {
  const { library } = useOutletContext<LibraryDetailContext>()

  return <BatchEditTab library={library} />
}
