"""The betslip, saved to a signed-in visitor's account so it follows them between devices. Each device saves its slip
(legs and stakes per book) a moment after a change and reads it back when it regains focus; the betting state and the
"all books" choice stay per device. Optimistic: a save based on an older copy than the server's is refused (409), so the
device merges the two and saves again rather than silently dropping another device's changes."""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import delete
from sqlalchemy.orm import Session

from . import auth
from .bets import require_member
from .db import User, UserSlip
from .schemas import SlipIn, SlipOut

router = APIRouter(prefix="/api/me", tags=["slip"])

MAX_LEGS = 40
MAX_BYTES = 64_000


def _out(slip) -> SlipOut:
    if slip is None:
        return SlipOut(legs=[], stakes={}, updated_at=None)
    return SlipOut(legs=slip.legs or [], stakes=slip.stakes or {}, updated_at=slip.updated_at.isoformat())


@router.get("/slip", response_model=SlipOut)
def read_slip(user: User = Depends(require_member), db: Session = Depends(auth.get_db)):
    return _out(db.get(UserSlip, user.id))


@router.put("/slip", response_model=SlipOut, dependencies=[Depends(auth.same_origin)])
def save_slip(body: SlipIn, user: User = Depends(require_member), db: Session = Depends(auth.get_db)):
    if len(body.legs) > MAX_LEGS or any(not isinstance(leg.get("id"), str) for leg in body.legs):
        raise HTTPException(422, f"A slip holds up to {MAX_LEGS} legs")
    stakes = {str(b)[:40]: round(float(s), 2) for b, s in body.stakes.items() if 0 <= s <= 100_000}
    if len(json.dumps(body.legs)) + len(json.dumps(stakes)) > MAX_BYTES:
        raise HTTPException(422, "That slip is too large to save")
    slip = db.get(UserSlip, user.id)
    if slip and body.base and slip.updated_at.isoformat() > body.base:
        # another device saved since this one last read: send it the newer copy to merge
        return JSONResponse(status_code=409, content=_out(slip).model_dump())
    if slip is None:
        slip = UserSlip(user_id=user.id)
        db.add(slip)
    slip.legs, slip.stakes, slip.updated_at = body.legs, stakes, datetime.utcnow()
    db.commit()
    return _out(slip)


def delete_for(db: Session, user_id: int) -> None:
    """An account being deleted (app/auth.py)."""
    db.execute(delete(UserSlip).where(UserSlip.user_id == user_id))
