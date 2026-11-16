// An on/off switch: a button announced as a switch, with its label as its name.
type Props = { label: string; checked: boolean; onChange: (checked: boolean) => void }

export function Switch({ label, checked, onChange }: Props) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      className="switch"
      onClick={() => onChange(!checked)}
    >
      <span className="track" aria-hidden="true" />
      {label}
    </button>
  )
}
