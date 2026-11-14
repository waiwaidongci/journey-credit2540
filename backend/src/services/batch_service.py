from ..models import JourneyBatch,Journey
from ..utils.serialize import record

def list_batches(db):return [dict(record(b),journey_count=db.query(Journey).filter_by(batch_id=b.id,withdrawn=False).count(),conversions=db.query(Journey).filter_by(batch_id=b.id,withdrawn=False,converted=True).count()) for b in db.query(JourneyBatch).order_by(JourneyBatch.id)]
