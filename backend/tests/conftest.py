import os,sys,tempfile
os.environ["DATABASE_URL"]="sqlite:///"+tempfile.mktemp(prefix="journey-test-",suffix=".db")
os.environ["SEED_DEMO"]="false"
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from src.config.database import Base,engine,SessionLocal
from src.config.migrate import ensure_schema
from src.models import User,Channel,JourneyBatch,Journey
from src.utils.security import hash_password

CHANNELS=[('POSTER','城市海报',12.,500.),('NEWSLETTER','策展通讯',8.,450.),('CREATOR','创作者推荐',18.,350.),('SEARCH','主动检索',22.,600.),('COMMUNITY','社群分享',6.,400.),('PARTNER','合作场馆',15.,300.)]

@pytest.fixture()
def db():
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine);ensure_schema(engine)
    with SessionLocal() as s:
        for role,name in [("admin","陈照 · 传播负责人"),("analyst","许晴 · 路径研究员"),("viewer","闻溪 · 策展阅读者")]:
            s.add(User(email=role+"@xunguang.demo",name=name,role=role,password_hash=hash_password("Xunguang2026!")))
        for code,name,cost,cap in CHANNELS:s.add(Channel(code=code,name=name,unit_cost=cost,capacity=cap,description="模拟成本容量"))
        s.flush()
        for name in ['巡光秋展 · 首周路径','巡光秋展 · 第二周路径']:
            s.add(JourneyBatch(name=name,source="xg-exhibition-paths.json",description="匿名预约触点路径"))
        s.commit()
        yield s
    s.close()

def add_journey(db,code,batch_id,path,converted,revision=1,note=""):
    row=Journey(code=code,batch_id=batch_id,path=path,converted=converted,note=note,revision=revision,withdrawn=False)
    db.add(row);db.commit();return row

def batches(db):
    return db.query(JourneyBatch).order_by(JourneyBatch.id).all()

def payload(*records,source="test-supplement.json"):
    return {"source":source,"records":list(records)}

def rec(code,revision,batch_id,path,converted,**kw):
    return dict(code=code,revision=revision,batch_id=batch_id,path=path,converted=converted,**kw)
