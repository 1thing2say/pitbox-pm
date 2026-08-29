import { useId, useState } from 'react'

import {
  CONNECT_BY_LABELS,
  CONNECT_BY_ORDER,
  type ConnectBy,
  type ConnectionValue,
} from '../lib/connections'

interface Props {
  connectBy: ConnectBy
  values: ConnectionValue[]
  selected: string[]
  onChangeField: (by: ConnectBy) => void
  onToggle: (key: string) => void
  onClear: () => void
}

/**
 * Lives in the Breakdown header. Pick a field, then search its values by name;
 * each one you add becomes a coloured lane in the right-hand gutter.
 */
export function ConnectionPicker({
  connectBy,
  values,
  selected,
  onChangeField,
  onToggle,
  onClear,
}: Props) {
  const [query, setQuery] = useState('')
  const listId = useId()

  // Only values on two or more nodes can actually connect anything.
  const connectable = values.filter((v) => v.nodeIds.length > 1)
  const selectedSet = new Set(selected)

  const commit = (raw: string) => {
    const needle = raw.trim().toLowerCase()
    if (!needle) return
    const hit =
      connectable.find((v) => v.label.toLowerCase() === needle) ??
      connectable.find((v) => v.label.toLowerCase().includes(needle))
    if (hit && !selectedSet.has(hit.key)) onToggle(hit.key)
    setQuery('')
  }

  return (
    <div className="connbar">
      <span className="filter-label">Connect by</span>

      <select
        className="input compact"
        aria-label="Connection field"
        value={connectBy}
        onChange={(e) => onChangeField(e.target.value as ConnectBy)}
      >
        {CONNECT_BY_ORDER.map((by) => (
          <option key={by} value={by}>
            {CONNECT_BY_LABELS[by]}
          </option>
        ))}
      </select>

      <input
        className="input conn-search"
        type="search"
        list={listId}
        placeholder={`Search ${CONNECT_BY_LABELS[connectBy].toLowerCase()}…`}
        aria-label="Search connection values"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value)
          // Picking from the datalist fires change with the full label.
          if (connectable.some((v) => v.label.toLowerCase() === e.target.value.trim().toLowerCase())) {
            commit(e.target.value)
          }
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            commit(query)
          }
        }}
      />
      <datalist id={listId}>
        {connectable
          .filter((v) => !selectedSet.has(v.key))
          .map((v) => (
            <option key={v.key} value={v.label}>
              {`${v.nodeIds.length} items`}
            </option>
          ))}
      </datalist>

      {selected.length > 0 && (
        <div className="conn-chips">
          {selected.map((key) => {
            const value = values.find((v) => v.key === key)
            if (!value) return null
            return (
              <button
                key={key}
                type="button"
                className="conn-chip"
                style={{ borderColor: value.color, color: value.color }}
                title="Stop drawing this connection"
                onClick={() => onToggle(key)}
              >
                <span className="conn-swatch" style={{ background: value.color }} />
                {value.label}
                <span className="count">{value.nodeIds.length}</span>
                <span aria-hidden="true">×</span>
              </button>
            )
          })}
          <button type="button" className="btn btn-sm btn-ghost" onClick={onClear}>
            Clear
          </button>
        </div>
      )}

      {selected.length === 0 && connectable.length === 0 && (
        <span className="conn-hint">No shared values on this field yet.</span>
      )}
    </div>
  )
}
