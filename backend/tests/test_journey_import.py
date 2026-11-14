import threading
import jwt
from fastapi.testclient import TestClient
from src.config.settings import JWT_SECRET
from src.models import User,Journey,AttributionRun,BudgetScenario
from src.schemas.journey import ImportInput
from src.services.journey_service import import_journeys,list_journeys
from src.services.attribution_algorithm import analyze_attribution
from src.services.channel_service import list_channels
from src.utils.fingerprint import fingerprint
from conftest import add_journey,batches,payload,rec

def analyst(db):return db.query(User).filter_by(role="analyst").first()
def do_import(db,data):return import_journeys(db,ImportInput(**data),analyst(db))
def codes(db,bid):return {j["code"] for j in list_journeys(db,bid)}

def test_import_new_records(db):
    b1,b2=batches(db)
    report=do_import(db,payload(rec("XG-T001",1,b1.id,["POSTER","SEARCH"],True),rec("XG-T002",1,b2.id,["COMMUNITY"],False)))
    assert report["applied"] and report["summary"]["imported"]==2
    assert codes(db,b1.id)=={"XG-T001"} and codes(db,b2.id)=={"XG-T002"}
    row=db.query(Journey).filter_by(code="XG-T001").one()
    assert row.revision==1 and row.withdrawn is False

def test_higher_revision_wins_and_stale_ignored(db):
    b1,_=batches(db)
    do_import(db,payload(rec("XG-T010",1,b1.id,["POSTER"],False)))
    report=do_import(db,payload(rec("XG-T010",2,b1.id,["SEARCH","POSTER"],True)))
    assert report["records"][0]["outcome"]=="updated"
    stale=do_import(db,payload(rec("XG-T010",1,b1.id,["POSTER"],False)))
    assert stale["records"][0]["outcome"]=="stale"
    row=db.query(Journey).filter_by(code="XG-T010").one()
    assert row.revision==2 and row.path==["SEARCH","POSTER"] and row.converted is True

def test_withdraw_then_stale_replay_does_not_revive(db):
    b1,_=batches(db)
    do_import(db,payload(rec("XG-T020",1,b1.id,["POSTER"],True)))
    gone=do_import(db,payload(dict(code="XG-T020",revision=2,withdraw=True)))
    assert gone["records"][0]["outcome"]=="withdrawn" and codes(db,b1.id)==set()
    replay=do_import(db,payload(rec("XG-T020",1,b1.id,["POSTER"],True)))
    assert replay["records"][0]["outcome"]=="stale" and "撤回" in replay["records"][0]["detail"]
    assert codes(db,b1.id)==set() and db.query(Journey).filter_by(code="XG-T020").one().withdrawn is True
    revive=do_import(db,payload(rec("XG-T020",3,b1.id,["SEARCH"],False)))
    assert revive["records"][0]["outcome"]=="revived" and codes(db,b1.id)=={"XG-T020"}

def test_withdraw_before_path_arrives_blocks_late_old_version(db):
    b1,_=batches(db)
    tomb=do_import(db,payload(dict(code="XG-T021",revision=5,withdraw=True)))
    assert tomb["records"][0]["outcome"]=="withdrawn"
    late=do_import(db,payload(rec("XG-T021",3,b1.id,["POSTER"],True)))
    assert late["records"][0]["outcome"]=="stale" and codes(db,b1.id)==set()

def test_same_revision_conflict_rejects_whole_batch(db):
    b1,_=batches(db)
    add_journey(db,"XG-T030",b1.id,["POSTER"],False,revision=1)
    report=do_import(db,payload(rec("XG-T030",1,b1.id,["SEARCH"],True),rec("XG-T031",1,b1.id,["POSTER"],False)))
    assert report["applied"] is False
    by_code={r["code"]:r for r in report["records"]}
    assert by_code["XG-T030"]["outcome"]=="conflict" and "冲突" in by_code["XG-T030"]["detail"]
    assert by_code["XG-T031"]["outcome"]=="skipped" and by_code["XG-T031"]["accepted"] is False
    assert db.query(Journey).filter_by(code="XG-T031").first() is None
    row=db.query(Journey).filter_by(code="XG-T030").one()
    assert row.path==["POSTER"] and row.converted is False

