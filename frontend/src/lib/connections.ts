import type { Member, TreeNode } from '../api/types'
import { tagsOf, type TreeIndex } from './tree'
import { STATUS_LABELS } from './format'

/**
 * Connections are the second, non-hierarchical relationship in the tree.
 *
 * The left side of the view shows parentage. This shows the other thing people
 * actually need: "which parts, anywhere in the car, share this property?" Two
 * items both tagged Electrical are connected even though one lives under
 * Drivetrain and the other under Ergonomics — that link crosses the hierarchy,
 * so it cannot be drawn with indentation and gets its own gutter on the right.
 *
 * A connection is just a shared data value. Pick the field (tag, status,
 * assignee, material, vendor, type), then pick which values to draw.
 */

export type ConnectBy =
  | 'tag'
  | 'status'
  | 'assignee'
  | 'material'
  | 'vendor'
  | 'sourcing'
  | 'node_type'

export const CONNECT_BY_LABELS: Record<ConnectBy, string> = {
  tag: 'Tag',
  status: 'Status',
  assignee: 'Assignee',
  material: 'Material',
  vendor: 'Vendor',
  sourcing: 'Make / Buy',
  node_type: 'Type',
}

export const CONNECT_BY_ORDER = Object.keys(CONNECT_BY_LABELS) as ConnectBy[]

/** Lane colours for fields that have no colour of their own (tags bring theirs). */
const LANE_PALETTE = [
  '#ff6a1a',
  '#38bdf8',
  '#a78bfa',
  '#4ade80',
  '#f472b6',
  '#facc15',
  '#2dd4bf',
  '#fb923c',
]

export interface ConnectionValue {
  /** Stable identity for this value, e.g. 'electrical' or '6061-T6'. */
  key: string
  label: string
  color: string
  nodeIds: number[]
}

export interface ConnectionGroup extends ConnectionValue {
  /** Column in the right gutter. Assigned in selection order. */
  lane: number
}

/**
 * Every value a node carries for the chosen field.
 *
 * Tags are the one multi-valued case — a node in two tag groups appears on two
 * lanes, which is correct: it really does belong to both.
 */
function valuesFor(
  index: TreeIndex,
  node: TreeNode,
  by: ConnectBy,
): { key: string; label: string; color?: string }[] {
  switch (by) {
    case 'tag':
      return tagsOf(index, node.id).map((t) => ({
        key: t.slug,
        label: t.name,
        color: t.color,
      }))
    case 'status':
      return [{ key: node.status, label: STATUS_LABELS[node.status] }]
    case 'assignee':
      return node.assignee_id == null ? [] : [{ key: `m${node.assignee_id}`, label: '' }]
    case 'material':
      return node.material ? [{ key: node.material, label: node.material }] : []
    case 'vendor':
      return node.vendor ? [{ key: node.vendor, label: node.vendor }] : []
    case 'sourcing':
      // 'na' means nobody has decided yet — not a thing worth connecting.
      return node.sourcing === 'na'
        ? []
        : [{ key: node.sourcing, label: node.sourcing === 'make' ? 'Make' : 'Buy' }]
    case 'node_type':
      return [{ key: node.node_type, label: node.node_type }]
  }
}

/**
 * All values of the chosen field that exist in this project, with the nodes
 * carrying each. Sorted by how many nodes they touch — the useful ones first.
 */
export function connectionValues(
  index: TreeIndex,
  by: ConnectBy,
  members: Member[],
): ConnectionValue[] {
  const memberNames = new Map(members.map((m) => [`m${m.id}`, m.name]))
  const buckets = new Map<string, { label: string; color?: string; nodeIds: number[] }>()

  for (const node of index.nodes) {
    for (const v of valuesFor(index, node, by)) {
      const existing = buckets.get(v.key)
      if (existing) existing.nodeIds.push(node.id)
      else buckets.set(v.key, { label: v.label, color: v.color, nodeIds: [node.id] })
    }
  }

  return [...buckets.entries()]
    .map(([key, b], i) => ({
      key,
      label: by === 'assignee' ? (memberNames.get(key) ?? 'Unknown') : b.label || key,
      color: b.color ?? LANE_PALETTE[i % LANE_PALETTE.length],
      nodeIds: b.nodeIds,
    }))
    .sort((a, b) => b.nodeIds.length - a.nodeIds.length || a.label.localeCompare(b.label))
}

/** Resolve the selected value keys into drawable lanes, in selection order. */
export function buildGroups(values: ConnectionValue[], selected: readonly string[]): ConnectionGroup[] {
  const byKey = new Map(values.map((v) => [v.key, v]))
  const groups: ConnectionGroup[] = []
  for (const key of selected) {
    const value = byKey.get(key)
    // A value can disappear when the field changes or the last node loses it.
    if (!value) continue
    groups.push({ ...value, lane: groups.length })
  }
  return groups
}

/** Every node touched by any selected group — used to auto-reveal members. */
export function connectedNodeIds(groups: ConnectionGroup[]): Set<number> {
  const ids = new Set<number>()
  for (const g of groups) for (const id of g.nodeIds) ids.add(id)
  return ids
}

export const LANE_WIDTH = 16
export const GUTTER_PAD = 14

export function gutterWidth(groups: ConnectionGroup[]): number {
  return groups.length === 0 ? 0 : groups.length * LANE_WIDTH + GUTTER_PAD
}
