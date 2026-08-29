"""Node endpoints: create children, edit metadata, move, duplicate, delete, tag."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas, tree
from ..database import get_db
from ..models import Attachment, Node, NodeTag, Tag

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


def _get_node(db: Session, node_id: int) -> Node:
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(404, f"Node {node_id} not found")
    return node


def _detail(db: Session, node: Node) -> schemas.NodeDetail:
    """Assemble everything the detail panel needs in one shot."""
    effective = tree.effective_tags(db, node.project_id).get(node.id, [])
    attachments = list(
        db.scalars(
            select(Attachment)
            .where(Attachment.node_id == node.id)
            .order_by(Attachment.filename, Attachment.version.desc())
        )
    )
    subtree = tree.get_subtree(db, node)

    # Rollups are a straight sum of unit cost x quantity over the subtree. They do
    # NOT multiply through parent quantities -- if you have 2 identical assemblies,
    # model that as 2 nodes or set quantity on the leaves. Keeping it simple here
    # avoids silently wrong numbers in a cost report.
    rollup_cost = sum((n.cost_cents or 0) * n.quantity for n in subtree)
    rollup_mass = sum((n.mass_g or 0.0) * n.quantity for n in subtree)

    return schemas.NodeDetail(
        **schemas.NodeOut.model_validate(node).model_dump(),
        tags=[schemas.EffectiveTag(**t) for t in effective],
        attachments=[schemas.AttachmentOut.model_validate(a) for a in attachments],
        ancestor_ids=node.ancestor_ids,
        child_count=db.scalar(
            select(func.count()).select_from(Node).where(Node.parent_id == node.id)
        ) or 0,
        descendant_count=max(len(subtree) - 1, 0),
        rollup_cost_cents=rollup_cost,
        rollup_mass_g=rollup_mass,
    )


@router.get("/{node_id}", response_model=schemas.NodeDetail)
def get_node(node_id: int, db: Session = Depends(get_db)):
    return _detail(db, _get_node(db, node_id))


@router.post("", response_model=schemas.NodeDetail, status_code=201)
def create_node(payload: schemas.NodeCreate, db: Session = Depends(get_db)):
    """Add a node. This is requirement #2 -- extending a branch is one POST.

    parent_id=None creates a second root, which is legal but unusual; the UI
    always passes the id of the node you clicked '+' on.
    """
    parent = None
    if payload.parent_id is not None:
        parent = _get_node(db, payload.parent_id)
        if parent.project_id != payload.project_id:
            raise HTTPException(400, "Parent belongs to a different project.")

    fields = payload.model_dump(exclude={"parent_id", "project_id"})
    node = tree.create_node(db, project_id=payload.project_id, parent=parent, **fields)
    db.commit()
    db.refresh(node)
    return _detail(db, node)


@router.patch("/{node_id}", response_model=schemas.NodeDetail)
def update_node(node_id: int, payload: schemas.NodeUpdate, db: Session = Depends(get_db)):
    node = _get_node(db, node_id)
    # exclude_unset is what separates "set this to null" from "don't touch it".
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(node, field, value)
    db.commit()
    db.refresh(node)
    return _detail(db, node)


@router.post("/{node_id}/move", response_model=schemas.NodeDetail)
def move_node(node_id: int, payload: schemas.NodeMove, db: Session = Depends(get_db)):
    """Re-parent a node (drag and drop). Rewrites the subtree's paths."""
    node = _get_node(db, node_id)
    new_parent = _get_node(db, payload.new_parent_id) if payload.new_parent_id is not None else None
    try:
        tree.move_node(db, node, new_parent, payload.position)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.commit()
    db.refresh(node)
    return _detail(db, node)


@router.post("/reorder", status_code=204)
def reorder(payload: schemas.NodeReorder, db: Session = Depends(get_db)):
    """Persist a new sibling order after a drag-and-drop."""
    tree.reorder_siblings(db, payload.project_id, payload.parent_id, payload.ordered_ids)
    db.commit()


@router.post("/{node_id}/duplicate", response_model=schemas.NodeDetail, status_code=201)
def duplicate_node(node_id: int, payload: schemas.NodeDuplicate, db: Session = Depends(get_db)):
    """Deep-copy a node and everything under it.

    Handy for the four corners of a suspension: build one upright assembly
    properly, then duplicate it three times.
    """
    source = _get_node(db, node_id)
    if payload.new_parent_id is not None:
        new_parent = _get_node(db, payload.new_parent_id)
    else:
        new_parent = db.get(Node, source.parent_id) if source.parent_id else None

    clone = tree.copy_subtree(
        db,
        source,
        target_project_id=source.project_id,
        new_parent=new_parent,
        reset_status=payload.reset_status,
        copy_tags=payload.copy_tags,
        copy_attachments=payload.copy_attachments,
    )
    clone.name = payload.name or f"{source.name} (copy)"
    db.commit()
    db.refresh(clone)
    return _detail(db, clone)


@router.delete("/{node_id}", status_code=200)
def delete_node(node_id: int, db: Session = Depends(get_db)):
    """Delete a node and its entire subtree. Returns the count so the UI can say
    'this will remove 34 parts' rather than quietly vaporising a subsystem."""
    node = _get_node(db, node_id)
    removed = tree.delete_node(db, node)
    db.commit()
    return {"deleted_node_id": node_id, "deleted_count": removed}


# --- tag assignment ----------------------------------------------------------

@router.post("/{node_id}/tags", response_model=list[schemas.EffectiveTag], status_code=201)
def add_tag(node_id: int, payload: schemas.TagAssignment, db: Session = Depends(get_db)):
    """Attach a tag. cascade=True tags the entire branch beneath this node."""
    node = _get_node(db, node_id)
    if db.get(Tag, payload.tag_id) is None:
        raise HTTPException(404, f"Tag {payload.tag_id} not found")

    link = db.scalar(
        select(NodeTag).where(NodeTag.node_id == node_id, NodeTag.tag_id == payload.tag_id)
    )
    if link is None:
        link = NodeTag(node_id=node_id, tag_id=payload.tag_id)
        db.add(link)
    # Re-posting an existing tag updates the cascade flag rather than 409-ing,
    # so the UI's "apply to whole branch" toggle is a plain idempotent POST.
    link.cascade = payload.cascade
    link.note = payload.note
    db.commit()

    return [
        schemas.EffectiveTag(**t)
        for t in tree.effective_tags(db, node.project_id).get(node_id, [])
    ]


@router.delete("/{node_id}/tags/{tag_id}", status_code=204)
def remove_tag(node_id: int, tag_id: int, db: Session = Depends(get_db)):
    """Remove a tag from a node.

    Note this only removes a DIRECT assignment. An inherited tag has to be
    removed at the ancestor that broadcasts it -- the API reports which node that
    is, so the UI can offer to jump there.
    """
    node = _get_node(db, node_id)
    link = db.scalar(select(NodeTag).where(NodeTag.node_id == node_id, NodeTag.tag_id == tag_id))
    if link is None:
        inherited_from = [
            t["source_node_id"]
            for t in tree.effective_tags(db, node.project_id).get(node_id, [])
            if t["tag_id"] == tag_id and t["inherited"]
        ]
        if inherited_from:
            raise HTTPException(
                409,
                f"That tag is inherited from node {inherited_from[0]}. "
                "Remove it there to clear it from this whole branch.",
            )
        raise HTTPException(404, "Tag is not assigned to this node.")
    db.delete(link)
    db.commit()
