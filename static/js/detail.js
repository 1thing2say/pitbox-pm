// The right-hand detail panel: metadata, tags, files.
//
// Fields save on blur (or change, for selects) rather than behind a Save button.
// In a shop, people edit one field and walk away; an unsaved form is lost work.

import { api } from './api.js';
import { state, memberName } from './state.js';
import { STATUS_LABELS } from './treeview.js';

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
};

let handlers = {};
let current = null;

export function initDetail(callbacks) {
  handlers = callbacks;
}

export function clearDetail() {
  current = null;
  const root = document.getElementById('detailRoot');
  root.className = 'detail-empty';
  root.replaceChildren(el('p', null, 'Select a part to see its details, tags and files.'));
}

const money = (cents) => (cents == null ? '' : (cents / 100).toFixed(2));

export function renderDetail(node) {
  current = node;
  const root = document.getElementById('detailRoot');
  root.className = 'detail';
  const frag = document.createDocumentFragment();

  frag.appendChild(buildBreadcrumb(node));
  frag.appendChild(buildTitle(node));
  frag.appendChild(buildRollups(node));

  frag.appendChild(el('h3', null, 'Details'));
  frag.appendChild(buildFields(node));

  frag.appendChild(el('h3', null, 'Tags'));
  frag.appendChild(buildTags(node));

  frag.appendChild(el('h3', null, `Files (${node.attachments.length})`));
  frag.appendChild(buildFiles(node));

  root.replaceChildren(frag);
}

function buildBreadcrumb(node) {
  const bar = el('div', 'breadcrumb');
  const ancestors = node.ancestor_ids
    .map((id) => state.byId.get(id))
    .filter(Boolean);
  ancestors.forEach((ancestor, i) => {
    if (i > 0) bar.appendChild(el('span', 'sep', '/'));
    const crumb = el('span', null, ancestor.name);
    crumb.addEventListener('click', () => handlers.onSelectId?.(ancestor.id));
    bar.appendChild(crumb);
  });
  if (!ancestors.length) bar.appendChild(el('span', 'sep', 'Root of this tree'));
  return bar;
}

function buildTitle(node) {
  const wrap = el('div', 'detail-title');
  const heading = el('h1', null, node.name);
  wrap.appendChild(heading);

  const addBtn = el('button', 'btn btn-sm btn-primary', '+ Child');
  addBtn.addEventListener('click', () => handlers.onAddChild?.(node));
  wrap.appendChild(addBtn);
  return wrap;
}

function buildRollups(node) {
  const wrap = el('div', 'rollups');
  const add = (label, value) => {
    const item = el('span', null, `${label} `);
    item.appendChild(el('b', null, value));
    wrap.appendChild(item);
  };
  add('Children:', String(node.child_count));
  add('In subtree:', String(node.descendant_count));
  if (node.rollup_cost_cents) add('Subtree cost:', `$${money(node.rollup_cost_cents)}`);
  if (node.rollup_mass_g) add('Subtree mass:', `${(node.rollup_mass_g / 1000).toFixed(2)} kg`);
  return wrap;
}

// --- metadata form -----------------------------------------------------------

function save(field, value) {
  api
    .updateNode(current.id, { [field]: value })
    .then((updated) => handlers.onSaved?.(updated))
    .catch((err) => handlers.onError?.(err));
}

function textField(label, field, value, { wide = false, type = 'text' } = {}) {
  const wrap = el('div', `field${wide ? ' wide' : ''}`);
  wrap.appendChild(el('label', null, label));
  const input = el('input', 'input');
  input.type = type;
  input.value = value ?? '';
  input.addEventListener('blur', () => {
    let next = input.value.trim();
    if (type === 'number') {
      if (next === '') return save(field, null);
      const num = Number(next);
      if (Number.isNaN(num)) return;
      return save(field, num);
    }
    save(field, next === '' ? null : next);
  });
  wrap.appendChild(input);
  return wrap;
}

