import { usePageTitle } from '../app/usePageTitle'
import { AthleteSection } from './AthleteSection'
import { DisplaySwitches } from './DisplaySwitches'
import { TimeZoneSection } from './TimeZoneSection'
import { WatchedFolders } from './WatchedFolders'

export function SettingsPage() {
  usePageTitle('Settings')
  return (
    <>
      <h1>Settings</h1>
      <section aria-labelledby="display-heading">
        <h2 id="display-heading">Display</h2>
        <div className="switches" data-testid="display-settings">
          <DisplaySwitches />
        </div>
        <p className="hint">
          Remembered in this browser. The theme is also in the header, and follows your system until
          you choose one.
        </p>
      </section>
      <TimeZoneSection />
      <WatchedFolders />
      <AthleteSection />
    </>
  )
}
