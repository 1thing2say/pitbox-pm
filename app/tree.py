"""Tree mechanics.

Everything that maintains the materialized path lives here. Nothing else in the
codebase should ever write Node.path, Node.depth or Node.position directly --
route all structural changes through these functions and the cache stays honest.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Attachment, Node, NodeTag, Project, Tag


# --- small utilities ---------------------------------------------------------

def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", value) or "untitled"


def unique_slug(db: Session, base: str) -> str:
    """Append -2, -3 ... until the project slug is free."""
    slug = slugify(base)
    candidate, n = slug, 1
    while db.scalar(select(func.count()).select_from(Project).where(Project.slug == candidate)):
        n += 1
        candidate = f"{slug}-{n}"
    return candidate


# --- reading -----------------------------------------------------------------

def get_project_nodes(db: Session, project_id: int) -> list[Node]:
    """Every node of a project, in depth-first display order.

    Sorting by (path) alone is NOT display order once you have more than 9
    siblings ('/1/10/' sorts before '/1/2/'), so we sort in Python using the
    parent/position graph. A Baja BOM is a few thousand rows at most -- one flat
    query and an in-memory sort beats any amount of recursive-CTE cleverness,
    and it lets the browser do instant filtering with no round trips.
    """
    nodes = list(db.scalars(select(Node).where(Node.project_id == project_id)))
    by_parent: dict[int | None, list[Node]] = defaultdict(list)
    for n in nodes:
        by_parent[n.parent_id].append(n)
    for siblings in by_parent.values():
        siblings.sort(key=lambda n: (n.position, n.id))

    ordered: list[Node] = []

    def walk(parent_id: int | None) -> None:
        for child in by_parent[parent_id]:
            ordered.append(child)
            walk(child.id)

    walk(None)
    # Defensive: if a path cache ever drifted and orphaned a row, still return it
    # rather than silently hiding a part from the team.
    if len(ordered) != len(nodes):
        seen = {n.id for n in ordered}
        ordered.extend(n for n in nodes if n.id not in seen)
    return ordered


def get_subtree(db: Session, node: Node) -> list[Node]:
    """The node plus every descendant -- one indexed prefix scan."""
    return list(
        db.scalars(
            select(Node)
            .where(Node.project_id == node.project_id, Node.path.like(node.subtree_pattern))
            .order_by(Node.depth, Node.position, Node.id)
        )
    )


def next_position(db: Session, project_id: int, parent_id: int | None) -> int:
    current = db.scalar(
        select(func.max(Node.position)).where(
            Node.project_id == project_id, Node.parent_id == parent_id
        )
    )
    return 0 if current is None else current + 1


# --- writing -----------------------------------------------------------------

def create_node(db: Session, *, project_id: int, parent: Node | None, **fields) -> Node:
    """Insert a node and stamp its hierarchy cache.

    The path cannot be computed before the INSERT because it ends in the node's
    own id, so we flush to get the id, then fill it in.
    """
    parent_id = parent.id if parent else None
    position = fields.pop("position", None)
    if position is None:
        position = next_position(db, project_id, parent_id)

    node = Node(project_id=project_id, parent_id=parent_id, position=position, **fields)
    db.add(node)
    db.flush()  # assigns node.id

    node.path = f"{parent.path}{node.id}/" if parent else f"/{node.id}/"
    node.depth = (parent.depth + 1) if parent else 0
    db.flush()
    return node


def move_node(db: Session, node: Node, new_parent: Node | None, position: int | None = None) -> Node:
    """Re-parent a node and rewrite the paths of everything beneath it.

    Raises ValueError on the two moves that would corrupt the tree: onto itself,
    or into its own descendant (which would detach the whole branch into a cycle).
    """
    if new_parent is not None:
        if new_parent.id == node.id:
            raise ValueError("A node cannot be its own parent.")
        if new_parent.path.startswith(node.path):
            raise ValueError("Cannot move a node into its own descendant.")
        if new_parent.project_id != node.project_id:
            raise ValueError("Cannot move a node across projects.")

    old_path = node.path
    old_depth = node.depth
    new_path = f"{new_parent.path}{node.id}/" if new_parent else f"/{node.id}/"
    new_depth = (new_parent.depth + 1) if new_parent else 0
    depth_delta = new_depth - old_depth

    # Grab the subtree BEFORE mutating the node's own path.
    subtree = get_subtree(db, node)

    node.parent_id = new_parent.id if new_parent else None
    node.position = (
        position
        if position is not None
        else next_position(db, node.project_id, new_parent.id if new_parent else None)
    )

    for descendant in subtree:
        # Splice the new prefix onto the part of the path below this node.
        descendant.path = new_path + descendant.path[len(old_path):]
        descendant.depth += depth_delta

    db.flush()
    return node


def reorder_siblings(db: Session, project_id: int, parent_id: int | None, ordered_ids: list[int]) -> None:
    """Apply an explicit sibling order (used by drag-and-drop)."""
    lookup = {
        n.id: n
        for n in db.scalars(
            select(Node).where(Node.project_id == project_id, Node.parent_id == parent_id)
        )
    }
    for index, node_id in enumerate(ordered_ids):
        if node_id in lookup:
            lookup[node_id].position = index
    db.flush()


def delete_node(db: Session, node: Node) -> int:
    """Delete a node and its whole subtree. Returns how many nodes went away.

    The ON DELETE CASCADE foreign key does the actual work (which is why
    PRAGMA foreign_keys=ON in database.py matters); we count first so the API
    can tell the user what they are about to lose.
    """
    count = len(get_subtree(db, node))
    db.delete(node)
    db.flush()
    return count


COPYABLE_FIELDS = (
    "name", "node_type", "part_number", "status", "assignee_id", "description",
    "quantity", "sourcing", "material", "mass_g", "cost_cents", "vendor",
    "lead_time_days", "extra",
)


def copy_subtree(
    db: Session,
    source: Node,
    *,
    target_project_id: int,
    new_parent: Node | None,
    reset_status: str | None = None,
    copy_tags: bool = True,
    copy_attachments: bool = True,
) -> Node:
    """Deep-copy a node and its descendants.

    This is what powers "start next year's car from last year's" -- the single
    most valuable button in the app, because carrying over the 2025 BOM beats
    retyping 800 rows.

    Attachments are copied by metadata only. The bytes are content-addressed, so
    both rows point at the same blob on disk and nothing is duplicated.
    """
    id_map: dict[int, Node] = {}
    originals = get_subtree(db, source)

    for original in originals:
        fields = {f: getattr(original, f) for f in COPYABLE_FIELDS}
        if isinstance(fields.get("extra"), dict):
            fields["extra"] = dict(fields["extra"])  # don't share the JSON dict
        if reset_status:
            fields["status"] = reset_status

        if original.id == source.id:
            parent = new_parent
        else:
            parent = id_map.get(original.parent_id)
            if parent is None:
                continue  # parent was skipped; skip the orphan too

        clone = create_node(db, project_id=target_project_id, parent=parent, **fields)
        id_map[original.id] = clone

    db.flush()

    if copy_tags:
        links = db.scalars(
            select(NodeTag).where(NodeTag.node_id.in_(list(id_map.keys())))
        ).all()
        for link in links:
            db.add(
                NodeTag(
                    node_id=id_map[link.node_id].id,
                    tag_id=link.tag_id,
                    cascade=link.cascade,
                    note=link.note,
                )
            )

    if copy_attachments:
        files = db.scalars(
            select(Attachment).where(Attachment.node_id.in_(list(id_map.keys())))
        ).all()
        for f in files:
            db.add(
                Attachment(
                    node_id=id_map[f.node_id].id,
                    filename=f.filename,
                    content_type=f.content_type,
                    size_bytes=f.size_bytes,
                    sha256=f.sha256,  # same blob, no copy on disk
                    kind=f.kind,
                    version=f.version,
                    is_current=f.is_current,
                    notes=f.notes,
                    uploaded_by_id=f.uploaded_by_id,
                )
            )

    db.flush()
    return id_map[source.id]


# --- tag resolution ----------------------------------------------------------

def effective_tags(db: Session, project_id: int) -> dict[int, list[dict]]:
    """Map every node id in a project to its full tag list.

    A node's effective tags are its own tags, plus every cascade=True tag on any
    of its ancestors. Because each node's path already contains its ancestor ids,
    this is a dict lookup per level -- no recursive query, no per-node round trip.

    Returns {node_id: [{tag_id, slug, name, color, category, inherited, source_node_id}]}
    """
    rows = db.execute(
        select(NodeTag, Tag, Node.path, Node.id)
        .join(Tag, Tag.id == NodeTag.tag_id)
        .join(Node, Node.id == NodeTag.node_id)
        .where(Node.project_id == project_id)
    ).all()

    direct: dict[int, list[dict]] = defaultdict(list)
    cascading: dict[int, list[dict]] = defaultdict(list)  # node_id -> tags it broadcasts

    for link, tag, _path, node_id in rows:
        entry = {
            "tag_id": tag.id,
            "slug": tag.slug,
            "name": tag.name,
            "color": tag.color,
            "category": tag.category,
            "cascade": link.cascade,
            "inherited": False,
            "source_node_id": node_id,
        }
        direct[node_id].append(entry)
        if link.cascade:
            cascading[node_id].append(entry)

    result: dict[int, list[dict]] = {}
    if not cascading:
        return {nid: list(tags) for nid, tags in direct.items()}

    for node in db.scalars(select(Node).where(Node.project_id == project_id)):
        tags = list(direct.get(node.id, []))
        seen = {t["tag_id"] for t in tags}
        for ancestor_id in node.ancestor_ids:
            for entry in cascading.get(ancestor_id, []):
                if entry["tag_id"] not in seen:
                    seen.add(entry["tag_id"])
                    tags.append({**entry, "inherited": True})
        if tags:
            result[node.id] = tags
    return result
