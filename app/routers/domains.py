from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, DevelopmentalDomain
from app.schemas import DomainOut
from app.security import get_current_user

router = APIRouter(prefix="/domains", tags=["domains"])


@router.get("", response_model=list[DomainOut])
def list_domains(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(DevelopmentalDomain).filter(DevelopmentalDomain.school_id == user.school_id).all()
