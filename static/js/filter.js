// Tree filtering.
//
// THE CORE PROBLEM: a tree filter is not a list filter. If someone filters for
// "Pending Machining" and the only match is a bracket five levels down, showing
// just that bracket throws away the context that tells you what it belongs to --
// and there is no valid tree to render, because the row has no visible parent.
//
// So we compute three sets:
//
//   matched  -- nodes that genuinely satisfy the filter
//   context  -- ancestors of matches, shown dimmed purely as scaffolding
//   visible  -- matched + context (+ descendants, if "+ subtree" is on)
//
// and then offer two ways to look at the result:
//
//   isolate    -- render only `visible`. The tree collapses down to the branches
//                 that matter. Best for "show me everything I still owe."
//   highlight  -- render the whole tree, dim anything not matched. Best for
//                 "where in the car does the electrical work actually live?"
//
// Everything is a Set of ids so the renderer can answer "should I draw this?"
// in O(1) per row.

import { state, tagsOf, ancestorsOf, isFilterActive } from './state.js';

function matchesText(node, needle) {
  if (!needle) return true;
  return [node.name, node.part_number, node.description, node.vendor, node.material]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
    .includes(needle);
}

function matchesTags(node, wanted, mode) {
  if (wanted.size === 0) return true;
  // tagsOf() returns EFFECTIVE tags -- a part inherits the tags cascading from
  // its branch, so filtering for "Electrical" finds every connector under the
  // Electrical subsystem without anyone having tagged them one by one.
  const slugs = new Set(tagsOf(node.id).map((t) => t.slug));
  if (mode === 'all') {
    for (const slug of wanted) if (!slugs.has(slug)) return false;
    return true;
  }
  for (const slug of wanted) if (slugs.has(slug)) return true;
  return false;
}

function matchesNode(node, f) {
  if (f.status && node.status !== f.status) return false;
  if (f.assigneeId && String(node.assignee_id) !== String(f.assigneeId)) return false;
  if (!matchesText(node, f.query)) return false;
  if (!matchesTags(node, f.tags, f.tagMode)) return false;
  return true;
}

export function computeVisibility() {
  const f = state.filter;
  const matched = new Set();
  const context = new Set();
  const visible = new Set();

  if (!isFilterActive()) {
    // No filter: everything is visible and nothing is specially marked.
    for (const node of state.nodes) visible.add(node.id);
    return { matched, context, visible, active: false };
  }

  for (const node of state.nodes) {
    if (matchesNode(node, f)) matched.add(node.id);
  }

  for (const id of matched) {
    visible.add(id);
    const node = state.byId.get(id);
    for (const ancestorId of ancestorsOf(node)) {
      if (!matched.has(ancestorId)) context.add(ancestorId);
      visible.add(ancestorId);
    }
  }

  if (f.includeDescendants && matched.size) {
    // "Show me this whole branch." Prefix-match on the materialized path, the
    // same trick the backend uses -- string startsWith instead of walking.
    const prefixes = [...matched].map((id) => state.byId.get(id).path);
    for (const node of state.nodes) {
      if (visible.has(node.id)) continue;
      if (prefixes.some((p) => node.path.startsWith(p))) {
        visible.add(node.id);
        context.add(node.id);
      }
    }
  }

  return { matched, context, visible, active: true };
}

// When a filter is on, matches buried in collapsed branches would be invisible.
// Auto-open every ancestor of a match so results are actually on screen.
export function expandToMatches(matched) {
  for (const id of matched) {
    const node = state.byId.get(id);
    if (!node) continue;
    for (const ancestorId of ancestorsOf(node)) state.expanded.add(ancestorId);
  }
}
