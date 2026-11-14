import {FormEvent,useEffect,useState} from 'react';
import {useSearchParams} from 'react-router-dom';
import {Upload} from 'lucide-react';
import {useResearchData} from '../hooks/useResearch';
import {useAuth} from '../stores/auth';
import {useAction} from '../hooks/useAction';
import {annotateJourney,importJourneys} from '../api/journeys';
import {BatchSelector} from '../components/BatchSelector';
import {DataTable} from '../components/common/DataTable';
import {Notice} from '../components/common/Notice';
import {ImportReport} from '../types/domain';
import {ImportOutcome} from '../constants/enums';
import {money,number} from '../utils/format';

export function Sources(){
  const s=useResearchData(),{user}=useAuth(),a=useAction(),[params]=useSearchParams();
  const [selected,setSelected]=useState(Number(params.get('batch'))||0),[editing,setEditing]=useState(0),[note,setNote]=useState('');
  const [importing,setImporting]=useState(false),[source,setSource]=useState('xg-exhibition-paths-supplement.json'),[payloadText,setPayloadText]=useState(''),[report,setReport]=useState<ImportReport|null>(null);
  const batch=s.batches.find(b=>b.id===selected)||s.batches[0];
  useEffect(()=>{if(batch)s.loadJourneys(batch.id)},[batch?.id,s.loadJourneys]);
  const channelName=(code:string)=>s.channels.find(c=>c.code===code)?.name||code;
  const canImport=user?.role==='admin'||user?.role==='analyst';
  function fillExample(){
    const other=s.batches.find(b=>b.id!==batch?.id);
    setPayloadText(JSON.stringify([
      {code:'XG-90001',revision:1,batch_id:batch?.id,path:['POSTER','SEARCH'],converted:true,note:'补传示例：首周晚到路径'},
      {code:'XG-00001',revision:2,batch_id:other?.id??batch?.id,path:['POSTER','COMMUNITY','SEARCH'],converted:false},
      {code:'XG-00002',revision:2,withdraw:true}
    ],null,2));
  }
  function submitImport(e:FormEvent){
    e.preventDefault();
    a.execute(async()=>{
      let records:unknown;
      try{records=JSON.parse(payloadText)}catch{throw new Error('补传内容不是有效JSON，请检查格式');}
      if(!Array.isArray(records)||!records.length)throw new Error('补传内容需为非空记录数组');
      const r=await importJourneys({source,records});
      setReport(r);
      if(r.applied){await s.refresh();if(batch)await s.loadJourneys(batch.id);}
    });
  }
  return <div className="page">
    <div className="page-title">
      <div><p className="eyebrow">SOURCE FOLD / 02</p><h1>路径与渠道<span>保留触点顺序、循环与未转化终点。</span></h1></div>
      {canImport&&<button className="outline" onClick={()=>{setImporting(v=>!v);setReport(null)}}><Upload size={14}/> 补传路径</button>}
    </div>
    <Notice message={s.error||a.error} retry={s.refresh}/>
    {importing&&canImport&&<form className="import-form" onSubmit={submitImport}>
      <label>来源标识<input aria-label="来源标识" value={source} onChange={e=>setSource(e.target.value)} minLength={2} maxLength={200} required/></label>
      <label>补传记录（JSON数组，每条含匿名编号code与来源修订号revision；撤回用{"{\"withdraw\":true}"}）<textarea aria-label="补传记录" value={payloadText} onChange={e=>setPayloadText(e.target.value)} required placeholder='[{"code":"XG-90001","revision":1,"batch_id":1,"path":["POSTER"],"converted":false}]'/></label>
      <div><button className="primary" disabled={a.busy}>校验并导入</button><button type="button" className="outline" onClick={fillExample}>填入示例</button><button type="button" className="outline" onClick={()=>setImporting(false)}>收起</button></div>
      <p className="caption">同一匿名编号按来源修订号取新；撤回登记后旧版晚到不复活；同版内容冲突或记录无效时整批拒收；跨周迁移与归因可见性在同一事务生效，研究只读到完整的导入前或导入后路径。</p>
    </form>}
    {report&&<div className="import-report">
      <div className="section-heading"><h2>补传{report.applied?'已应用':'整批拒收'}</h2><span>{report.source} · {Object.entries(report.summary).map(([k,v])=>`${ImportOutcome[k as keyof typeof ImportOutcome]||k} ${v}`).join(' · ')}</span></div>
      {!report.applied&&<Notice message="存在冲突或无效记录，整批未应用；修正后可重新提交，已接收内容不受影响。"/>}
      <DataTable head={['匿名编号','修订号','处置','说明']}>{report.records.map((r,i)=><tr key={r.code+'-'+r.revision+'-'+i}><td className="mono">{r.code}</td><td className="mono">{r.revision}</td><td><span className={'terminal'+(r.accepted?' converted':'')}>{r.accepted?'接收':'拒绝'} · {ImportOutcome[r.outcome as keyof typeof ImportOutcome]||r.outcome}</span></td><td className="path-cell">{r.detail}</td></tr>)}</DataTable>
    </div>}
    <BatchSelector batches={s.batches} value={batch?.id||0} onChange={setSelected}/>
    <p className="caption">{batch?.description} 展示当前批次全部在册路径；路径以START开端、CONVERSION或NULL闭合，不含个人标识；已撤回路径不再展示也不进入归因。</p>
    {editing>0&&<form className="annotation" onSubmit={e=>{e.preventDefault();a.execute(async()=>{await annotateJourney(editing,note);setEditing(0);await s.loadJourneys(batch!.id)})}}><label>路径备注<input aria-label="路径备注" value={note} onChange={e=>setNote(e.target.value)} minLength={8} required/></label><button className="primary">保存备注</button><button type="button" className="outline" onClick={()=>setEditing(0)}>取消</button></form>}
    <DataTable head={['匿名路径','修订号','顺序触点（START →）','终点','操作']}>{s.journeys.map(j=><tr key={j.id}><td className="mono">{j.code}</td><td className="mono">{j.revision}</td><td className="path-cell">{j.path.map(channelName).join(' → ')||'直接路径'}</td><td><span className={'terminal '+(j.converted?'converted':'')}>{j.converted?'CONVERSION':'NULL'}</span></td><td>{user?.role!=='viewer'&&<button className="text-link" onClick={()=>{setEditing(j.id);setNote(j.note)}}>补充备注</button>}</td></tr>)}</DataTable>
    <div className="section-heading"><h2>渠道约束底稿</h2><span>新归因运行保存此时的成本/容量快照</span></div>
    <DataTable head={['渠道','标识','模拟单位成本','容量上限','口径']}>{s.channels.map(c=><tr key={c.id}><td>{c.name}</td><td className="mono">{c.code}</td><td>{money(c.unit_cost)}</td><td>{number(c.capacity,0)}</td><td>{c.description}</td></tr>)}</DataTable>
  </div>;
}
