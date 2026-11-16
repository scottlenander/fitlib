import { Route, Routes } from 'react-router'
import { Layout } from './components/Layout'
import { BikesPage } from './pages/BikesPage'
import { ImportPage } from './pages/ImportPage'
import { LibraryPage } from './pages/LibraryPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { RidePage } from './pages/RidePage'
import { SettingsPage } from './pages/SettingsPage'

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<LibraryPage />} />
        <Route path="rides/:id" element={<RidePage />} />
        <Route path="import" element={<ImportPage />} />
        <Route path="bikes" element={<BikesPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
