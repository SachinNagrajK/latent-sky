import argparse,time
from .science import ROOT,CASES,process
parser=argparse.ArgumentParser()
parser.add_argument('--local',choices=list(CASES))
args=parser.parse_args()
if args.local:
    m,d=process(args.local,ROOT/'output'/args.local,lambda n,s:print(n,s,flush=True))
    print('Finished',m['duration_seconds'],'seconds;',len(d),'detections')
else:
    from .backend import Backend,run_job
    try: db=Backend()
    except KeyError: raise SystemExit('Configure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env first.')
    print('Worker ready; one job at a time.',flush=True)
    while True:
        jobs=db.rpc('claim_job',{})
        if jobs: run_job(db,jobs[0])
        else: time.sleep(3)