def test_in_payload_same_revision_conflict_rejects_all(db):
    b1,_=batches(db)
    report=do_import(db,payload(rec("XG-T040",1,b1.id,["POSTER"],False),rec("XG-T040",1,b1.id,["SEARCH"],True),rec("XG-T041",1,b1.id,["POSTER"],True)))
    assert report["applied"] is False and db.query(Journey).filter_by(code="XG-T041").first() is None

def test_same_revision_redelivery_is_idempotent(db):
    b1,_=batches(db)
    do_import(db,payload(rec("XG-T050",1,b1.id,["POSTER","SEARCH"],True,note="首条")))
    again=do_import(db,payload(rec("XG-T050",1,b1.id,["POSTER","SEARCH"],True)))
    assert again["applied"] and again["records"][0]["outcome"]=="unchanged"
    assert db.query(Journey).filter_by(code="XG-T050").count()==1

def test_in_payload_highest_revision_wins(db):
    b1,_=batches(db)
    report=do_import(db,payload(rec("XG-T060",1,b1.id,["POSTER"],False),rec("XG-T060",3,b1.id,["SEARCH"],True),rec("XG-T060",2,b1.id,["CREATOR"],False)))
    assert report["applied"]
    outcomes={(r["code"],r["revision"]):r["outcome"] for r in report["records"]}
    assert outcomes[("XG-T060",3)]=="imported" and outcomes[("XG-T060",1)]=="superseded" and outcomes[("XG-T060",2)]=="superseded"
    row=db.query(Journey).filter_by(code="XG-T060").one()
    assert row.revision==3 and row.path==["SEARCH"]

def test_invalid_records_reject_whole_batch(db):
    b1,_=batches(db)
    bad_channel=do_import(db,payload(rec("XG-T070",1,b1.id,["UNKNOWN"],False),rec("XG-T071",1,b1.id,["POSTER"],True)))
    assert bad_channel["applied"] is False and db.query(Journey).filter_by(code="XG-T071").first() is None
    bad_batch=do_import(db,payload(rec("XG-T072",1,9999,["POSTER"],False)))
    assert bad_batch["applied"] is False and "批次" in bad_batch["records"][0]["detail"]

def test_cross_week_migration_atomic_and_visible_to_attribution(db):
    b1,b2=batches(db)
    for i in range(1,61):add_journey(db,f"XG-A{i:03}",b1.id,["POSTER","SEARCH"] if i%3 else ["SEARCH"],i%3==0)
    for i in range(1,41):add_journey(db,f"XG-B{i:03}",b2.id,["COMMUNITY","SEARCH"] if i%2 else ["POSTER"],i%2==0)
    before1=analyze_attribution(b1,list_journeys(db,b1.id),list_channels(db))
    before2=analyze_attribution(b2,list_journeys(db,b2.id),list_channels(db))
    report=do_import(db,payload(rec("XG-A001",2,b2.id,["POSTER","SEARCH"],False),rec("XG-A003",2,b2.id,["SEARCH"],True)))
    assert report["applied"] and all(r["outcome"]=="moved" for r in report["records"])
    assert db.query(Journey).filter(Journey.code.in_(["XG-A001","XG-A003"])).count()==2
    assert not {"XG-A001","XG-A003"}&codes(db,b1.id) and {"XG-A001","XG-A003"}<=codes(db,b2.id)
    after1=analyze_attribution(b1,list_journeys(db,b1.id),list_channels(db))
    after2=analyze_attribution(b2,list_journeys(db,b2.id),list_channels(db))
    assert after1["journey_count"]==before1["journey_count"]-2 and after2["journey_count"]==before2["journey_count"]+2
    assert after1["conversions"]==before1["conversions"]-1 and after2["conversions"]==before2["conversions"]+1
    assert after1["input_hash"]!=before1["input_hash"] and after2["input_hash"]!=before2["input_hash"]

