// Application state and the indexes derived from one /tree response.
//
// The whole tree arrives as a flat array. We build parent/child indexes once and
// keep everything in memory, which is why searching and tag filtering feel
// instant -- no request per keystroke.

export const state = {
  projects: [],
  projectId: null,
  project: null,

  nodes: [],                 // flat, already in depth-first display order
  byId: new Map(),           // id -> node
  childrenOf: new Map(),     // parentId (or 'root') -> [node]
  tagsByNode: new Map(),     // id -> [effective tag]
  attachmentCounts: new Map(),
  tags: [],
  members: [],

  expanded: new Set(),
  selectedId: null,

  filter: {
    query: '',
    tags: new Set(),         // slugs
    tagMode: 'any',          // any | all
    status: '',
    assigneeId: '',
    includeDescendants: false,
    mode: 'isolate',         // isolate | highlight
  },
};

export const ROOT = 'root';

export function loadTree(payload) {
  state.project = payload.project;
  state.nodes = payload.nodes;
  state.tags = payload.tags;
  state.members = payload.members;

  state.byId = new Map(payload.nodes.map((n) => [n.id, n]));

  state.childrenOf = new Map();
  for (const node of payload.nodes) {
    const key = node.parent_id ?? ROOT;
    if (!state.childrenOf.has(key)) state.childrenOf.set(key, []);
    state.childrenOf.get(key).push(node);
  }

  // JSON object keys are strings; normalize to numbers so lookups by node.id work.
  state.tagsByNode = new Map(
    Object.entries(payload.tags_by_node).map(([k, v]) => [Number(k), v])
  );
  state.attachmentCounts = new Map(
    Object.entries(payload.attachment_counts).map(([k, v]) => [Number(k), v])
  );

  // First load: open the root and its immediate children so the page is not
  // a single collapsed line.
  if (state.expanded.size === 0) {
    for (const node of payload.nodes) {
      if (node.depth <= 1) state.expanded.add(node.id);
    }
  }
}

export const childrenOf = (id) => state.childrenOf.get(id ?? ROOT) || [];
export const roots = () => childrenOf(ROOT);
export const tagsOf = (id) => state.tagsByNode.get(id) || [];

export function ancestorsOf(node) {
  // The path already encodes the ancestors: '/1/7/23/' -> [1, 7].
  return node.path.split('/').filter(Boolean).map(Number).slice(0, -1);
}

export function isFilterActive() {
  const f = state.filter;
  return Boolean(f.query || f.tags.size || f.status || f.assigneeId);
}

export function memberName(id) {
  const m = state.members.find((x) => x.id === id);
  return m ? m.name : '';
}
