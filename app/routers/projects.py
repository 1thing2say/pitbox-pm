"""Project (tree) endpoints: create, clone, fetch whole tree, filter, export."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas, tree
from ..database import get_db
from ..models import Attachment, Member, Node, NodeTag, Project, Tag
from ..seed import BAJA_TEMPLATE, build_template

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _get_project(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    return project


@router.get("", response_model=list[schemas.ProjectSummary])
def list_projects(db: Session = Depends(get_db), include_archived: bool = False):
    stmt = select(Project).order_by(Project.season.desc(), Project.name)
    if not include_archived:
        stmt = stmt.where(Project.is_archived.is_(False))
    projects = list(db.scalars(stmt))

    node_counts = dict(
        db.execute(select(Node.project_id, func.count(Node.id)).group_by(Node.project_id)).all()
    )
    file_counts = dict(
        db.execute(
            select(Node.project_id, func.count(Attachment.id))
            .join(Attachment, Attachment.node_id == Node.id)
            .group_by(Node.project_id)
        ).all()
    )
    return [
        schemas.ProjectSummary(
            **schemas.ProjectOut.model_validate(p).model_dump(),
            node_count=node_counts.get(p.id, 0),
            attachment_count=file_counts.get(p.id, 0),
        )
        for p in projects
    ]


@router.post("", response_model=schemas.ProjectOut, status_code=201)
def create_project(payload: schemas.ProjectCreate, db: Session = Depends(get_db)):
    """Create a brand-new tree, optionally pre-seeded with the standard Baja
    subsystem breakdown so nobody starts from a blank page."""
    project = Project(
        name=payload.name,
        slug=tree.unique_slug(db, payload.name),
        season=payload.season,
        description=payload.description,
    )
    db.add(project)
    db.flush()

    root = tree.create_node(
        db,
        project_id=project.id,
        parent=None,
        name=payload.name,
        node_type="vehicle",
        status="concept",
    )
    if payload.template == "baja_standard":
        build_template(db, project.id, root, BAJA_TEMPLATE)

    db.commit()
    db.refresh(project)
    return project


@router.post("/clone", response_model=schemas.ProjectOut, status_code=201)
def clone_project(payload: schemas.ProjectClone, db: Session = Depends(get_db)):
    """Start a new season from an existing car.

    Copies the entire structure, metadata, tag assignments and attachment links.
    Statuses are reset (default 'concept') so nothing arrives pre-marked as built.
    """
    source = _get_project(db, payload.source_project_id)
    source_root = db.scalar(
        select(Node).where(Node.project_id == source.id, Node.parent_id.is_(None))
    )
    if source_root is None:
        raise HTTPException(400, "Source project has no root node to clone.")

    project = Project(
        name=payload.name,
        slug=tree.unique_slug(db, payload.name),
        season=payload.season,
        description=payload.description or f"Cloned from {source.name}",
    )
    db.add(project)
    db.flush()

    new_root = tree.copy_subtree(
        db,
        source_root,
        target_project_id=project.id,
        new_parent=None,
        reset_status=payload.reset_status,
        copy_tags=payload.copy_tags,
        copy_attachments=payload.copy_attachments,
    )
    new_root.name = payload.name
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=schemas.ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)):
    return _get_project(db, project_id)


@router.patch("/{project_id}", response_model=schemas.ProjectOut)
def update_project(
    project_id: int, payload: schemas.ProjectUpdate, db: Session = Depends(get_db)
):
    project = _get_project(db, project_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    """Permanently delete a project and every node under it.

    Attachment ROWS go with it; the blobs on disk are left alone, because another
    project may share them and orphan cleanup is a separate, auditable job
    (see scripts/gc_blobs.py).
    """
    project = _get_project(db, project_id)
    db.delete(project)
    db.commit()


@router.get("/{project_id}/tree", response_model=schemas.TreeResponse)
def get_tree(project_id: int, db: Session = Depends(get_db)):
    """The entire tree in one request.

    This is the endpoint the UI lives on. Sending everything at once means
    expand/collapse, search and tag filtering are all instant and offline-ish --
    no spinner every time someone opens a branch.
    """
    project = _get_project(db, project_id)
    nodes = tree.get_project_nodes(db, project_id)
    tags_by_node = tree.effective_tags(db, project_id)

    counts = dict(
        db.execute(
            select(Attachment.node_id, func.count(Attachment.id))
            .join(Node, Node.id == Attachment.node_id)
            .where(Node.project_id == project_id)
            .group_by(Attachment.node_id)
        ).all()
    )

    usage = dict(
        db.execute(select(NodeTag.tag_id, func.count(NodeTag.id)).group_by(NodeTag.tag_id)).all()
    )
    tags = [
        schemas.TagWithUsage(
            **schemas.TagOut.model_validate(t).model_dump(), node_count=usage.get(t.id, 0)
        )
        for t in db.scalars(select(Tag).order_by(Tag.category, Tag.name))
    ]
    members = list(db.scalars(select(Member).where(Member.is_active.is_(True)).order_by(Member.name)))

    return schemas.TreeResponse(
        project=project,
        nodes=nodes,
        tags_by_node=tags_by_node,
        attachment_counts=counts,
        tags=tags,
        members=members,
    )


@router.get("/{project_id}/filter", response_model=schemas.FilterResult)
def filter_tree(
    project_id: int,
    db: Session = Depends(get_db),
    tags: list[str] = Query(default=[], description="Tag slugs"),
    tag_mode: str = Query(default="any", pattern="^(any|all)$"),
    status: list[str] = Query(default=[]),
    assignee_id: int | None = None,
    sourcing: str | None = None,
    q: str | None = Query(default=None, description="Text across name, part number, description"),
    include_descendants: bool = Query(
        default=False, description="Also reveal everything under a matching node"
    ),
):
    """Server-side equivalent of the client filter.

    The important part is visible_ids. If you return only the nodes that matched,
    the client cannot render them as a tree -- a matching bolt six levels down has
    no visible parent to hang off. So we always add the ancestor chain of every
    match; the UI draws those as dimmed context rows.
    """
    _get_project(db, project_id)
    nodes = tree.get_project_nodes(db, project_id)
    effective = tree.effective_tags(db, project_id)

    wanted = {t for t in tags if t}
    needle = (q or "").strip().lower()

    matched: list[Node] = []
    for node in nodes:
        if status and node.status not in status:
            continue
        if assignee_id is not None and node.assignee_id != assignee_id:
            continue
        if sourcing and node.sourcing != sourcing:
            continue
        if needle:
            haystack = " ".join(
                filter(None, [node.name, node.part_number, node.description, node.vendor])
            ).lower()
            if needle not in haystack:
                continue
        if wanted:
            node_slugs = {t["slug"] for t in effective.get(node.id, [])}
            if tag_mode == "all":
                if not wanted.issubset(node_slugs):
                    continue
            elif not (wanted & node_slugs):
                continue
        matched.append(node)

    matched_ids = [n.id for n in matched]
    visible: set[int] = set(matched_ids)
    for node in matched:
        visible.update(node.ancestor_ids)
    if include_descendants:
        prefixes = [n.path for n in matched]
        for node in nodes:
            if any(node.path.startswith(p) for p in prefixes):
                visible.add(node.id)

    ordered_visible = [n.id for n in nodes if n.id in visible]
    return schemas.FilterResult(
        matched_ids=matched_ids, visible_ids=ordered_visible, matched_count=len(matched_ids)
    )


@router.get("/{project_id}/export.csv")
def export_bom(project_id: int, db: Session = Depends(get_db)):
    """Flat BOM as CSV -- for the cost report, a purchase order, or a sanity check
    in Excel. Indentation is preserved via the Level column."""
    project = _get_project(db, project_id)
    nodes = tree.get_project_nodes(db, project_id)
    effective = tree.effective_tags(db, project_id)
    members = {m.id: m.name for m in db.scalars(select(Member))}

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([
        "Level", "Name", "Type", "Part Number", "Status", "Qty", "Sourcing", "Material",
        "Mass (g)", "Unit Cost", "Vendor", "Lead Time (days)", "Assignee", "Tags", "Description",
    ])
    for n in nodes:
        writer.writerow([
            n.depth,
            ("    " * n.depth) + n.name,
            n.node_type,
            n.part_number or "",
            n.status,
            n.quantity,
            n.sourcing,
            n.material or "",
            f"{n.mass_g:.1f}" if n.mass_g is not None else "",
            f"{n.cost_cents / 100:.2f}" if n.cost_cents is not None else "",
            n.vendor or "",
            n.lead_time_days if n.lead_time_days is not None else "",
            members.get(n.assignee_id, ""),
            ", ".join(sorted(t["name"] for t in effective.get(n.id, []))),
            (n.description or "").replace("\n", " "),
        ])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{project.slug}-bom.csv"'},
    )
