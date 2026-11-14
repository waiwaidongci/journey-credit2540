from fastapi import HTTPException
from sqlalchemy import text
from ..models import JourneyBatch,Journey,Channel
from ..utils.serialize import record
from .audit_service import log

# 串行化并发补传：同一时刻只允许一个导入事务，第二个等待前一事务提交后再按修订号裁决
IMPORT_LOCK_KEY=20261114

def list_journeys(db,bid):
    if not db.get(JourneyBatch,bid):raise HTTPException(404,"路径批次不存在")
    return [record(j) for j in db.query(Journey).filter_by(batch_id=bid,withdrawn=False).order_by(Journey.code)]
def annotate_journey(db,jid,data,user):
    row=db.get(Journey,jid)
    if not row or row.withdrawn:raise HTTPException(404,"路径不存在或已撤回")
    row.note=data.note;log(db,user.email,"journey.annotate",row.id);db.commit();return record(row)

def _content(rec):
    # 内容身份：撤回标记、归属批次、触点顺序、终点；备注是研究员本地标注，不参与冲突判定
    if rec.withdraw:return ("withdraw",)
    return ("path",rec.batch_id,tuple(rec.path or ()),rec.converted)
def _stored_content(row):
    if row.withdrawn:return ("withdraw",)
    return ("path",row.batch_id,tuple(row.path),row.converted)

def import_journeys(db,data,user):
    if db.get_bind().dialect.name=="postgresql":db.execute(text("SELECT pg_advisory_xact_lock(:k)"),{"k":IMPORT_LOCK_KEY})
    channels={c.code for c in db.query(Channel)}
    batches={b.id for b in db.query(JourneyBatch)}
    if not batches:raise HTTPException(400,"无可用路径批次，无法补传")
    problems={}
    def reject(rec,msg):problems.setdefault((rec.code,rec.revision),msg)
    for rec in data.records:
        if rec.batch_id is not None and rec.batch_id not in batches:reject(rec,"归属批次不存在")
        if rec.withdraw:continue
        if rec.batch_id is None:reject(rec,"缺少归属批次")
        if rec.path is None:reject(rec,"缺少触点路径")
        elif len(rec.path)>50 or any(type(c) is not str or c not in channels for c in rec.path):reject(rec,"路径包含未知渠道或长度超过50")
        if type(rec.converted) is not bool:reject(rec,"缺少转化终点标记")
    winners={}
    for rec in data.records:
        cur=winners.get(rec.code)
        if cur is None or rec.revision>cur.revision:winners[rec.code]=rec
    seen={}
    for rec in data.records:
        key=(rec.code,rec.revision)
        if key in seen and seen[key]!=_content(rec):reject(rec,"同一补传内同版内容冲突")
        seen[key]=_content(rec)
    stored={j.code:j for j in db.query(Journey).filter(Journey.code.in_(list(winners)))} if winners else {}
    for code,rec in winners.items():
        row=stored.get(code)
        if row and rec.revision==row.revision and _content(rec)!=_stored_content(row):reject(rec,"与已接收的同版内容冲突")
    def outcome(rec):
        row=stored.get(rec.code)
        if row is None:return ("withdrawn","撤回登记：路径尚未到达，先留撤回标记，旧版晚到不复活") if rec.withdraw else ("imported","新建接收")
        if rec.revision>row.revision:
            if rec.withdraw:return ("withdrawn","撤回生效，路径从批次与研究读取中移除")
            if row.withdrawn:return ("revived","更高修订号合法恢复，覆盖旧撤回标记")
            return ("moved","跨周迁移：归属批次更正，与归因可见性同一事务生效") if row.batch_id!=rec.batch_id else ("updated","修订更新：更高修订号覆盖旧内容")
        if rec.revision==row.revision:return ("unchanged","重复送达，内容一致，幂等跳过")
        return ("stale","旧版晚到：该编号已撤回，不再复活") if row.withdrawn else ("stale",f"旧版晚到：已存在修订号{row.revision}，忽略")
    reports=[];summary={}
    if problems:
        db.rollback()
        for rec in data.records:
            reason=problems.get((rec.code,rec.revision))
            if reason:o,d="conflict" if "冲突" in reason else "invalid",reason
            else:o,d="skipped","整批拒收：因其他记录冲突或无效，本记录未应用"
            reports.append({"code":rec.code,"revision":rec.revision,"accepted":False,"outcome":o,"detail":d});summary[o]=summary.get(o,0)+1
        log(db,user.email,"journey.import.rejected",f"{data.source} records={len(data.records)}")
        db.commit()
        return {"applied":False,"source":data.source,"summary":summary,"records":reports}
    fallback_batch=min(batches)
    for rec in data.records:
        if winners.get(rec.code) is not rec:
            if winners[rec.code].revision>rec.revision:o,d="superseded","同一补传内被更高修订号覆盖"
            else:o,d="duplicate","同一补传内重复送达，内容一致，随首条处理"
            reports.append({"code":rec.code,"revision":rec.revision,"accepted":True,"outcome":o,"detail":d});summary[o]=summary.get(o,0)+1;continue
        o,d=outcome(rec);row=stored.get(rec.code)
        if rec.revision>(row.revision if row else 0):
            if rec.withdraw:
                if row is None:db.add(Journey(code=rec.code,batch_id=rec.batch_id or fallback_batch,path=[],converted=False,note="",revision=rec.revision,withdrawn=True))
                else:row.revision=rec.revision;row.withdrawn=True
            elif row is None:db.add(Journey(code=rec.code,batch_id=rec.batch_id,path=rec.path,converted=rec.converted,note=rec.note or "",revision=rec.revision,withdrawn=False))
            else:row.batch_id=rec.batch_id;row.path=rec.path;row.converted=rec.converted;row.revision=rec.revision;row.withdrawn=False
        reports.append({"code":rec.code,"revision":rec.revision,"accepted":True,"outcome":o,"detail":d});summary[o]=summary.get(o,0)+1
    log(db,user.email,"journey.import",f"{data.source} records={len(data.records)} summary={summary}")
    db.commit()
    return {"applied":True,"source":data.source,"summary":summary,"records":reports}