function selectField(label, field, value, options) {
  const wrap = el('div', 'field');
  wrap.appendChild(el('label', null, label));
  const select = el('select', 'input');
  for (const [val, text] of options) {
    const opt = el('option', null, text);
    opt.value = val;
    if (String(val) === String(value ?? '')) opt.selected = true;
    select.appendChild(opt);
  }
  select.addEventListener('change', () =>
    save(field, select.value === '' ? null : select.value)
  );
  wrap.appendChild(select);
  return wrap;
}

function buildFields(node) {
  const grid = el('div', 'field-grid');

  grid.appendChild(textField('Name', 'name', node.name, { wide: true }));
  grid.appendChild(textField('Part number', 'part_number', node.part_number));
  grid.appendChild(
    selectField('Status', 'status', node.status, Object.entries(STATUS_LABELS))
  );
  grid.appendChild(
    selectField('Type', 'node_type', node.node_type, [
      ['vehicle', 'Vehicle'], ['subsystem', 'Subsystem'],
      ['assembly', 'Assembly'], ['part', 'Part'],
    ])
  );
  grid.appendChild(
    selectField('Assignee', 'assignee_id', node.assignee_id, [
      ['', 'Unassigned'],
      ...state.members.map((m) => [m.id, m.subteam ? `${m.name} (${m.subteam})` : m.name]),
    ])
  );
  grid.appendChild(
    selectField('Sourcing', 'sourcing', node.sourcing, [
      ['na', '—'], ['make', 'Make'], ['buy', 'Buy'],
    ])
  );
  grid.appendChild(textField('Quantity', 'quantity', node.quantity, { type: 'number' }));
  grid.appendChild(textField('Material', 'material', node.material));
  grid.appendChild(textField('Mass (g)', 'mass_g', node.mass_g, { type: 'number' }));
  grid.appendChild(textField('Vendor', 'vendor', node.vendor));
  grid.appendChild(
    textField('Lead time (days)', 'lead_time_days', node.lead_time_days, { type: 'number' })
  );

  // Cost is stored in integer cents; the form works in dollars.
  const costWrap = el('div', 'field');
  costWrap.appendChild(el('label', null, 'Unit cost ($)'));
  const costInput = el('input', 'input');
  costInput.type = 'number';
  costInput.step = '0.01';
  costInput.value = money(node.cost_cents);
  costInput.addEventListener('blur', () => {
    const raw = costInput.value.trim();
    if (raw === '') return save('cost_cents', null);
    const dollars = Number(raw);
    if (!Number.isNaN(dollars)) save('cost_cents', Math.round(dollars * 100));
  });
  costWrap.appendChild(costInput);
  grid.appendChild(costWrap);

  const descWrap = el('div', 'field wide');
  descWrap.appendChild(el('label', null, 'Description'));
  const textarea = el('textarea');
  textarea.value = node.description ?? '';
  textarea.addEventListener('blur', () =>
    save('description', textarea.value.trim() === '' ? null : textarea.value)
  );
  descWrap.appendChild(textarea);
  grid.appendChild(descWrap);

  return grid;
}

// --- tags --------------------------------------------------------------------

