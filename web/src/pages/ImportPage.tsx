import { useState, type DragEvent, type FormEvent, type ReactNode } from 'react'
import { Link } from 'react-router'
import { useImport, type ImportResult } from '../api/client'
import { usePageTitle } from '../usePageTitle'

const ACCEPTED = /\.(fit|zip)$/i

export function ImportPage() {
  usePageTitle('Import rides')
  const [files, setFiles] = useState<File[]>([])
  const [dragging, setDragging] = useState(false)
  const upload = useImport()

  function choose(list: FileList | null) {
    setFiles(list ? [...list] : [])
    upload.reset()
  }

  function drop(event: DragEvent) {
    event.preventDefault()
    setDragging(false)
    choose(event.dataTransfer.files)
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (files.length) upload.mutate(files)
  }

  const skippedTypes = files.filter((file) => !ACCEPTED.test(file.name)).length

  return (
    <>
      <h1>Import rides</h1>
      <p>
        Add <code>.fit</code> files, or <code>.zip</code> archives such as a Garmin Connect export.
        Rides already in the library are recognised and skipped, so importing the same files again
        is safe.
      </p>
      <form onSubmit={submit} className="import-form" data-testid="import-form">
        <div
          className={dragging ? 'dropzone dragging' : 'dropzone'}
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={drop}
        >
          <label htmlFor="import-files">Choose .fit or .zip files</label>
          <input
            id="import-files"
            type="file"
            multiple
            accept=".fit,.zip"
            onChange={(e) => choose(e.target.files)}
          />
          <p className="hint">or drop them here</p>
        </div>
        {files.length > 0 && (
          <p data-testid="chosen-files">
            {files.length} {files.length === 1 ? 'file' : 'files'} chosen
            {skippedTypes > 0 && ` (${skippedTypes} not .fit or .zip)`}
          </p>
        )}
        <button type="submit" disabled={!files.length || upload.isPending}>
          {upload.isPending ? 'Importing…' : 'Import'}
        </button>
      </form>

      <div aria-live="polite">
        {upload.isError && (
          <p role="alert" data-testid="form-error">
            The import failed: {upload.error.message}
          </p>
        )}
        {upload.data && <Results result={upload.data} />}
      </div>
    </>
  )
}

function Results({ result }: { result: ImportResult }) {
  const counts = [
    `Imported ${result.imported.length}`,
    `already in library ${result.duplicates.length}`,
    `skipped ${result.skipped.length}`,
    `failed ${result.failed.length}`,
  ]
  return (
    <section aria-labelledby="results-heading" data-testid="import-results">
      <h2 id="results-heading">Results</h2>
      <p data-testid="import-summary">{counts.join(', ')}.</p>
      {result.imported.length > 0 && (
        <Outcomes title="Imported" testId="imported-files">
          {result.imported.map((o) => (
            <li key={o.file}>
              <Link to={`/rides/${o.detail}`}>{o.file}</Link>
            </li>
          ))}
        </Outcomes>
      )}
      {(
        [
          ['Already in library', 'duplicate-files', result.duplicates],
          ['Skipped', 'skipped-files', result.skipped],
          ['Failed', 'failed-files', result.failed],
        ] as const
      ).map(
        ([title, testId, outcomes]) =>
          outcomes.length > 0 && (
            <Outcomes key={title} title={title} testId={testId}>
              {outcomes.map((o) => (
                <li key={o.file}>
                  {o.file}: {title === 'Already in library' ? 'already imported' : o.detail}
                </li>
              ))}
            </Outcomes>
          ),
      )}
    </section>
  )
}

function Outcomes(props: { title: string; testId: string; children: ReactNode }) {
  return (
    <>
      <h3>{props.title}</h3>
      <ul data-testid={props.testId}>{props.children}</ul>
    </>
  )
}
