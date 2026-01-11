"\"\"\"Public endpoints (no auth) for Heliox landing and waitlist.\"\"\""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.waitlist import WaitlistEntry
from app.schemas.waitlist import WaitlistCreate, WaitlistResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/waitlist",
    response_model=WaitlistResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Join the waitlist",
    tags=["Public"],
)
def join_waitlist(payload: WaitlistCreate, db: Session = Depends(get_db)):
    """
    Capture waitlist signups from the public landing page.
    Stores attribution `source` and timestamps for analytics.
    """
    email = payload.email.strip().lower()

    try:
        entry = WaitlistEntry(
          email=email,
          name=payload.name,
          company=payload.company,
          role=payload.role,
          source=payload.source or "landing",
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        logger.info("Waitlist signup created", extra={"email": email, "source": entry.source})
        return entry
    except IntegrityError:
        db.rollback()
        logger.info("Duplicate waitlist signup attempt", extra={"email": email})
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email is already on the waitlist.",
        )
    except Exception as exc:  # pragma: no cover - defensive
        db.rollback()
        logger.error(f"Failed to create waitlist entry: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save waitlist entry at this time.",
        )

