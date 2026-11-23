import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import {
  useAddWatchFolder,
  useRemoveWatchFolder,
  useScanWatched,
  useWatch,
  type ScanResult,
  type WatchFolder,
  type WatchedFile,
} from '../api/client'
import * as f from '../format'
import { ScrollBox } from './ScrollBox'

// Settings: the folders whose new rides the server imports, adding and removing them, a scan
// on demand, and the latest files found. Checked every 5 s while shown, so a ride dropped
// into a folder appears here soon after it's imported.
const POLL_MS = 5_000

const STATES: Record<WatchFolder['state'], string> = {
  watching: 'Watching',
  missing: "Not found: it's watched again when it's back",
  error: "Can't be watched",
  stopped: 'Not watched: the server was started with --no-watch',
}

const OUTCOMES: Record<WatchedFile['outcome'], string> = {
  imported: 'Imported',
  duplicate: 'Already in the library',
  skipped: 'Skipped',
  failed: "Couldn't be read",
}

export function WatchedFolders() {
  const watch = useWatch(POLL_MS)
  const status = watch.data
  return (
    <section aria-labelledby="watch-heading" className="watched" data-testid="watched-folders">
      <h2 id="watch-heading">Watched folders</h2>
      <p className="hint">
        While fitlib is running, new rides in these folders are imported on their own, once each
        file has stopped changing for 10 seconds. Folders are also checked when fitlib starts and
        every 10 minutes.
      </p>
      {watch.isError && <p role="alert">Couldn't load the watched folders.</p>}
      {status && (
        <>
          {!status.running && (
            <p className="notice" data-testid="watch-stopped">
              fitlib was started with <code>--no-watch</code>, so it isn't watching. Scan now
              imports what's new.
            </p>
          )}
          <FolderList folders={status.folders} />
          <AddFolder suggestions={status.suggestions} />
          {status.folders.length > 0 && <ScanNow waiting={status.waiting} />}
          <RecentFiles files={status.recent} />
        </>
      )}
    </section>
  )
}

function FolderList({ folders }: { folders: WatchFolder[] }) {
  const remove = useRemoveWatchFolder()
  if (folders.length === 0) return <p data-testid="watch-empty">No folders are watched yet.</p>
  return (
    <>
      <ul className="watch-folders" aria-label="Watched folders">
        {folders.map((folder) => (
          <li key={folder.path} data-testid="watch-folder">
            <span className="watch-path">{folder.path}</span>{' '}
            <span className={`watch-state watch-state-${folder.state}`}>
              {STATES[folder.state]}
              {folder.message ? `: ${folder.message}` : ''}
            </span>{' '}
            <span className="muted">
              {folder.files === 1 ? '1 file found' : `${folder.files} files found`}
            </span>{' '}
            <button
              type="button"
              aria-label={`Stop watching ${folder.path}`}
              disabled={remove.isPending}
              onClick={() => remove.mutate(folder.path)}
            >
              Stop watching
            </button>
          </li>
        ))}
      </ul>
      {remove.isError && <p role="alert">{remove.error.message}</p>}
      <p className="hint">Rides already imported stay in the library when you stop watching.</p>
    </>
  )
}

function AddFolder({ suggestions }: { suggestions: string[] }) {
  const add = useAddWatchFolder()
  const [path, setPath] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    add.mutate(path, { onSuccess: () => setPath('') })
  }

  return (
    <>
      <form onSubmit={submit} className="inline-form" data-testid="watch-form">
        <label>
          Folder to watch
          <input
            type="text"
            className="watch-input"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="~/Documents/Zwift/Activities"
            spellCheck={false}
            autoComplete="off"
            required
          />
        </label>
        <button type="submit" disabled={add.isPending}>
          Watch folder
        </button>
      </form>
      <p className="hint">
        Its full path; <code>~</code> is your home folder. In Finder, hold Option and choose Copy as
        Pathname to copy a folder's path.
      </p>
      {suggestions.length > 0 && (
        <p className="suggestions">
          Found on this computer:{' '}
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              disabled={add.isPending}
              onClick={() => add.mutate(suggestion)}
            >
              Watch {suggestion}
            </button>
          ))}
        </p>
      )}
      {add.isError && (
        <p role="alert" data-testid="form-error">
          {add.error.message}
        </p>
      )}
      {add.isSuccess && (
        <p data-testid="form-notice">
          Watching {add.data.path}. Rides already in it are being imported.
        </p>
      )}
    </>
  )
}

function ScanNow({ waiting }: { waiting: number }) {
  const scan = useScanWatched()
  return (
    <>
      <p>
        <button type="button" disabled={scan.isPending} onClick={() => scan.mutate()}>
          Scan now
        </button>{' '}
        {waiting > 0 && (
          <span className="muted" data-testid="watch-waiting">
            {waiting === 1
              ? '1 file is still being written; it will be imported once it stops changing.'
              : `${waiting} files are still being written; they will be imported once they stop changing.`}
          </span>
        )}
      </p>
      {scan.isError && <p role="alert">{scan.error.message}</p>}
      {scan.data && <p data-testid="scan-result">{scanText(scan.data)}</p>}
    </>
  )
}

function scanText(result: ScanResult): string {
  if (result.background) return 'Looking for new rides in the watched folders…'
  const parts = [
    `Imported ${result.imported}`,
    `already in the library ${result.duplicates}`,
    `skipped ${result.skipped}`,
    `couldn't be read ${result.failed}`,
  ]
  const writing = result.still_writing
    ? ` ${result.still_writing} still being written: scan again shortly.`
    : ''
  return `${parts.join(', ')}.${writing}`
}

// The latest files that weren't already in the library, newest first, the rides linked.
function RecentFiles({ files }: { files: WatchedFile[] }) {
  if (files.length === 0) return null
  return (
    // Focusable, as its rows may have no links to Tab to (only failed files, say).
    <ScrollBox label="Latest files from watched folders">
      <table className="wide" data-testid="watch-recent">
        <caption>Latest files from watched folders</caption>
        <thead>
          <tr>
            <th scope="col">File</th>
            <th scope="col">When</th>
            <th scope="col">Outcome</th>
            <th scope="col">Detail</th>
          </tr>
        </thead>
        <tbody>
          {files.map((file) => (
            <tr key={file.path} data-testid="watch-file">
              <th scope="row">
                {file.outcome === 'imported' && file.ride_id ? (
                  <Link to={`/rides/${file.ride_id}`}>{file.name}</Link>
                ) : (
                  file.name
                )}
              </th>
              <td>{f.when(file.seen_at)}</td>
              <td>{OUTCOMES[file.outcome]}</td>
              <td>{file.ride_deleted ? 'Ride deleted since' : (file.detail ?? '')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollBox>
  )
}
