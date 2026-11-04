create extension if not exists pgcrypto;
create table public.sample_cases (id text primary key, title text not null, ra_deg double precision not null check(ra_deg>=0 and ra_deg<360), dec_deg double precision not null check(dec_deg between -90 and 90), recipe jsonb not null default '{}', enabled boolean not null default true);
insert into public.sample_cases values ('cosmic-stitch','NGC 1300 · Cosmic Stitch',49.921026,-19.411163,'{"bands":"grz","tiles":4}'),('faint-sources','Coma · Faint Source Explorer',195.033738,27.977025,'{"bands":"grz","sigma":5}');
create table public.jobs (id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users, case_id text not null references public.sample_cases, kind text not null default 'image' check(kind in ('image','fault','repair','health')), status text not null default 'queued' check(status in ('queued','running','complete','failed')), progress int not null default 0 check(progress between 0 and 100), stage text, parameters jsonb not null default '{}', idempotency_key uuid not null, attempt int not null default 0, lease_token uuid, lease_expires_at timestamptz, error text, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(owner_id,idempotency_key));
create table public.ingest_staging (id uuid primary key default gen_random_uuid(),job_id uuid not null references public.jobs on delete cascade,source_id text,ra_deg double precision,dec_deg double precision,band text,observed_at timestamptz,retrieved_at timestamptz,source_url text,checksum text,validation_state text not null default 'pending',is_demo_fault boolean not null default false,created_at timestamptz not null default now());
create table public.observations (id uuid primary key default gen_random_uuid(),archive text not null,product_id text not null,band text not null,ra_deg double precision not null check(ra_deg>=0 and ra_deg<360),dec_deg double precision not null check(dec_deg between -90 and 90),observed_at timestamptz,storage_path text not null,checksum text not null,wcs_summary jsonb not null,units text,coverage_fraction double precision not null check(coverage_fraction between 0 and 1),metadata jsonb not null default '{}',created_at timestamptz not null default now(),unique(archive,product_id,band,checksum));
create table public.job_inputs (job_id uuid references public.jobs on delete cascade,observation_id uuid references public.observations,primary key(job_id,observation_id));
create table public.detections (id uuid primary key default gen_random_uuid(),job_id uuid not null references public.jobs on delete cascade,observation_id uuid references public.observations,source_index int not null,x double precision,y double precision,ra_deg double precision not null check(ra_deg>=0 and ra_deg<360),dec_deg double precision not null check(dec_deg between -90 and 90),flux double precision,flux_error double precision,size_pixels double precision,flags int,catalog_id text,match_separation_arcsec double precision,classification text not null check(classification in ('catalog matched','unmatched candidate','artifact suspected')),artifact_reasons jsonb default '[]',created_at timestamptz not null default now(),unique(job_id,source_index));
create table public.artifacts (id uuid primary key default gen_random_uuid(),job_id uuid not null references public.jobs on delete cascade,kind text not null,storage_path text not null,manifest_path text not null,checksum text not null,parameters jsonb not null default '{}',created_at timestamptz not null default now(),unique(job_id,kind));
create table public.reviews (id uuid primary key default gen_random_uuid(),owner_id uuid not null references auth.users,detection_id uuid not null references public.detections on delete cascade,label text not null,note text not null default '',created_at timestamptz not null default now(),updated_at timestamptz not null default now(),unique(owner_id,detection_id));
create table public.pipeline_events (id uuid primary key default gen_random_uuid(),job_id uuid not null references public.jobs on delete cascade,stage text not null,status text not null,rows_processed int not null default 0 check(rows_processed>=0),duration_ms int not null default 0 check(duration_ms>=0),created_at timestamptz not null default now());
create table public.quality_snapshots (id uuid primary key default gen_random_uuid(),job_id uuid not null references public.jobs on delete cascade,provider text not null check(provider in ('app','sodabase')),dataset text not null,tool text,verdict text not null,violation_count int,findings jsonb not null default '[]',provider_checked_at timestamptz,fetched_at timestamptz not null default now(),raw_response jsonb);
create table public.demo_admins (user_id uuid primary key references auth.users);
alter table public.demo_admins enable row level security;
create policy own_admin_status on public.demo_admins for select to authenticated using(user_id=auth.uid());
grant select on public.demo_admins to authenticated;
do $$ declare t text; begin
foreach t in array array['sample_cases','jobs','ingest_staging','observations','job_inputs','detections','artifacts','reviews','pipeline_events','quality_snapshots'] loop
execute format('alter table public.%I enable row level security',t);
execute format('revoke all on public.%I from anon,authenticated',t);
execute format('grant select on public.%I to authenticated',t);
execute format('grant all on public.%I to service_role',t);
end loop; end $$;
create policy case_read on public.sample_cases for select to authenticated using(enabled);
create policy job_read on public.jobs for select to authenticated using(owner_id=auth.uid());
create policy observation_read on public.observations for select to authenticated using(true);
do $$ declare t text; begin foreach t in array array['ingest_staging','job_inputs','detections','artifacts','pipeline_events','quality_snapshots'] loop execute format('create policy owned_job_read on public.%I for select to authenticated using (exists(select 1 from public.jobs j where j.id=job_id and j.owner_id=auth.uid()))',t); end loop; end $$;
grant insert,update on public.reviews to authenticated;
create policy review_read on public.reviews for select to authenticated using(owner_id=auth.uid());
create policy review_insert on public.reviews for insert to authenticated with check(owner_id=auth.uid() and exists(select 1 from public.detections d join public.jobs j on j.id=d.job_id where d.id=detection_id and j.owner_id=auth.uid()));
create policy review_update on public.reviews for update to authenticated using(owner_id=auth.uid()) with check(owner_id=auth.uid() and exists(select 1 from public.detections d join public.jobs j on j.id=d.job_id where d.id=detection_id and j.owner_id=auth.uid()));
create function public.enqueue_job(p_case text,p_key uuid,p_parameters jsonb default '{}',p_kind text default 'image') returns public.jobs language plpgsql security definer set search_path=public as $$ declare result public.jobs; begin
if auth.uid() is null then raise exception 'Sign in required'; end if;
if p_kind not in ('image','fault','repair') then raise exception 'Unsupported action'; end if;
if p_kind<>'image' and not exists(select 1 from demo_admins where user_id=auth.uid()) then raise exception 'Demo administrator required'; end if;
if not exists(select 1 from sample_cases where id=p_case and enabled) then raise exception 'Unknown preset'; end if;
if p_parameters - 'stretch' <> '{}'::jsonb or coalesce((p_parameters->>'stretch')::numeric,1) not between .1 and 10 then raise exception 'Invalid display recipe'; end if;
select * into result from jobs where owner_id=auth.uid() and idempotency_key=p_key;
if found then return result; end if;
if (select count(*) from jobs where owner_id=auth.uid() and status in ('queued','running'))>=3 then raise exception 'Three runs already active'; end if;
insert into jobs(owner_id,case_id,idempotency_key,parameters,kind) values(auth.uid(),p_case,p_key,p_parameters,p_kind) on conflict(owner_id,idempotency_key) do nothing;
select * into result from jobs where owner_id=auth.uid() and idempotency_key=p_key; return result; end $$;
revoke all on function public.enqueue_job(text,uuid,jsonb,text) from public;
grant execute on function public.enqueue_job(text,uuid,jsonb,text) to authenticated;
create function public.claim_job() returns setof public.jobs language plpgsql security definer set search_path=public as $$ begin
update jobs set status=case when attempt<3 then 'queued' else 'failed' end,error='Previous worker lease expired',lease_token=null where status='running' and lease_expires_at<now();
return query update jobs set status='running',attempt=attempt+1,lease_token=gen_random_uuid(),lease_expires_at=now()+interval '90 seconds',updated_at=now() where id=(select id from jobs where status='queued' order by created_at for update skip locked limit 1) returning *; end $$;
create function public.update_run(p_id uuid,p_token uuid,p_progress int,p_stage text,p_error text default null) returns boolean language plpgsql security definer set search_path=public as $$ begin
update jobs set progress=p_progress,stage=p_stage,lease_expires_at=now()+interval '90 seconds',updated_at=now(),error=p_error,status=case when p_error is not null then case when attempt<3 then 'queued' else 'failed' end else status end where id=p_id and lease_token=p_token and status='running' and lease_expires_at>now(); return found; end $$;
create function public.finish_run(p_id uuid,p_token uuid,p_artifacts jsonb,p_detections jsonb,p_quality jsonb) returns void language plpgsql security definer set search_path=public as $$ declare a jsonb; begin
perform 1 from jobs where id=p_id and lease_token=p_token and status='running' and lease_expires_at>now() for update;
if not found then raise exception 'Worker lease is no longer valid'; end if;
for a in select * from jsonb_array_elements(p_artifacts) loop insert into artifacts(job_id,kind,storage_path,manifest_path,checksum,parameters) values(p_id,a->>'kind',a->>'storage_path',a->>'manifest_path',a->>'checksum',a->'parameters'); end loop;
insert into detections(job_id,source_index,x,y,ra_deg,dec_deg,flux,flux_error,size_pixels,flags,catalog_id,match_separation_arcsec,classification,artifact_reasons) select p_id,d.source_index,d.x,d.y,d.ra_deg,d.dec_deg,d.flux,d.flux_error,d.size_pixels,d.flags,d.catalog_id,d.match_separation_arcsec,d.classification,d.artifact_reasons from jsonb_to_recordset(p_detections) as d(source_index int,x float8,y float8,ra_deg float8,dec_deg float8,flux float8,flux_error float8,size_pixels float8,flags int,catalog_id text,match_separation_arcsec float8,classification text,artifact_reasons jsonb);
for a in select * from jsonb_array_elements(p_quality) loop insert into quality_snapshots(job_id,provider,dataset,tool,verdict,violation_count,findings,provider_checked_at,raw_response) values(p_id,a->>'provider',a->>'dataset',a->>'tool',a->>'verdict',(a->>'violation_count')::int,a->'findings',(a->>'provider_checked_at')::timestamptz,a->'raw_response'); end loop;
update jobs set status='complete',progress=100,stage='Complete',updated_at=now(),lease_token=null where id=p_id;
end $$;
revoke all on function public.claim_job(),public.update_run(uuid,uuid,int,text,text),public.finish_run(uuid,uuid,jsonb,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.claim_job(),public.update_run(uuid,uuid,int,text,text),public.finish_run(uuid,uuid,jsonb,jsonb,jsonb) to service_role;
insert into storage.buckets(id,name,public,file_size_limit) values('astronomy','astronomy',false,52428800);
create policy output_read on storage.objects for select to authenticated using(bucket_id='astronomy' and (storage.foldername(name))[1]=auth.uid()::text);
alter publication supabase_realtime add table public.jobs,public.reviews;
