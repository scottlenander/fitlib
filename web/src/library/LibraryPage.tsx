import { useState } from 'react'
import { Link } from 'react-router'
import { useRides } from '../api/rides'
import { useHealth } from '../api/settings'
import { usePageTitle } from '../app/usePageTitle'
import { ConfirmDelete } from '../ride/ConfirmDelete'
import { TssNotes } from '../shared/TssDisplay'
import { useUnits } from '../shared/units'
import { BulkEditPanel } from './BulkEditPanel'
import { Filters, SearchBox } from './LibraryFilters'
import { OutdatedNotice } from './OutdatedNotice'
import { hasFilters, toQuery } from './libraryQuery'
import { Pager, RideTable } from './RideTable'
import { SelectionBar } from './SelectionBar'
import { usePicked } from './selection'
import { useLibraryNotices } from './useLibraryNotices'
import { useLibraryParams } from './useLibraryParams'

export function LibraryPage() {
  usePageTitle('Library')
  const { state, update, sortBy } = useLibraryParams()
  const rides = useRides(toQuery(state))
  const health = useHealth()
  const { units } = useUnits()
  const selection = usePicked()
  const notices = useLibraryNotices(selection)
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const page = rides.data
  const pages = page ? Math.max(1, Math.ceil(page.total / page.limit)) : 1

  return (
    <>
      <h1>Library</h1>
      <OutdatedNotice health={health.data} />
      <div aria-live="polite">
        {notices.deletedNotice && (
          <p className="notice" data-testid="deleted-notice">
            {notices.deletedNotice}
          </p>
        )}
        {notices.missingNotice && (
          <p className="notice" data-testid="missing-notice">
            {notices.missingNotice}
          </p>
        )}
      </div>
      <SearchBox key={state.q} initial={state.q} onSearch={(q) => update({ q })} />
      <Filters state={state} onChange={update} />

      {rides.isError && (
        <p role="alert" data-testid="form-error">
          Couldn't load rides: {rides.error.message}
        </p>
      )}
      {page && (
        <>
          <p data-testid="ride-count" aria-live="polite">
            {page.total === 0
              ? 'No rides found.'
              : `Showing ${page.offset + 1}–${page.offset + page.items.length} of ${page.total} ${page.total === 1 ? 'ride' : 'rides'}`}
          </p>
          {page.total === 0 && !hasFilters(state) && (
            <p>
              Your library is empty. <Link to="/import">Import some rides</Link>.
            </p>
          )}
          {page.total > 0 && (
            <SelectionBar
              picked={selection.picked}
              editing={editing}
              onEdit={() => setEditing(!editing)}
              onDelete={() => setDeleting(true)}
              onClear={selection.clear}
            />
          )}
          {deleting && selection.picked.length > 0 && (
            <ConfirmDelete
              rides={selection.picked}
              onCancel={() => setDeleting(false)}
              onMissing={notices.dropMissing}
              onDeleted={(count) => {
                selection.unselectAll(selection.picked)
                setDeleting(false)
                setEditing(false)
                notices.deleted(count)
              }}
            />
          )}
          {editing && selection.picked.length > 0 && (
            <BulkEditPanel
              ids={selection.picked.map((p) => p.id)}
              onClose={() => setEditing(false)}
              onMissing={notices.dropMissing}
            />
          )}
          {page.items.length > 0 && (
            <RideTable
              rides={page.items}
              state={state}
              units={units}
              picked={selection.picked}
              onSort={sortBy}
              onPick={selection.toggle}
              onSelect={selection.selectAll}
              onUnselect={selection.unselectAll}
            />
          )}
          <TssNotes rides={page.items} />
          {page.total > 0 && (
            <Pager
              page={state.page}
              pages={pages}
              limit={state.limit}
              onPage={(n) => update({ page: n }, true)}
              onLimit={(limit) => update({ limit })}
            />
          )}
        </>
      )}
    </>
  )
}
