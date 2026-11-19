import { Route, Routes } from 'react-router'
import { Layout } from './components/Layout'
import { BikesPage } from './pages/BikesPage'
import { ComparePage } from './pages/ComparePage'
import { ImportPage } from './pages/ImportPage'
import { LibraryPage } from './pages/LibraryPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { RidePage } from './pages/RidePage'
import { SettingsPage } from './pages/SettingsPage'
import { TrendsPage } from './pages/TrendsPage'

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<LibraryPage />} />
        <Route path="rides/:id" element={<RidePage />} />
        <Route path="compare" element={<ComparePage />} />
        <Route path="trends" element={<TrendsPage />} />
        <Route path="import" element={<ImportPage />} />
        <Route path="bikes" element={<BikesPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
