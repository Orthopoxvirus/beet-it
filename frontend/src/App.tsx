import { Routes, Route, Navigate, useParams } from 'react-router-dom'
import Layout from './components/Layout'
import { LibraryRedirect, ImportRedirect, MaintenanceRedirect } from './components/redirects'
import HomePage from './pages/HomePage'
import CreateLibraryPage from './pages/CreateLibraryPage'
import LibraryDetailLayout from './pages/LibraryDetailLayout'
import { LibraryAlbumsPage, LibraryTitlesPage, LibraryBatchEditPage, LibraryBeetsConfigPage, LibrarySettingsPage, AlbumDetailPage, LibraryDownloadCenterPage, LibraryMaintenancePage } from './pages/library'
import ImportDetailLayout from './pages/ImportDetailLayout'
import { ImportBeetsPage, ImportUploadPage } from './pages/import'
import ActivityPage from './pages/ActivityPage'
import SettingsPage from './pages/SettingsPage'

// Redirect component for legacy /edit route
function EditRedirect() {
  const { slug } = useParams<{ slug: string }>()
  return <Navigate to={`/libraries/${slug}/settings`} replace />
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<HomePage />} />

        {/* Library routes with redirect for base path */}
        <Route path="libraries" element={<LibraryRedirect />} />
        <Route path="libraries/create" element={<CreateLibraryPage />} />

        {/* Library Detail - nested routes */}
        <Route path="libraries/:slug" element={<LibraryDetailLayout />}>
          <Route index element={<Navigate to="albums" replace />} />
          <Route path="albums" element={<LibraryAlbumsPage />} />
          <Route path="albums/:albumId" element={<AlbumDetailPage />} />
          <Route path="titles" element={<LibraryTitlesPage />} />
          <Route path="batch-edit" element={<LibraryBatchEditPage />} />
          <Route path="beets-config" element={<LibraryBeetsConfigPage />} />
          <Route path="maintenance" element={<Navigate to="cover-art" replace />} />
          <Route path="maintenance/:tab" element={<LibraryMaintenancePage />} />
          <Route path="downloads" element={<LibraryDownloadCenterPage />} />
          <Route path="settings" element={<LibrarySettingsPage />} />
        </Route>

        {/* Legacy route redirect */}
        <Route path="libraries/:slug/edit" element={<EditRedirect />} />

        {/* Import routes with redirect for base path */}
        <Route path="import" element={<ImportRedirect />} />

        {/* Import Detail - nested routes */}
        <Route path="import/:slug" element={<ImportDetailLayout />}>
          <Route index element={<Navigate to="beets" replace />} />
          <Route path="beets" element={<ImportBeetsPage />} />
          <Route path="upload" element={<ImportUploadPage />} />
          {/* Legacy routes from the pre-production nav */}
          <Route path="files" element={<Navigate to="../beets" replace />} />
          <Route path="prepare" element={<Navigate to="../beets" replace />} />
        </Route>

        <Route path="activity" element={<ActivityPage />} />
        {/* Legacy global maintenance path — now library-scoped */}
        <Route path="maintenance" element={<MaintenanceRedirect />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  )
}

export default App
