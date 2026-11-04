grant all on public.demo_admins to service_role;
create index if not exists jobs_queue_idx on public.jobs(created_at) where status='queued';
create index if not exists detections_job_idx on public.detections(job_id);
create index if not exists artifacts_job_idx on public.artifacts(job_id);
create index if not exists staging_job_idx on public.ingest_staging(job_id);
create or replace function public.schedule_health() returns void language plpgsql security definer set search_path=public as $$ begin
 update jobs set status=case when attempt<3 then 'queued' else 'failed' end,lease_token=null,error='Worker lease expired',updated_at=now() where status='running' and lease_expires_at<now();
 insert into jobs(owner_id,case_id,kind,idempotency_key)
 select user_id,'cosmic-stitch','health',gen_random_uuid() from demo_admins where not exists(select 1 from jobs where kind='health' and status in ('queued','running')) limit 1;
end $$;
revoke all on function public.schedule_health() from public,anon,authenticated;
grant execute on function public.schedule_health() to service_role;
-- Enable pg_cron from Supabase Integrations first if your project does not have it.
create extension if not exists pg_cron;
select cron.schedule('latent-sky-archive-health','*/5 * * * *','select public.schedule_health()');
