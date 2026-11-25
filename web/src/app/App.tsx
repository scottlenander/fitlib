import { useState } from 'react'
import { Route, Routes } from 'react-router'
import { Layout } from './Layout'
import { BikesPage } from '../bikes/BikesPage'
import { ComparePage } from '../compare/ComparePage'
import { ImportPage } from '../imports/ImportPage'
import { LibraryPage } from '../library/LibraryPage'
import { NotFoundPage } from './NotFoundPage'
import { RidePage } from '../ride/RidePage'
import { SettingsPage } from '../settings/SettingsPage'
import { Stopped } from './Stopped'
import { StoppedContext } from './quitContext'
import { TrendsPage } from '../trends/TrendsPage'

export function App() {
  const [stopped, setStopped] = useState(false)
  if (stopped) return <Stopped />
  return (
    <StoppedContext value={() => setStopped(true)}>
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
    </StoppedContext>
  )
}
