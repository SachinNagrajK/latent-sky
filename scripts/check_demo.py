"""Real local acceptance checks; optional live-service verification."""
import sys,json,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from astropy.io import fits
from worker.science import ROOT,process,read_cube,validate_record,sha
parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');args=parser.parse_args()
for case in ['cosmic-stitch','faint-sources']:
    manifest,detections=process(case,ROOT/'output'/case)
    assert all(e['coverage_fraction']>.8 and sha(ROOT/e['path'])==e['checksum'] for e in manifest['inputs'])
    if case=='cosmic-stitch':
        coverage=fits.getdata(ROOT/'output'/case/'coverage.fits')
        assert np.nanmax(coverage)>=4 and coverage.shape[0]>=950
    else:
        matched=[d for d in detections if d['catalog_id']]
        assert matched,'Catalog gate FAILED: download verified reference catalog first'
        assert all(d['match_separation_arcsec']<2 for d in matched)
    print('PASS',case,manifest['duration_seconds'],'seconds')
row=dict(ra_deg=420,dec_deg=27.9,source_id='fault',source_url='https://example.org',checksum='test')
assert 'ra_deg' in validate_record(row)
row['ra_deg']=195.033738
assert validate_record(row)==[]
print('PASS local malformed-coordinate rejection and correction')
if args.live:
    from worker.backend import Backend
    db=Backend()
    for table in ['jobs','observations','detections','artifacts','quality_snapshots']:
        rows=db.request('GET','/rest/v1/'+table+'?select=*&limit=1')
        assert rows,f'Live gate incomplete: {table} has no evidence'
    evidence=db.request('GET','/rest/v1/quality_snapshots?provider=eq.sodabase&select=*')
    assert any(e['raw_response'] for e in evidence),'No actual Sodabase response'
    print('Live records present. Two-user RLS and expired-lease tests still require authenticated test users.')
else: print('Live Supabase, RLS, Cron, and Sodabase checks NOT RUN; use --live once connected.')
