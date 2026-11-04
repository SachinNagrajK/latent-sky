from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=root/'worker/backend.py'
s=p.read_text();s=s.replace("if job['kind']!='image': raise ValueError('Quality demo requires operator setup')", "if job['kind']!='image':\n            from .operations import operational_job\n            operational_job(db,job)\n            return")
p.write_text(s)
# Ensure same-key retries return their existing job even when the queue is full.
p=root/'supabase/migrations/202611040001_latent_sky.sql'
s=p.read_text().replace("if (select count(*) from jobs where owner_id=auth.uid()", "select * into result from jobs where owner_id=auth.uid() and idempotency_key=p_key;\nif found then return result; end if;\nif (select count(*) from jobs where owner_id=auth.uid()")
p.write_text(s)
