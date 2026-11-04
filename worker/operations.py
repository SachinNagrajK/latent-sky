"""Explicit staging-only quality demo and real archive connectivity checks."""
import asyncio,time
from .science import prepare,now,validate_record

def operational_job(db,job):
    from .backend import soda_snapshot
    started=time.monotonic(); jid=job['id']; kind=job['kind']
    quality=[]
    if kind=='health':
        import httpx
        response=httpx.head('https://www.legacysurvey.org/viewer/fits-cutout?ra=49.921026&dec=-19.411163&layer=ls-dr10&pixscale=0.7&bands=grz&size=256',timeout=30,follow_redirects=True)
        quality=[dict(provider='app',dataset='archive endpoint',tool='HTTP HEAD',verdict='passed' if response.is_success else 'failed',violation_count=0 if response.is_success else 1,findings=[{'status_code':response.status_code,'content_type':response.headers.get('content-type'),'note':'Endpoint response only; no new observations inferred'}],provider_checked_at=now())]
    else:
        admins=db.request('GET','/rest/v1/demo_admins?user_id=eq.'+job['owner_id']+'&select=user_id')
        if not admins: raise ValueError('Demo administrator required')
        original=prepare(job['case_id'])['inputs'][0]
        if kind=='fault':
            row={k:original[k] for k in ['source_id','ra_deg','dec_deg','band','source_url','checksum','observed_at','retrieved_at']}
            row.update(job_id=jid,ra_deg=420,is_demo_fault=True,validation_state='rejected')
            row=db.insert('ingest_staging',row)[0]
        elif kind=='repair':
            owned=db.request('GET','/rest/v1/jobs?owner_id=eq.'+job['owner_id']+'&case_id=eq.'+job['case_id']+'&kind=eq.fault&order=created_at.desc&limit=1')
            if not owned: raise ValueError('No fault batch exists for this owner and case')
            rows=db.request('GET','/rest/v1/ingest_staging?job_id=eq.'+owned[0]['id']+'&is_demo_fault=eq.true&select=*')
            if not rows: raise ValueError('No labeled fault record found')
            row=rows[0]
            if row['source_id']!=original['source_id']: raise ValueError('Fault fixture does not match original')
            row.update(ra_deg=original['ra_deg'],validation_state='valid')
            db.request('PATCH','/rest/v1/ingest_staging?id=eq.'+row['id'],json={'ra_deg':row['ra_deg'],'validation_state':'valid'})
        else: raise ValueError('Unsupported operation')
        errors=validate_record(row)
        quality=[dict(provider='app',dataset='ingest_staging',tool='coordinate and provenance validation',verdict='blocked' if errors else 'passed',violation_count=len(errors),findings=[{'staging_id':row['id'],'invalid_fields':errors,'is_demo_fault':True,'curated_promotion':'blocked' if errors else 'test copy only; not promoted'}],provider_checked_at=now()),asyncio.run(soda_snapshot())]
    db.insert('pipeline_events',dict(job_id=jid,stage=kind,status='complete',rows_processed=1,duration_ms=int((time.monotonic()-started)*1000)))
    db.rpc('finish_run',dict(p_id=jid,p_token=job['lease_token'],p_artifacts=[],p_detections=[],p_quality=quality))
