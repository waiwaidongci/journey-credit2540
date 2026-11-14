from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from ..config.database import get_db
from ..controllers.dependencies import roles
from ..constants.roles import Role
from ..schemas.journey import JourneyAnnotation,ImportInput,ImportReport
from ..services.journey_service import annotate_journey,import_journeys
router=APIRouter(prefix="/journeys",tags=["journeys"])
@router.patch("/{jid}")
def annotate(jid:int,data:JourneyAnnotation,db:Session=Depends(get_db),user=Depends(roles(Role.ADMIN,Role.ANALYST))):return annotate_journey(db,jid,data,user)
@router.post("/import",response_model=ImportReport)
def supplement(data:ImportInput,db:Session=Depends(get_db),user=Depends(roles(Role.ADMIN,Role.ANALYST))):return import_journeys(db,data,user)