function buildTags(node) {
  const wrap = el('div');
  const list = el('div', 'tag-list');

  for (const tag of node.tags) {
    const pill = el('span', `tag-pill${tag.inherited ? ' inherited' : ''}`);
    if (tag.inherited) {
      pill.style.color = tag.color;
      const source = state.byId.get(tag.source_node_id);
      pill.title = `Inherited from ${source ? source.name : 'an ancestor'}`;
    } else {
      pill.style.background = tag.color;
    }
    pill.appendChild(document.createTextNode(tag.name));

    if (!tag.inherited) {
      const remove = el('button', null, '×');
      remove.title = 'Remove this tag';
      remove.setAttribute('aria-label', `Remove tag ${tag.name}`);
      remove.addEventListener('click', () => {
        api
          .removeTag(node.id, tag.tag_id)
          .then(() => handlers.onTagsChanged?.())
          .catch((err) => handlers.onError?.(err));
      });
      pill.appendChild(remove);
    } else {
      const jump = el('button', null, '↑');
      jump.title = 'Go to the node this tag comes from';
      jump.addEventListener('click', () => handlers.onSelectId?.(tag.source_node_id));
      pill.appendChild(jump);
    }
    list.appendChild(pill);
  }
  wrap.appendChild(list);

  // --- add a tag, with the cascade switch
  const adder = el('div', 'tag-list');
  adder.style.marginTop = '8px';

  const picker = el('select', 'input compact');
  const placeholder = el('option', null, '+ Add tag…');
  placeholder.value = '';
  picker.appendChild(placeholder);
  const assigned = new Set(node.tags.filter((t) => !t.inherited).map((t) => t.tag_id));
  for (const tag of state.tags) {
    if (assigned.has(tag.id)) continue;
    const opt = el('option', null, tag.name);
    opt.value = tag.id;
    picker.appendChild(opt);
  }

  const cascadeLabel = el('label', 'check');
  const cascadeBox = el('input');
  cascadeBox.type = 'checkbox';
  cascadeLabel.appendChild(cascadeBox);
  cascadeLabel.appendChild(el('span', null, 'apply to whole branch'));
  cascadeLabel.title =
    'Tag every node beneath this one too — including parts added later.';

  picker.addEventListener('change', () => {
    if (!picker.value) return;
    api
      .addTag(node.id, { tag_id: Number(picker.value), cascade: cascadeBox.checked })
      .then(() => handlers.onTagsChanged?.())
      .catch((err) => handlers.onError?.(err));
  });

  adder.appendChild(picker);
  adder.appendChild(cascadeLabel);
  wrap.appendChild(adder);

  if (node.tags.some((t) => t.inherited)) {
    wrap.appendChild(
      el('p', 'tag-note', 'Dashed tags are inherited from a parent branch. Remove them where they were set.')
    );
  }
  return wrap;
}

// --- files -------------------------------------------------------------------

const humanSize = (bytes) => {
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) { value /= 1024; i += 1; }
  return `${value < 10 && i > 0 ? value.toFixed(1) : Math.round(value)} ${units[i]}`;
};

function buildFiles(node) {
  const wrap = el('div');

  for (const file of node.attachments) {
    const row = el('div', 'file-row');
    row.appendChild(el('span', 'file-kind', file.kind));

    const link = el('a', 'file-name', file.filename);
    link.href = `/api/attachments/${file.id}/download`;
    link.title = 'Download';
    row.appendChild(link);

    if (file.version > 1 || !file.is_current) {
      const badge = el('span', 'file-meta', `v${file.version}${file.is_current ? '' : ' (old)'}`);
      row.appendChild(badge);
    }
    row.appendChild(el('span', 'file-meta', humanSize(file.size_bytes)));

    const del = el('button', 'btn btn-sm btn-danger', '×');
    del.title = 'Delete this file';
    del.addEventListener('click', () => {
      if (!confirm(`Delete ${file.filename}?`)) return;
      api
        .deleteAttachment(file.id)
        .then(() => handlers.onFilesChanged?.())
        .catch((err) => handlers.onError?.(err));
    });
    row.appendChild(del);
    wrap.appendChild(row);
  }

  // Drop zone / file picker
  const zone = el('div', 'dropzone', 'Drop files here, or click to browse');
  const input = el('input');
  input.type = 'file';
  input.multiple = true;
  input.hidden = true;

  const upload = (files) => {
    if (!files || !files.length) return;
    handlers.onUploadStart?.(files.length);
    Promise.all([...files].map((f) => api.upload(node.id, f)))
      .then(() => handlers.onFilesChanged?.())
      .catch((err) => handlers.onError?.(err));
  };

  zone.addEventListener('click', () => input.click());
  input.addEventListener('change', () => upload(input.files));
  zone.addEventListener('dragover', (e) => {
    e.preventDefault();
    zone.classList.add('over');
  });
  zone.addEventListener('dragleave', () => zone.classList.remove('over'));
  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    zone.classList.remove('over');
    upload(e.dataTransfer.files);
  });

  wrap.appendChild(zone);
  wrap.appendChild(input);
  return wrap;
}
