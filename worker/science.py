from pathlib import Path
import hashlib, json, time, platform
from datetime import datetime, timezone
import httpx
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from astropy.coordinates import SkyCoord
from astropy import units as u
from astropy.visualization import make_lupton_rgb
from reproject import reproject_interp
from reproject.mosaicking import find_optimal_celestial_wcs, reproject_and_coadd
from PIL import Image
import sep

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'fixtures/cache'
CASES = {'cosmic-stitch': (49.921026, -19.411163, .7), 'faint-sources': (195.033738, 27.977025, .262)}
def now(): return datetime.now(timezone.utc).isoformat()
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def validate_record(row):
    errors=[]
    for name,lo,hi in [('ra_deg',0,360),('dec_deg',-90,90)]:
        v=row.get(name)
        if not isinstance(v,(int,float)) or not np.isfinite(v) or v<lo or v>hi or (name=='ra_deg' and v==hi): errors.append(name)
    for key in ['source_id','source_url','checksum']:
        if not row.get(key): errors.append(key)
    return errors

def fetch(url, name):
    CACHE.mkdir(parents=True,exist_ok=True)
    p=CACHE/name
    if p.exists() and p.with_suffix(p.suffix+'.sha256').exists() and sha(p)==p.with_suffix(p.suffix+'.sha256').read_text(): return p,True
    with httpx.stream('GET',url,timeout=180,follow_redirects=True) as r:
        r.raise_for_status(); data=bytearray()
        for chunk in r.iter_bytes():
            data.extend(chunk)
            if len(data)>15_000_000: raise ValueError('Archive product exceeds 15 MB limit')
    temp=p.with_suffix('.tmp'); temp.write_bytes(data); temp.replace(p)
    p.with_suffix(p.suffix+'.sha256').write_text(sha(p))
    return p,False

def read_cube(path):
    with fits.open(path) as hdus:
        hdu=next((h for h in hdus if h.data is not None and h.data.ndim==3),None)
        if hdu is None: raise ValueError('Expected a three-band image cube; inspect archive layout')
        data=np.array(hdu.data,dtype=np.float32); header=hdu.header.copy()
    if data.shape[0]!=3: raise ValueError('Expected exactly three bands')
    bands=[str(header.get(f'BAND{i}', '')).strip() for i in range(3)]
    if bands!=['g','r','z']: raise ValueError(f'Unexpected FITS band metadata: {bands}')
    wcs=WCS(header).celestial
    if not wcs.has_celestial: raise ValueError('Missing celestial WCS')
    world=wcs.pixel_to_world_values(data.shape[2]/2,data.shape[1]/2)
    if not np.all(np.isfinite(world)): raise ValueError('Invalid WCS')
    valid=np.isfinite(data).all(axis=0)&np.any(data!=0,axis=0)
    if valid.mean()<.8: raise ValueError(f'Insufficient archive coverage: {valid.mean():.1%}')
    return data,wcs,header,valid

def prepare(slug):
    ra,dec,scale=CASES[slug]; center=SkyCoord(ra*u.deg,dec*u.deg)
    entries=[]
    if slug=='cosmic-stitch':
        fields=[(f'tile-{i}',center.spherical_offsets_by(dx*u.arcsec,dy*u.arcsec),'ls-dr10') for i,(dx,dy) in enumerate([(-156.8,-156.8),(156.8,-156.8),(-156.8,156.8),(156.8,156.8)])]
    else: fields=[(kind,center,layer) for kind,layer in [('science','ls-dr10'),('model','ls-dr10-model'),('residual','ls-dr10-resid')]]
    for name,coord,layer in fields:
        url=f'https://www.legacysurvey.org/viewer/fits-cutout?ra={coord.ra.deg:.9f}&dec={coord.dec.deg:.9f}&layer={layer}&pixscale={scale}&bands=grz&size=512'
        p,cached=fetch(url,f'{slug}-{name}.fits'); data,wcs,header,valid=read_cube(p)
        entries.append(dict(source_id=p.stem,source_url=url,checksum=sha(p),path=str(p.relative_to(ROOT)),ra_deg=float(coord.ra.deg),dec_deg=float(coord.dec.deg),band='grz',units=header.get('BUNIT','not supplied by cutout header'),observed_at=None,observation_date_reason='Survey coadd spans multiple exposures; acquisition interval not supplied by cutout',retrieved_at=datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat(),coverage_fraction=float(valid.mean()),wcs_summary=dict(wcs.to_header()),cached=cached,kind=name))
    if sum((ROOT/e['path']).stat().st_size for e in entries)>50_000_000: raise ValueError('Input budget exceeds 50 MB')
    manifest=dict(case=slug,inputs=entries,attribution='DESI Legacy Imaging Surveys DR10',source_policy='https://www.legacysurvey.org/acknowledgment/',created_at=now())
    folder=ROOT/'fixtures/manifests'; folder.mkdir(parents=True,exist_ok=True)
    (folder/f'{slug}.json').write_text(json.dumps(manifest,indent=2))
    return manifest

def rgb(cube, path, stretch=1):
    clean=np.nan_to_num(cube,nan=0,posinf=0,neginf=0)
    image=make_lupton_rgb(clean[2],clean[1],clean[0],stretch=stretch,Q=8)
    Image.fromarray(np.flipud(image)).save(path)

