import type { ProjectSummary } from '../api/types'
import { Wordmark } from './Wordmark'

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
      {/* The same mark as the public pages — one component, so the app and
          the landing page cannot drift apart. */}
      <div className="brand">
        <Wordmark />
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
