import type { ProjectSummary } from '../api/types'

interface Props {
  projects: ProjectSummary[]
  projectId: number | null
  onSwitch: (id: number) => void
  onNew: () => void
  onClone: () => void
}

export function TopBar({ projects, projectId, onSwitch, onNew, onClone }: Props) {
  return (
    <header className="topbar">
      <div className="brand">
        <svg viewBox="0 0 48 48" width="26" height="26" aria-hidden="true">
          <path
            d="M6 34 L18 12 L26 24 L34 14 L42 34 Z"
            fill="none"
            stroke="currentColor"
            strokeWidth="3"
            strokeLinejoin="round"
          />
          <circle cx="16" cy="38" r="4" fill="currentColor" />
          <circle cx="34" cy="38" r="4" fill="currentColor" />
        </svg>
        <span>
          Pit <em>Box</em>
        </span>
      </div>

      <select
        className="input"
        aria-label="Select project"
        value={projectId ?? ''}
        onChange={(e) => onSwitch(Number(e.target.value))}
      >
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.season ? `${p.name} (${p.season})` : p.name}
          </option>
        ))}
      </select>

      <div className="topbar-actions">
        <button type="button" className="btn" onClick={onNew} title="Create a new tree">
          + New Tree
        </button>
        <button
          type="button"
          className="btn"
          onClick={onClone}
          title="Start next year from this car"
          disabled={projectId == null}
        >
          Clone
        </button>
        <a
          className="btn"
          href={projectId == null ? '#' : `/api/projects/${projectId}/export.csv`}
          title="Download the BOM as CSV"
        >
          Export CSV
        </a>
        <a className="btn btn-ghost" href="/docs" target="_blank" rel="noopener">
          API
        </a>
      </div>
    </header>
  )
}