def process(slug, out, progress=lambda *a:None, stretch=1):
    start=time.monotonic(); out=Path(out); out.mkdir(parents=True,exist_ok=True)
    progress(10,'Fetching and verifying archive inputs'); manifest=prepare(slug)
    cubes=[read_cube(ROOT/e['path']) for e in manifest['inputs']]
    progress(40,'Reprojecting tiles' if slug=='cosmic-stitch' else 'Measuring sources')
    detections=[]
    if slug=='cosmic-stitch':
        grid,shape=find_optimal_celestial_wcs([(c[0][0],c[1]) for c in cubes],resolution=.7*u.arcsec)
        bands=[]; footprints=[]
        for band in range(3):
            mosaic,foot=reproject_and_coadd([(np.where(c[3],c[0][band],np.nan),c[1]) for c in cubes],grid,shape_out=shape,reproject_function=reproject_interp,combine_function='mean',blank_pixel_value=np.nan)
            bands.append(mosaic); footprints.append(foot)
            fits.writeto(out/f'mosaic-{ "grz"[band] }.fits',mosaic,grid.to_header(),overwrite=True)
        cube=np.array(bands); coverage=np.min(footprints,axis=0)
        fits.writeto(out/'coverage.fits',coverage,grid.to_header(),overwrite=True)
        Image.fromarray(np.flipud(np.uint8(np.clip(coverage/4,0,1)*255))).save(out/'coverage.png')
        rgb(cube,out/'science.png',stretch)
        mono=np.nan_to_num(cube[1]); mono=np.arcsinh(np.maximum(mono,0)/stretch); mono/=max(float(np.percentile(mono,99.5)),1e-8)
        Image.fromarray(np.flipud(np.uint8(np.clip(mono,0,1)*255))).save(out/'r-band.png')
        manifest['tile_polygons']=[np.array(grid.world_to_pixel(c[1].pixel_to_world([0,511,511,0],[0,0,511,511]))).T.tolist() for c in cubes]
        manifest['shape']=list(shape)
    else:
        cube,wcs,header,valid=cubes[0]
        for e,c in zip(manifest['inputs'],cubes): rgb(c[0],out/f'{e["kind"]}.png',stretch)
        data=np.ascontiguousarray(np.nan_to_num(cube[1]),dtype=np.float64)
        background=sep.Background(data,mask=~valid,bw=32,bh=32)
        clean=data-background.back(); noise=background.rms()
        objects=sep.extract(clean,5,err=noise,mask=~valid,minarea=5)
        flux,err,flags=sep.sum_circle(clean,objects['x'],objects['y'],3,err=noise,mask=~valid)
        catalog_path=ROOT/'fixtures/catalogs/coma.csv'
        catalog=None
        if catalog_path.exists():
            from astropy.table import Table
            catalog=Table.read(catalog_path,format='ascii.csv')
            coords=SkyCoord(catalog['ra']*u.deg,catalog['dec']*u.deg)
        for i,obj in enumerate(objects):
            point=wcs.pixel_to_world(obj['x'],obj['y']); edge=min(obj['x'],obj['y'],511-obj['x'],511-obj['y'])<12
            # Bright central galaxy and SEP flags are conservative review flags, not scientific classifications.
            central=point.separation(SkyCoord(CASES[slug][0]*u.deg,CASES[slug][1]*u.deg)).arcsec<20
            item=dict(source_index=i,x=float(obj['x']),y=float(obj['y']),ra_deg=float(point.ra.deg),dec_deg=float(point.dec.deg),flux=float(flux[i]),flux_error=float(err[i]),size_pixels=float(np.sqrt(obj['a']*obj['b'])),flags=int(obj['flag'])|int(flags[i]),catalog_id=None,match_separation_arcsec=None,classification='unmatched candidate',artifact_reasons=['edge'] if edge else ['central galaxy halo'] if central else [])
            if catalog is not None and len(catalog):
                idx,sep2d,_=point.match_to_catalog_sky(coords)
                if sep2d.arcsec<2:
                    item.update(catalog_id=str(catalog['ls_id'][int(np.asarray(idx).item())]),match_separation_arcsec=float(np.asarray(sep2d.arcsec).item()),classification='catalog matched')
            if edge or central or item['flags']: item['classification']='artifact suspected'
            detections.append(item)
        (out/'detections.json').write_text(json.dumps(detections,indent=2))
        if (ROOT/'fixtures/catalogs/manifest.json').exists(): manifest['catalog_provenance']=json.loads((ROOT/'fixtures/catalogs/manifest.json').read_text())
        manifest.update(shape=[512,512],catalog_available=catalog is not None,threshold_sigma=5,match_tolerance_arcsec=2,psf_status='Not estimated; no extended-source classifications assigned',noise_method='SEP local background RMS; aperture errors omit correlated-noise correction')
    manifest.update(parameters=dict(stretch=stretch,Q=8,color_mapping={'red':'z','green':'r','blue':'g'}),duration_seconds=round(time.monotonic()-start,3),python=platform.python_version(),generated_at=now(),independent_exposure_depth=False)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    progress(85,'Saving reproducible outputs')
    return manifest,detections
