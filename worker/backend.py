import os,json,asyncio,threading,mimetypes
from pathlib import Path
import httpx
from dotenv import load_dotenv
from .science import ROOT,process,sha,now,validate_record
load_dotenv(ROOT/'.env')
class Backend:
    def __init__(self):
        self.url=os.environ['SUPABASE_URL'].rstrip('/')
        key=os.environ['SUPABASE_SERVICE_ROLE_KEY']
        headers={'apikey':key}
        # New Supabase secret keys are API keys, not JWTs. Legacy service-role
        # keys still need the bearer header, so support both during migration.
        if not key.startswith('sb_secret_'): headers['Authorization']='Bearer '+key
        self.client=httpx.Client(base_url=self.url,headers=headers,timeout=60)
    def request(self,method,path,**kwargs):
        r=self.client.request(method,path,**kwargs)
        if r.is_error: raise RuntimeError(f'Backend request failed ({r.status_code})')
        return r.json() if r.content else None
    def rpc(self,name,body): return self.request('POST','/rest/v1/rpc/'+name,json=body)
    def insert(self,table,body): return self.request('POST','/rest/v1/'+table,json=body,headers={'Prefer':'return=representation'})
    def upload(self,path,file): self.request('POST','/storage/v1/object/astronomy/'+path,content=Path(file).read_bytes(),headers={'Content-Type':mimetypes.guess_type(str(file))[0] or 'application/octet-stream','x-upsert':'true'})

async def soda_snapshot():
    result=dict(provider='sodabase',dataset='ingest_staging',tool='check_rule',verdict='unknown',violation_count=None,findings=['Sodabase is not connected; no external check has run'],provider_checked_at=None,raw_response=None)
    if not os.getenv('SODABASE_TOKEN'): return result
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    import jsonschema
    try:
        async with streamablehttp_client('https://sodabase.io/mcp',headers={'Authorization':'Bearer '+os.environ['SODABASE_TOKEN']}) as (read,write,_):
            async with ClientSession(read,write) as session:
                await session.initialize()
                rule=next(t for t in (await session.list_tools()).tools if t.name=='check_rule')
                args=json.loads(os.environ.get('SODABASE_RULE_ARGUMENTS_JSON','{}'))
                if not args: raise ValueError('Rule arguments must be configured from the live schema')
                jsonschema.validate(args,rule.inputSchema)
                response=await session.call_tool('check_rule',args)
                result.update(verdict='error' if response.isError else 'evidence received',raw_response=response.model_dump(mode='json'),findings=['Provider response retained without guessing undocumented verdict fields. Review the rule scope and evaluation time.'])
    except Exception as e: result.update(verdict='error',findings=[type(e).__name__+': external check unavailable; inspect worker configuration'])
    return result

def run_job(db,job):
    jid=job['id']; token=job['lease_token']; stop=threading.Event(); lost=threading.Event(); current=[0,'Starting']
    def progress(n,stage):
        current[:]=[n,stage]
        if not db.rpc('update_run',dict(p_id=jid,p_token=token,p_progress=n,p_stage=stage)): lost.set(); raise RuntimeError('Lease expired')
    def heartbeat():
        while not stop.wait(25):
            try: progress(*current)
            except Exception: lost.set(); return
    thread=threading.Thread(target=heartbeat,daemon=True); thread.start()
    try:
        if job['kind']!='image':
            from .operations import operational_job
            operational_job(db,job)
            return
        out=ROOT/'output'/jid/token
        manifest,detections=process(job['case_id'],out,progress,job['parameters'].get('stretch',1))
        if job['case_id']=='faint-sources' and not manifest.get('catalog_available'): raise ValueError('Reference catalog is required for a completed source run')
        for e in manifest['inputs']:
            if lost.is_set(): raise RuntimeError('Lease lost')
            record={k:e[k] for k in ['source_id','source_url','checksum','ra_deg','dec_deg','band','observed_at','retrieved_at']}
            record.update(job_id=jid,validation_state='rejected' if validate_record(record) else 'valid')
            db.insert('ingest_staging',record)
            if validate_record(record): raise ValueError('Invalid scientific metadata')
            storage='archive/'+e['checksum']+'.fits'; db.upload(storage,ROOT/e['path'])
            obs=dict(archive='Legacy Surveys DR10',product_id=e['source_id'],band=e['band'],ra_deg=e['ra_deg'],dec_deg=e['dec_deg'],observed_at=e['observed_at'],storage_path=storage,checksum=e['checksum'],wcs_summary=e['wcs_summary'],units=e['units'],coverage_fraction=e['coverage_fraction'],metadata={'date_reason':e['observation_date_reason'],'source_url':e['source_url']})
            rows=db.request('POST','/rest/v1/observations?on_conflict=archive,product_id,band,checksum',json=obs,headers={'Prefer':'resolution=merge-duplicates,return=representation'})
            db.request('POST','/rest/v1/job_inputs',json={'job_id':jid,'observation_id':rows[0]['id']},headers={'Prefer':'resolution=ignore-duplicates'})
        artifacts=[]; prefix=f"{job['owner_id']}/{jid}/{token}"
        for file in out.iterdir():
            path=prefix+'/'+file.name; db.upload(path,file)
            artifacts.append(dict(kind=file.name,storage_path=path,manifest_path=prefix+'/manifest.json',checksum=sha(file),parameters=manifest['parameters']))
        quality=[dict(provider='app',dataset='archive inputs',tool='FITS metadata validation',verdict='passed',violation_count=0,findings=['Bands, celestial WCS, coverage and checksums verified'],provider_checked_at=now()),asyncio.run(soda_snapshot())]
        db.insert('pipeline_events',dict(job_id=jid,stage='science processing',status='complete',rows_processed=len(detections),duration_ms=int(manifest['duration_seconds']*1000)))
        progress(95,'Committing outputs')
        db.rpc('finish_run',dict(p_id=jid,p_token=token,p_artifacts=artifacts,p_detections=detections,p_quality=quality))
    except Exception as e:
        db.rpc('update_run',dict(p_id=jid,p_token=token,p_progress=0,p_stage='Failed',p_error=f'{type(e).__name__}: processing failed; inspect cached fixtures and service configuration'))
        print('Run failed:',jid,type(e).__name__)
    finally: stop.set(); thread.join(timeout=2)
