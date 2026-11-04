import math
from worker.science import validate_record
def record(**kw): return dict(ra_deg=49.9,dec_deg=-19.4,source_id='tile',source_url='https://www.legacysurvey.org/',checksum='abc',**kw)
def test_coordinate_boundaries():
    r=record()
    for ra in [-1,360,420,float('nan'),float('inf')]:
        r['ra_deg']=ra; assert 'ra_deg' in validate_record(r)
    for ra in [0,359.999]:
        r['ra_deg']=ra; assert 'ra_deg' not in validate_record(r)
def test_declination_and_provenance():
    r=record();r['dec_deg']=91;assert 'dec_deg' in validate_record(r)
    r['dec_deg']=-90;assert not validate_record(r)
    r['source_url']='';assert 'source_url' in validate_record(r)
