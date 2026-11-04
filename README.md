# Latent Sky

Real Legacy Surveys DR10 FITS processing with a React explorer, a local Python worker, and a Supabase backend contract. The source lives in `C:\personal\supa`.

## Current state

No email or password is required. A private guest workspace is created automatically. Saved results belong to this browser session; clearing site data loses access to that guest workspace. Keep the local Python worker running for new jobs.


- Both real image pipelines run locally. The public preview assets are exported from those pipeline outputs, never generated illustrations.
- The interface supports science/model/residual layers, coverage, tile boundaries, measured source inspection, provenance downloads, and connected-account jobs/reviews.
- Public app: https://sachinnagrajk.github.io/latent-sky/ . Supabase project pjevtfddhnbubcombfml has both migrations applied. Both authenticated processing cases completed: 13 stored artifacts and 20 detections. The worker runs locally and must stay running. Sodabase project latent sky is connected under the requested account; embedded rule responses remain unconfigured.
- The asteroid extension is deferred.

## Start

Use Node 22+ with npm (or pnpm) and Python 3.12. From the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock.txt
npm install
python scripts/prepare_fixtures.py
python scripts/prepare_catalog.py
python -m worker --local cosmic-stitch
python -m worker --local faint-sources
python scripts/export_preview.py
npm run dev
```

`python scripts/check_demo.py` recomputes both cases and verifies coverage, checksums, a real catalog match, and coordinate rejection. `python -m pytest` checks boundary handling. `npm run build` typechecks and produces `dist`.

## Connect Supabase

1. Finish creating the Latent Sky project in your Supabase organization (free plan is sufficient). Enter its database password directly in Supabase; do not put it in source control.
2. Apply `supabase/migrations/202611040001_latent_sky.sql` using the SQL editor or Supabase CLI. Apply subsequent migrations in filename order.
3. Copy `.env.example` to `.env` and supply your project URL, browser publishable key, and backend service credential. Never prefix a backend credential with `VITE_`.
4. Deploy the `submit-run` Edge Function using `supabase functions deploy submit-run --project-ref YOUR_REF`. The current web release calls the authenticated enqueue_job RPC directly. It validates identity, presets, parameter bounds, rate limits and idempotency. The supplied Edge Function is optional and has not been deployed.
5. Add your app origin to Supabase Auth redirect URLs. Enable your preferred email login flow.
6. Run `python -m worker`. It claims jobs using `SKIP LOCKED`, heartbeats every 25 seconds, and commits results only with the current lease token. Keep the process running.
7. Restart/build the web app after setting browser environment variables. Sign in, run a case, and verify it survives reload.

The `astronomy` bucket is private. Output paths begin with the authenticated owner's ID; signed download links expire after one hour. Original public archive files are backend-only. No browser role can write trusted detections, job status, or quality snapshots.

## Sodabase

Connect the same Supabase project through Sodabase's official authorization flow. Watch `ingest_staging`, `observations`, `detections`, and `pipeline_events`; inspect its grants because its read-only role can see watched rows beyond app RLS.

Supply `SODABASE_TOKEN` only in the worker environment. The worker discovers the actual `check_rule` schema before calling it and validates `SODABASE_RULE_ARGUMENTS_JSON` against that schema. Configure that JSON using the real project dataset ID and intended RA rule. No REST endpoints or undocumented rule argument shapes are assumed. Responses are stored verbatim with provider attribution. Until response semantics are bound to the live service, the app shows “evidence received” rather than inventing a passing verdict or score.

Use `python scripts/discover_sodabase.py` to print live tool schemas without printing credentials. Add the authorized owner UUID to demo_admins using the SQL editor to enable staging-only fault/correct controls and bounded scheduled health checks. Actual rule scope, violation-count parsing, live fault/recovery, and scheduled monitor validation must be completed with the connected account.

## Scientific limits

z/r/g map to red/green/blue with a recorded Lupton stretch. Overlapping survey stacks do not provide independent exposure depth. FITS pixels remain floating point; missing coverage is preserved in FITS and displayed separately. Coadd acquisition dates are unknown unless provided by the archive; retrieval dates are not substituted.

Source extraction uses a local SEP background, a five-sigma threshold and 3-pixel aperture flux estimates in the original r band. Errors omit correlated-noise corrections. Edge, central-halo and SEP flags mark suspected artifacts. No source is classified as extended without a measured PSF. A catalog absence does not demonstrate a discovery or Coma membership. The model and residual are review aids, not proof of novelty. Full survey bit masks are not yet integrated.

## Remaining acceptance gates

Live job creation/storage/reload, two-user RLS isolation, expired-worker lease fencing, actual Sodabase rule results and fault/recovery, and two scheduled health executions require the connected project. Do not describe these as tested until the live checks pass.

Attribution and use requirements: https://www.legacysurvey.org/acknowledgment/ . Input URLs, checksums, WCS, units, and processing parameters are in fixture and output manifests. Keep FITS caches, secrets, and local runtime directories out of Git.