def test_concurrent_imports_both_apply_completely(db):
    b1,_=batches(db)
    from src.config.database import SessionLocal
    user=analyst(db);results={}
    def work(tag):
        with SessionLocal() as s:
            data=payload(*[rec(f"XG-{tag}{i:03}",1,b1.id,["POSTER"],i%2==0) for i in range(120)],source=tag+".json")
            results[tag]=import_journeys(s,ImportInput(**data),user)
    threads=[threading.Thread(target=work,args=("P",)),threading.Thread(target=work,args=("Q",))]
    for t in threads:t.start()
    for t in threads:t.join()
    assert results["P"]["applied"] and results["Q"]["applied"]
    assert db.query(Journey).filter_by(withdrawn=False).count()==240

def test_research_reads_never_mix_pre_and_post_import(db):
    b1,b2=batches(db)
    for i in range(1,81):add_journey(db,f"XG-C{i:03}",b1.id,["POSTER","SEARCH"],i%4==0)
    pre=fingerprint(list_journeys(db,b1.id))
    from src.config.database import SessionLocal
    user=analyst(db)
    def work():
        with SessionLocal() as s:
            data=payload(*[rec(f"XG-D{i:03}",1,b1.id,["COMMUNITY"],False) for i in range(300)],source="bulk.json")
            import_journeys(s,ImportInput(**data),user)
    t=threading.Thread(target=work);observed=set()
    with SessionLocal() as reader:
        t.start()
        while t.is_alive():
            reader.rollback();observed.add(fingerprint(list_journeys(reader,b1.id)))
        t.join()
    post=fingerprint(list_journeys(db,b1.id))
    assert pre!=post and observed<={pre,post} and observed

def test_existing_runs_and_scenarios_keep_original_values(db):
    b1,_=batches(db)
    run=AttributionRun(name="基线研究",batch_id=b1.id,status="completed",result={"input_hash":"base-hash","credits":[{"code":"POSTER","share":1.0}]},owner="许晴 · 路径研究员")
    db.add(run);db.flush()
    sc=BudgetScenario(name="基线情景",run_id=run.id,budget=5000.,capacity_overrides={},status="completed",review_status="approved",result={"input_hash":"sc-hash","attribution_hash":"base-hash"},owner="许晴 · 路径研究员",reviewer="陈照 · 传播负责人",review_note="批准归档")
    db.add(sc);db.commit();run_result,sc_result=dict(run.result),dict(sc.result)
    do_import(db,payload(rec("XG-T090",1,b1.id,["POSTER"],True),dict(code="XG-T090",revision=2,withdraw=True)))
    db.expire_all()
    assert db.get(AttributionRun,run.id).result==run_result and db.get(BudgetScenario,sc.id).result==sc_result

def test_annotate_withdrawn_journey_rejected(db):
    from fastapi import HTTPException
    from src.schemas.journey import JourneyAnnotation
    from src.services.journey_service import annotate_journey
    b1,_=batches(db)
    row=add_journey(db,"XG-T080",b1.id,["POSTER"],False)
    do_import(db,payload(dict(code="XG-T080",revision=2,withdraw=True)))
    try:annotate_journey(db,row.id,JourneyAnnotation(note="尝试备注已撤回路径"),analyst(db));assert False
    except HTTPException as e:assert e.status_code==404

def token(db,role):
    user=db.query(User).filter_by(role=role).first()
    return jwt.encode({"sub":str(user.id)},JWT_SECRET,algorithm="HS256")

def test_import_endpoint_permissions_and_report(db):
    from src.main import app
    b1,_=batches(db)
    body=payload(rec("XG-T100",1,b1.id,["POSTER"],True))
    with TestClient(app) as client:
        assert client.post("/journeys/import",json=body).status_code==401
        assert client.post("/journeys/import",json=body,headers={"Authorization":"Bearer "+token(db,"viewer")}).status_code==403
        ok=client.post("/journeys/import",json=body,headers={"Authorization":"Bearer "+token(db,"analyst")})
        assert ok.status_code==200 and ok.json()["applied"] and ok.json()["records"][0]["outcome"]=="imported"
        conflict=client.post("/journeys/import",json=payload(rec("XG-T100",1,b1.id,["SEARCH"],False)),headers={"Authorization":"Bearer "+token(db,"admin")})
        assert conflict.status_code==200 and conflict.json()["applied"] is False
        assert conflict.json()["records"][0]["outcome"]=="conflict"
    assert db.query(Journey).filter_by(code="XG-T100").one().path==["POSTER"]
