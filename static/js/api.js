// Thin wrapper around fetch. Every call returns parsed JSON or throws an Error
// carrying the API's own message, so the UI can surface something useful.

async function request(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body.detail) {
        // FastAPI validation errors arrive as a list of {loc, msg}.
        message = Array.isArray(body.detail)
          ? body.detail.map((d) => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`).join('; ')
          : body.detail;
      }
    } catch { /* non-JSON error body; keep the status line */ }
    throw new Error(message);
  }
  return res.status === 204 ? null : res.json();
}

const json = (method) => (url, body) =>
  request(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

const post = json('POST');
const patch = json('PATCH');

export const api = {
  listProjects: () => request('/api/projects'),
  createProject: (payload) => post('/api/projects', payload),
  cloneProject: (payload) => post('/api/projects/clone', payload),
  getTree: (projectId) => request(`/api/projects/${projectId}/tree`),

  getNode: (id) => request(`/api/nodes/${id}`),
  createNode: (payload) => post('/api/nodes', payload),
  updateNode: (id, payload) => patch(`/api/nodes/${id}`, payload),
  moveNode: (id, payload) => post(`/api/nodes/${id}/move`, payload),
  duplicateNode: (id, payload) => post(`/api/nodes/${id}/duplicate`, payload),
  deleteNode: (id) => request(`/api/nodes/${id}`, { method: 'DELETE' }),

  listTags: () => request('/api/tags'),
  createTag: (payload) => post('/api/tags', payload),
  addTag: (nodeId, payload) => post(`/api/nodes/${nodeId}/tags`, payload),
  removeTag: (nodeId, tagId) =>
    request(`/api/nodes/${nodeId}/tags/${tagId}`, { method: 'DELETE' }),

  // Multipart: do NOT set Content-Type by hand, the browser must add the boundary.
  upload: (nodeId, file, extra = {}) => {
    const form = new FormData();
    form.append('node_id', nodeId);
    form.append('file', file);
    Object.entries(extra).forEach(([k, v]) => v != null && form.append(k, v));
    return request('/api/attachments', { method: 'POST', body: form });
  },
  listAttachments: (nodeId, includeOld = false) =>
    request(`/api/attachments?node_id=${nodeId}&include_old_versions=${includeOld}`),
  deleteAttachment: (id) => request(`/api/attachments/${id}`, { method: 'DELETE' }),
};
