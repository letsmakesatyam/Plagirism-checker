"""
Assignment endpoints.

POST   /api/assignments        -> faculty creates an assignment
GET    /api/assignments        -> list assignments (faculty: their own; student: all active)
                                   supports ?search= (Phase 5: matches title/description)
GET    /api/assignments/{id}   -> get one assignment
PUT    /api/assignments/{id}   -> faculty edits their own assignment
DELETE /api/assignments/{id}   -> faculty deletes their own assignment
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_role
from app.database import get_db
from app.models.assignment import Assignment
from app.models.submission import Submission
from app.models.user import User, UserRole
from app.schemas.assignment import AssignmentCreate, AssignmentOut, AssignmentUpdate, AssignmentWithStats

router = APIRouter(prefix="/api/assignments", tags=["assignments"])


def _get_owned_assignment_or_404(assignment_id: uuid.UUID, faculty: User, db: Session) -> Assignment:
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    if assignment.faculty_id != faculty.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this assignment")
    return assignment


@router.post("", response_model=AssignmentOut, status_code=status.HTTP_201_CREATED)
def create_assignment(
    payload: AssignmentCreate,
    db: Session = Depends(get_db),
    faculty: User = Depends(require_role(UserRole.FACULTY)),
):
    assignment = Assignment(
        title=payload.title,
        description=payload.description,
        due_date=payload.due_date,
        faculty_id=faculty.id,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.get("", response_model=list[AssignmentWithStats])
def list_assignments(
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Assignment, func.count(Submission.id).label("submission_count")).outerjoin(
        Submission, Submission.assignment_id == Assignment.id
    )

    if current_user.role == UserRole.FACULTY:
        query = query.filter(Assignment.faculty_id == current_user.id)
    else:
        query = query.filter(Assignment.is_active.is_(True))

    if search:
        like = f"%{search}%"
        query = query.filter(or_(Assignment.title.ilike(like), Assignment.description.ilike(like)))

    query = query.group_by(Assignment.id).order_by(Assignment.created_at.desc())

    assignment_rows = query.all()

    # For a student, look up their own submission (if any) per assignment in
    # one query, rather than N+1 queries inside the loop below.
    my_submissions_by_assignment: dict = {}
    if current_user.role == UserRole.STUDENT and assignment_rows:
        assignment_ids = [a.id for a, _ in assignment_rows]
        my_subs = (
            db.query(Submission)
            .filter(Submission.assignment_id.in_(assignment_ids), Submission.student_id == current_user.id)
            .all()
        )
        my_submissions_by_assignment = {s.assignment_id: s for s in my_subs}

    results = []
    for assignment, submission_count in assignment_rows:
        item = AssignmentWithStats.model_validate(assignment)
        item.submission_count = submission_count
        my_submission = my_submissions_by_assignment.get(assignment.id)
        if my_submission:
            item.my_submission_id = my_submission.id
            item.my_submission_status = my_submission.status.value
        results.append(item)
    return results


@router.get("/{assignment_id}", response_model=AssignmentOut)
def get_assignment(
    assignment_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    if current_user.role == UserRole.STUDENT and not assignment.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    return assignment


@router.put("/{assignment_id}", response_model=AssignmentOut)
def update_assignment(
    assignment_id: uuid.UUID,
    payload: AssignmentUpdate,
    db: Session = Depends(get_db),
    faculty: User = Depends(require_role(UserRole.FACULTY)),
):
    assignment = _get_owned_assignment_or_404(assignment_id, faculty, db)
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(assignment, field, value)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assignment(
    assignment_id: uuid.UUID,
    db: Session = Depends(get_db),
    faculty: User = Depends(require_role(UserRole.FACULTY)),
):
    assignment = _get_owned_assignment_or_404(assignment_id, faculty, db)
    db.delete(assignment)
    db.commit()
    return None
