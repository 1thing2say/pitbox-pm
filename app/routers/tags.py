"""Tag CRUD. Assignment of tags to nodes lives in routers/nodes.py."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas, tree
from ..database import get_db
from ..models import Node, NodeTag, Tag

router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("", response_model=list[schemas.TagWithUsage])
def list_tags(db: Session = Depends(get_db)):
    usage = dict(
        db.execute(select(NodeTag.tag_id, func.count(NodeTag.id)).group_by(NodeTag.tag_id)).all()
    )
    return [
        schemas.TagWithUsage(
            **schemas.TagOut.model_validate(t).model_dump(), node_count=usage.get(t.id, 0)
        )
        for t in db.scalars(select(Tag).order_by(Tag.category, Tag.name))
    ]


@router.post("", response_model=schemas.TagOut, status_code=201)
def create_tag(payload: schemas.TagIn, db: Session = Depends(get_db)):
    slug = tree.slugify(payload.name)
    if db.scalar(select(Tag).where(Tag.slug == slug)):
        raise HTTPException(409, f"A tag with slug '{slug}' already exists.")
    tag = Tag(
        name=payload.name,
        slug=slug,
        color=payload.color,
        category=payload.category,
        description=payload.description,
    )
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


@router.patch("/{tag_id}", response_model=schemas.TagOut)
def update_tag(tag_id: int, payload: schemas.TagUpdate, db: Session = Depends(get_db)):
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(404, "Tag not found")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"]:
        new_slug = tree.slugify(data["name"])
        clash = db.scalar(select(Tag).where(Tag.slug == new_slug, Tag.id != tag_id))
        if clash:
            raise HTTPException(409, f"A tag with slug '{new_slug}' already exists.")
        tag.slug = new_slug
    for field, value in data.items():
        setattr(tag, field, value)
    db.commit()
    db.refresh(tag)
    return tag


@router.delete("/{tag_id}", status_code=204)
def delete_tag(tag_id: int, db: Session = Depends(get_db)):
    """Delete a tag everywhere. The ON DELETE CASCADE on node_tags removes every
    assignment, including cascading ones on branches."""
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(404, "Tag not found")
    db.delete(tag)
    db.commit()


@router.get("/{tag_id}/nodes", response_model=list[schemas.NodeOut])
def nodes_with_tag(tag_id: int, project_id: int, db: Session = Depends(get_db)):
    """Every node carrying this tag in a project, INCLUDING nodes that only
    inherit it from a tagged ancestor."""
    if db.get(Tag, tag_id) is None:
        raise HTTPException(404, "Tag not found")
    effective = tree.effective_tags(db, project_id)
    wanted = {nid for nid, tags in effective.items() if any(t["tag_id"] == tag_id for t in tags)}
    return [n for n in tree.get_project_nodes(db, project_id) if n.id in wanted]
