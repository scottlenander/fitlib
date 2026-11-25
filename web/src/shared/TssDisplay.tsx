import * as f from './format'
import { tssMarks, tssNotes, type TssFigures } from './tss'

// A ride's TSS in a table: "HR" when from heart rate, "*" when its FTP or threshold heart
// rate is worked out rather than set, each explained on hover and by <TssNotes>.
export function TssValue({ ride }: { ride: TssFigures }) {
  const marks = tssMarks(ride)
  return (
    <>
      {f.tss(ride.tss)}
      {marks.fromHeartRate && (
        <>
          {' '}
          <abbr title="TSS from heart rate (no power)">HR</abbr>
        </>
      )}
      {marks.estimated && (
        <abbr
          title={
            marks.fromHeartRate
              ? 'Threshold heart rate not set: from your rides or your age'
              : 'TSS from an estimated FTP'
          }
        >
          *
        </abbr>
      )}
    </>
  )
}

// The footnotes for the marks <TssValue> used in a table, if any.
export function TssNotes({ rides }: { rides: TssFigures[] }) {
  return (
    <>
      {tssNotes(rides).map((note) => (
        <p key={note} className="footnote">
          {note}
        </p>
      ))}
    </>
  )
}
