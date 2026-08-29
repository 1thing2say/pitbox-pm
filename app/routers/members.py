"""Team roster -- the list you pick from when assigning a part to someone."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..models import Member

router = APIRouter(prefix="/api/members", tags=["members"])


@router.get("", response_model=list[schemas.MemberOut])
def list_members(include_inactive: bool = False, db: Session = Depends(get_db)):
    stmt = select(Member).order_by(Member.name)
    if not include_inactive:
        stmt = stmt.where(Member.is_active.is_(True))
    return list(db.scalars(stmt))


@router.post("", response_model=schemas.MemberOut, status_code=201)
def create_member(payload: schemas.MemberIn, db: Session = Depends(get_db)):
    if payload.email and db.scalar(select(Member).where(Member.email == payload.email)):
        raise HTTPException(409, "A member with that email already exists.")
    member = Member(**payload.model_dump())
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


@router.patch("/{member_id}", response_model=schemas.MemberOut)
def update_member(member_id: int, payload: schemas.MemberIn, db: Session = Depends(get_db)):
    member = db.get(Member, member_id)
    if member is None:
        raise HTTPException(404, "Member not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(member, field, value)
    db.commit()
    db.refresh(member)
    return member


@router.delete("/{member_id}", status_code=204)
def deactivate_member(member_id: int, db: Session = Depends(get_db)):
    """Graduating seniors get deactivated, not deleted -- their name should stay
    on the parts they designed."""
    member = db.get(Member, member_id)
    if member is None:
        raise HTTPException(404, "Member not found")
    member.is_active = False
    db.commit()
