import type { Status, TreeNode } from '../api/types'
import { ancestorIds, tagsOf, type TreeIndex } from './tree'

/**
 * Tree filtering.
 *
 * THE CORE PROBLEM: a tree filter is not a list filter. If someone filters for
 * "Pending Machining" and the only match is a bracket five levels down, showing
 * just that bracket throws away the context that says what it belongs to — and
 * there is no valid tree to render, because the row has no visible parent.
 *
 * So we compute three sets:
 *   matched  — nodes that genuinely satisfy the filter
 *   context  — ancestors of matches, shown dimmed purely as scaffolding
 *   visible  — matched + context (+ descendants, when "+ subtree" is on)
 *
 * and offer two ways to look at the result:
 *   isolate    — render only `visible`; the tree collapses to what matters
 *   highlight  — render everything, dim the misses; shows WHERE matches sit
 */

export type FilterMode = 'isolate' | 'highlight'
export type TagMode = 'any' | 'all'

export interface FilterState {
  query: string
  tags: ReadonlySet<string>
  tagMode: TagMode
  status: Status | ''
  assigneeId: number | ''
  includeDescendants: boolean
  mode: FilterMode
}

export const emptyFilter: FilterState = {
  query: '',
  tags: new Set<string>(),
  tagMode: 'any',
  status: '',
  assigneeId: '',
  includeDescendants: false,
  mode: 'isolate',
}

export function isFilterActive(f: FilterState): boolean {
  return Boolean(f.query || f.tags.size || f.status || f.assigneeId !== '')
}

export interface Visibility {
  matched: Set<number>
  context: Set<number>
  visible: Set<number>
  active: boolean
}

function matchesText(node: TreeNode, needle: string): boolean {
  if (!needle) return true
  return [node.name, node.part_number, node.description, node.vendor, node.material]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
    .includes(needle)
}

function matchesTags(
  index: TreeIndex,
  node: TreeNode,
  wanted: ReadonlySet<string>,
  mode: TagMode,
): boolean {
  if (wanted.size === 0) return true
  // These are EFFECTIVE tags, so a part inherits whatever cascades from its
  // branch — filtering for "Electrical" finds every connector under the
  // Electrical subsystem without anyone tagging them one by one.
  const slugs = new Set(tagsOf(index, node.id).map((t) => t.slug))
  if (mode === 'all') {
    for (const slug of wanted) if (!slugs.has(slug)) return false
    return true
  }
  for (const slug of wanted) if (slugs.has(slug)) return true
  return false
}

function matchesNode(index: TreeIndex, node: TreeNode, f: FilterState): boolean {
  if (f.status && node.status !== f.status) return false
  if (f.assigneeId !== '' && node.assignee_id !== f.assigneeId) return false
  if (!matchesText(node, f.query)) return false
  if (!matchesTags(index, node, f.tags, f.tagMode)) return false
  return true
}

export function computeVisibility(index: TreeIndex, f: FilterState): Visibility {
  const matched = new Set<number>()
  const context = new Set<number>()
  const visible = new Set<number>()

  if (!isFilterActive(f)) {
    for (const node of index.nodes) visible.add(node.id)
    return { matched, context, visible, active: false }
  }

  for (const node of index.nodes) {
    if (matchesNode(index, node, f)) matched.add(node.id)
  }

  for (const id of matched) {
    visible.add(id)
    const node = index.byId.get(id)
    if (!node) continue
    for (const ancestorId of ancestorIds(node)) {
      if (!matched.has(ancestorId)) context.add(ancestorId)
      visible.add(ancestorId)
    }
  }

  if (f.includeDescendants && matched.size) {
    // "Show me this whole branch." Prefix-match on the materialized path — the
    // same trick the backend uses, string startsWith instead of walking.
    const prefixes = [...matched].map((id) => index.byId.get(id)?.path ?? '')
    for (const node of index.nodes) {
      if (visible.has(node.id)) continue
      if (prefixes.some((p) => p && node.path.startsWith(p))) {
        visible.add(node.id)
        context.add(node.id)
      }
    }
  }

  return { matched, context, visible, active: true }
}

/**
 * Matches buried in collapsed branches would be invisible, so every ancestor of
 * a match gets opened. Returns a new Set rather than mutating the caller's.
 */
export function expandedForMatches(
  index: TreeIndex,
  expanded: ReadonlySet<number>,
  matched: ReadonlySet<number>,
): Set<number> {
  const next = new Set(expanded)
  for (const id of matched) {
    const node = index.byId.get(id)
    if (!node) continue
    for (const ancestorId of ancestorIds(node)) next.add(ancestorId)
  }
  return next
}
