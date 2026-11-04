# Latent Sky: working prototype build plan

Prepared November 4, 2026, for the Supabase + Sodabase + BuilderBase NYC hackathon.

## 1. What we are building

A browser app that turns public telescope observations into beautiful, traceable images and reviewable astronomical candidates. Users choose a prepared sky region, run a real processing job, inspect its output, and see the quality of the data behind it.

**Ship two complete astronomy demos first:** a stitched color image of NGC 1300, and a faint-source explorer near NGC 4889 in the Coma cluster. Add a third demo that recovers a known asteroid from archival images only if a usable image sequence is secured early.

Supabase owns accounts, job state, scientific metadata, saved results, and file storage. Sodabase checks the tables used by the pipeline and provides evidence of data problems. A small Python worker performs image processing.

The success condition is a working end-to-end prototype with real archive inputs and reproducible outputs. A newly discovered galaxy, asteroid, or comet is not a dependency. Candidate detection and data quality are separate concepts: a healthy table does not establish a scientific discovery.

### Current state and planning assumptions

- The user reports that hackathon/team onboarding is complete. Verify that Sodabase is connected to the same Supabase project used by this app.
- The workspace currently contains the hackathon resource PDF, with no application implementation.
- Supabase credit redemption remains unresolved; implementation should not depend on a paid upgrade or select a billing organization automatically.
- This document is a build specification. No database, worker, image processing pipeline, or Sodabase monitor has been deployed by writing it.
- Two sample cutout URLs returned HTTP 200 with `image/fits` on November 4. Their pixel coverage and scientific usability still require inspection during the first build step.

## 2. Prioritized sample cases

| Priority | Case | What the user sees | Completion requirement |
| --- | --- | --- | --- |
| P0 | NGC 1300: Cosmic Stitch | Four grayscale tiles become a color galaxy mosaic, with tile boundaries and source information | Recompute the output from real FITS files; save it through Supabase; show Sodabase rule results for its input records |
| P0 | Coma field: Faint Source Explorer | Image/model/residual comparison, detected-source markers, catalog matches, and a saved review | Produce real detections, distinguish catalog matches from unmatched candidates, and demonstrate a malformed record being caught |
| P1 | Asteroid recovery: 523 Ada | An epoch slider/blink animation, a measured track, and a comparison with a known object's predicted positions | At least three usable real exposures at distinct times; a detection-based track consistent with the known object |

The required release is Cases 1 and 2 plus the shared Sodabase failure-and-recovery demonstration. Case 3 is an extension, not a reason to delay the core release.

### Case 1: NGC 1300 — Cosmic Stitch

**Purpose:** prove that the app can assemble a custom view from scientific inputs, preserve provenance, and produce an attractive result.

**Input selection:** use DESI Legacy Imaging Surveys DR10, `g`, `r`, and `z` bands. NGC 1300's reference center is approximately RA `49.921026°`, Dec `-19.411163°` in ICRS. The position is derived from the [SIMBAD entry](https://simbad.cds.unistra.fr/simbad/sim-id?Ident=NGC1300).

[Reachable center test cutout](https://www.legacysurvey.org/viewer/fits-cutout?ra=49.921026&dec=-19.411163&layer=ls-dr10&pixscale=0.7&bands=grz&size=256): HTTP 200, FITS, 792,000 bytes reported by HEAD. This small center cutout is a connectivity check, not the final mosaic.

Build sequence:

1. Generate a 2 × 2 grid of 512-pixel tiles at 0.7 arcseconds per pixel, overlapping by 64 pixels. The resulting footprint is approximately 11.2 arcminutes across. Calculate tile centers through a tangent-plane WCS or spherical offsets, not naive RA addition.
2. Retrieve the four three-band FITS cutouts, recording URLs, band order, units, WCS, coverage, retrieval time, and SHA-256 checksums. Inspect actual headers rather than assuming image HDU layout.
3. Reject missing coverage and invalid coordinate metadata. Keep masks and original floating-point arrays.
4. Reproject the tiles onto one celestial grid and combine overlaps with valid-pixel weights. Use documented `reproject` mosaicking functions; show a coverage layer. These tiles come from existing survey stacks, so overlapping them does not create independent extra exposure depth.
5. Map `z → red`, `r → green`, `g → blue`, using an asinh/Lupton stretch. Record the stretch and color mapping as processing parameters.
6. Save the RGB PNG, per-band mosaic FITS, coverage map, and provenance manifest to Supabase Storage; write the artifact records and complete the job.
7. Let the user compare a single input band with the final image, toggle tile boundaries, adjust display settings, and save a new composition.

Acceptance:

- The galaxy is visible, spatial alignment is checked, and gaps are displayed as missing coverage.
- A fresh run recomputes an output using cached real FITS inputs; it does not just display a pre-rendered picture.
- The saved result survives a page reload and links to the exact input records and processing recipe.
- Describe it as a custom archival composite. Do not assert that nobody has previously made or viewed this image.

### Case 2: Coma field — Faint Source Explorer

**Purpose:** show how archival pixels can reveal sources worth examining, with evidence and an honest known-object comparison.

**Input selection:** a field centered near NGC 4889 at RA `195.033738°`, Dec `27.977025°`, based on [SIMBAD](https://simbad.cds.unistra.fr/simbad/sim-basic?Ident=NGC+4889&submit=SIMBAD+search). Use a 512-pixel cutout at 0.262 arcseconds per pixel, approximately 2.24 arcminutes across.

[Reachable science cutout](https://www.legacysurvey.org/viewer/fits-cutout?ra=195.033738&dec=27.977025&layer=ls-dr10&pixscale=0.262&bands=grz&size=512): HTTP 200, FITS, 3,150,720 bytes reported by HEAD.

Also request matching model and residual products using `ls-dr10-model` and `ls-dr10-resid`. The survey documents these layer names; availability and useful coverage at this exact field must be verified. Prefer a nearby offset field if the central galaxy's halo dominates source extraction. Freeze the selected coordinates in the fixture manifest before the demo. See the [DR10 image service](https://www.legacysurvey.org/dr10/description/).

Build sequence:

1. Fetch science, model, residual, and available mask/weight products. Obtain a small local catalog subset from the [NOIRLab Legacy Surveys service](https://datalab.noirlab.edu/data/legacy-surveys); inspect its actual schema before writing the query.
2. Detect sources in the original science arrays with a local background model and SEP or Photutils. Start conservatively, for example at five times the estimated local noise, then tune on the fixture.
3. Calculate positions, flux/error estimates, size, and artifact flags. Evaluate measurements on the scientific arrays, before color stretching. Estimate a local stellar PSF before labeling a source as extended.
4. Use residuals to rank structures for inspection, not as automatic proof of new objects. Mask bright-star artifacts, saturated pixels, image edges, and problematic large-galaxy regions. Model mismatch can leave convincing residual structures.
5. Match positions to the catalog using a documented angular tolerance, initially 2 arcseconds and adjusted to the measured astrometric uncertainty. Show the match separation and catalog identifier.
6. Present sources as `catalog matched`, `unmatched candidate`, or `artifact suspected`. A missing catalog match alone does not establish novelty, galaxy type, or Coma membership.
7. Save a user's annotation and classification to Supabase; update the view through Realtime.

Acceptance:

- At least one real, independently detected source is matched to a catalog object. If the initial field cannot support that, select the nearby field during fixture preparation.
- Empty candidate results are valid and displayed honestly. Do not manufacture unmatched detections to make the demo exciting.
- The user can switch between science, model, and residual views and inspect each source's evidence.
- Candidate quality fields and source provenance are present in Supabase, and the shared Sodabase rule demonstration works on the associated staging data.

### Case 3: 523 Ada — recover a known asteroid (optional)

**Purpose:** demonstrate motion detection using old observations, with a known target as the control.

Use the WISE/NEOWISE archive's Solar System Object search for `523` or `Ada`, following [IRSA's moving-object instructions](https://irsa.ipac.caltech.edu/applications/ICORE/docs/movingupload.html). IRSA documents this object as an input example; that is not confirmation that we already have a suitable image sequence.

Fixture gate:

- Spend no more than 20 minutes obtaining at least three W1 exposures from one observing window, with the object in usable coverage and measurable motion.
- Pin the exact image identifiers, acquisition times, masks, object positions, observatory location, and original retrieval information in a manifest.
- If this gate fails, defer the case and ship the two core cases. Do not substitute a simulated sequence and label it as an archival detection.

Processing:

1. Align frames on background stars and normalize their backgrounds.
2. Detect sources per exposure, then link positions with approximately consistent motion over the short time span. Use image quality masks and inspect residuals.
3. Fit a short track and report its measured angular motion and fit residuals. Fit detections before comparing with the known orbit.
4. Compare against [JPL Horizons](https://ssd-api.jpl.nasa.gov/doc/horizons.html) at the actual exposure times and spacecraft observer location. An Earth-centered approximation can be inappropriate for a nearby object.
5. Display the blink animation, observed track, predicted positions, and the label `known asteroid recovered`.

This case does not fit a discovery orbit, claim a new asteroid, or classify a comet. New-comet searches and follow-up reporting belong to a later research phase.

## 3. Architecture and runtime

```text
React web app
  |-- Supabase Auth: identify the user
  |-- Supabase Postgres + Realtime: cases, jobs, reviews, progress
  |-- Supabase Storage: FITS inputs, output images, manifests
  |
  +-- submit-run Edge Function
         | validates user + fixed sample parameters
         +-- inserts a queued job

Python worker on the builder's laptop
  |-- atomically claims a job from Supabase
  |-- retrieves/caches archive files
  |-- validates metadata and processes FITS
  +-- writes measurements, artifacts, progress, and run events

Supabase Cron
  +-- enqueues periodic archive-health checks and recovers expired job leases

Sodabase -- read-only --> selected Supabase tables
  ^
  | authenticated MCP client in the Python worker
  +-- explicit rule results + scan verdicts --> quality snapshots --> app
```

Suggested stack: React + Vite + TypeScript; Supabase client; Python with NumPy, Astropy, reproject, SEP or Photutils, Pillow, and the MCP client SDK. Pin compatible dependency versions after the first successful run.

Run the worker locally for the hackathon. It only needs outbound connections to archives, Supabase, and Sodabase; the browser never needs to reach the laptop directly. It must remain running for new jobs to complete. A remotely hosted worker is a later deployment step.

Keep Edge Functions small: authentication, validation, enqueueing, and signed access. FITS reprojection and source extraction run in Python. Hosted Edge Functions currently have 256 MB memory and a 2-second CPU budget per request, so they are the wrong execution target for this processing workload. [Supabase limits](https://supabase.com/docs/guides/functions/limits)

Start with one concurrent image job, fixed case presets, and a cap of 50 MB of inputs per core run. Reject oversized or arbitrary archive requests. Set a measured target of under 60 seconds for cached core runs; show actual timings rather than promising an unmeasured speed.

## 4. Supabase implementation contract

### Tables

| Table | Essential fields | Purpose |
| --- | --- | --- |
| `sample_cases` | `id`, `slug`, `title`, `ra_deg`, `dec_deg`, `recipe`, `fixture_manifest_path`, `enabled` | Versioned, prepared demo selections |
| `jobs` | `id`, `owner_id`, `case_id`, `kind`, `status`, `progress`, `idempotency_key`, `attempt`, `lease_token`, `lease_expires_at`, `error`, timestamps | Durable processing lifecycle |
| `ingest_staging` | `id`, `job_id`, `source_id`, `ra_deg`, `dec_deg`, `band`, `observed_at`, `retrieved_at`, `source_url`, `checksum`, `validation_state`, `is_demo_fault`, `created_at` | Incoming metadata before scientific validation; suitable for explicit Sodabase rules |
| `observations` | `id`, `archive`, `product_id`, `band`, `ra_deg`, `dec_deg`, `observed_at`, `storage_path`, `checksum`, `wcs_summary`, `units`, `coverage_fraction`, `created_at` | Validated input metadata, deduplicated by archive/product/band |
| `job_inputs` | `job_id`, `observation_id` | Reuse inputs across runs without duplicating observations |
| `detections` | `id`, `job_id`, `observation_id`, position, measurement/error fields, `flags`, `catalog_id`, `match_separation_arcsec`, `classification`, `created_at` | Actual measured sources; optional motion-track fields for Case 3 |
| `artifacts` | `id`, `job_id`, `kind`, `storage_path`, `manifest_path`, `checksum`, `parameters`, `created_at` | Reproducible mosaics, previews, and animations |
| `reviews` | `id`, `owner_id`, `detection_id`, `label`, `note`, timestamps | User annotations |
| `pipeline_events` | `id`, `job_id`, `stage`, `status`, `rows_processed`, `duration_ms`, `created_at` | Append-only evidence of real pipeline work |
| `quality_snapshots` | `id`, `job_id`, `provider`, `dataset`, `tool`, `verdict`, `violation_count`, `findings`, `provider_checked_at`, `fetched_at`, `raw_response` | Separately attributed app checks and Sodabase responses |

Shared tables such as `observations` contain public archive metadata only. Job-associated private records derive access from the owning job. Do not use publicly accessible artifact buckets for private user outputs.

### Timestamps and constraints

- `observed_at` means when the telescope observed the sky; preserve it and its source time scale. Store MJD/time-scale metadata when provided, especially for moving objects.
- `created_at` is the current database insertion time; `retrieved_at` is when we fetched a source. Never replace scientific observation times with the current time or fabricate historical activity.
- Use `created_at` on append-only pipeline tables for pipeline freshness. Keep an `updated_at` field only where records actually change. An archival table can correctly remain unchanged for months.
- Curated coordinates must be finite, with `0 <= ra_deg < 360` and `-90 <= dec_deg <= 90`. Other required metadata is validated before promotion.
- Keep permissive staging fields for rejected inputs; protect curated tables with database constraints. Invalid demo records must stay in staging.
- A coadded survey image may span multiple observing dates. Record its observation interval or missing-date reason rather than inventing one acquisition time.

### Jobs, storage, and access

1. `submit-run` validates the user's JWT, selected preset, and parameter limits, then returns a job ID immediately. Repeated submission with the same idempotency key returns the existing job.
2. Implement a worker-only `claim_job` database function using a transactional row lock and `SKIP LOCKED`. A claim sets a lease and a unique token. Completion writes must match the current lease token so an expired worker cannot overwrite a retried job.
3. Use `queued → running → complete | failed`, with stage/progress updates. Heartbeat while processing; retry recoverable failures at most twice, then show an actionable failure.
4. Cache originals by checksum and archive product ID. Store artifacts under paths tied to the job; mark complete only after uploads and linked records exist. A retry must not duplicate measurements or outputs.
5. Enable RLS for user-facing tables and Storage. Users can read their jobs and outputs; only the worker writes trusted detections and quality snapshots. Keep worker credentials out of browser code.
6. Enable Realtime on job/progress tables and reviews. If the connection drops, poll job state every three seconds. Page reload resumes from the saved job ID.
7. Use Cron to enqueue a bounded archive-health check, for example every five minutes, and recover expired leases. Record the real response and status. A successful request that finds no new archival data is valid; do not insert fake observations to keep a freshness badge green. [Supabase Cron](https://supabase.com/docs/guides/cron)

Credentials: browser gets only the Supabase URL and publishable key; worker receives the appropriate backend credential and Sodabase token through environment variables. Store no credential values in fixtures, manifests, logs, or this plan. Follow [Storage access control](https://supabase.com/docs/guides/storage/security/access-control).

## 5. Sodabase integration: real checks, visible evidence

The current [MCP tool reference](https://sodabase.io/docs/mcp-tools), inspected in the browser on November 4, documents explicit rules and on-demand scans in addition to freshness monitoring. This supports a practical short demo without depending on historical anomaly learning.

### Connect early

1. Verify the existing team's connected Supabase project reference. If necessary, connect the intended project through the documented Supabase authorization flow.
2. Add the populated staging, observation, detection, and pipeline-event tables to the watched list. Small tables may be skipped automatically; confirm each selected table in Sodabase rather than assuming it is watched.
3. For the app's integration, use the documented remote MCP endpoint `https://sodabase.io/mcp` with Streamable HTTP. An owner/admin can create an access token under Sodabase Settings → MCP; keep it only in the worker environment. OAuth in an authenticated development client is an alternative for setup and inspection. [Connection and authentication guide](https://sodabase.io/docs/ask-your-agent)
4. Discover the live MCP tool schemas before calling them. Bind selected datasets to the intended project, particularly if the workspace contains several projects. Do not invent REST routes or assume documentation examples are complete input schemas.
5. Keep Sodabase access scoped to public astronomy metadata and pipeline tables. Its read-only role can see all rows of watched tables even when app RLS would hide them. Review the actual grant during connection. [Database access](https://sodabase.io/docs/database-access)

### Tool usage

| Documented tool | Prototype use |
| --- | --- |
| `list_datasets` | Confirm the intended project tables are accessible and watched |
| `check_rule` | Evaluate explicit coordinate/provenance rules and return violation counts; persist a rule only when supported and desired |
| `data_trust_scan` | Start an on-demand quality scan; owner/admin operation |
| `data_trust` / `data_trust_health` | Retrieve current scan verdicts and findings |
| `check_trust` | Read the latest dataset trust verdict and its evidence |
| `data_trust_sample` | Retrieve a suggested query for a finding; an operator reviews it before running it in the team's database |

On-demand scans are asynchronous. Display pending/scanning states and poll at a modest interval, such as every 10 seconds for up to two minutes. If still pending, allow later refresh. Inspect response fields and distinguish result evaluation time from the time our app fetched it.

### Astronomy rules to configure

Use clear, single-table rules first; wording is proposed application configuration, not a promise of built-in astronomy support.

- Staging: RA is present and within `[0, 360)` degrees.
- Staging: declination is present and within `[-90, 90]` degrees.
- Staging: source product identifier and original source URL are present.
- Observations: coverage fraction is between 0 and 1.
- Observations: a downloaded product has a checksum and Storage path.
- Pipeline events: duration and processed-row count are nonnegative.

Use our own validated code/SQL for WCS correctness, band consistency, duplicates, file checksum verification, matching precision, and image artifacts. Sodabase sees the stored metadata; it does not inspect FITS pixels or prove the identity of a galaxy.

Record each response in `quality_snapshots` with `provider = 'sodabase'`. Record local validation separately with `provider = 'app'`. The interface shows verdict, evidence, and timestamps. Preserve `unknown`, `scanning`, and errors; do not convert them into a healthy badge. Any hackathon score must come from the actual Sodabase interface or an explicitly documented field, not a number calculated by this app.

### Shared failure-and-recovery demo

Use this sequence on Case 2, and expose its result beside Case 1's provenance panel:

1. Process the real fixture and save its clean measurements.
2. An owner-only demo action creates a clearly labeled staging batch with one malformed record, for example `ra_deg = 420`, and `is_demo_fault = true`. It is a test copy, not a changed original observation.
3. Local validation blocks the malformed record from entering curated tables. Call Sodabase `check_rule` against the selected staging table and verify that its reported failing-row count agrees with the count for the same rule and scope in Supabase.
4. Show the affected record ID, the quality finding, and the fact that scientific processing was blocked for that batch. If a sampled scan misses the row, rely on the explicit rule result and label the scan accurately.
5. Correct the test copy from the original validated metadata, retain an audit event, rerun the same check, and show zero violations for that rule and scope. This does not automatically mean every other quality check passed.
6. Run/retry the processing job, save its output, and show the new real quality response.

This makes Sodabase visible in the product rather than only a separate dashboard tab. If token access is unavailable, demonstrate checks in an authenticated MCP client and label any imported evidence as a dated snapshot. A cached response must not appear to be a live check.

### Monitoring caveat

Automatic freshness and row-count checks may need history; `updated_at`-based freshness and new row-count checks can warm up. Do not promise a stale-data alert during a three-minute presentation or seed artificial history. Use explicit rules for the live quality demonstration. [Sodabase warm-up behavior](https://sodabase.io/docs/warm-up)

## 6. Screens and user flow

Keep the interface to three screens:

1. **Choose a case:** two enabled cards with real preview thumbnails; show the asteroid card only after its fixture passes. Each card explains the expected result in one sentence.
2. **Explore:** a large image viewer, layer/epoch controls, a progress indicator, and a source list. Show a small, expandable provenance and data-quality panel. Keep service setup details in an admin view.
3. **Saved results:** reopen a mosaic or reviewed candidate, download its image and manifest, or rerun with a new display recipe.

Every job clearly states whether it fetched archive inputs or reused verified cached inputs. A rerun on cached inputs still executes actual processing and writes a new job record.

## 7. Build order and time budget

Target a 150-minute core sprint after project access is available. These are planning estimates, not measured implementation times. Start with the data and integration gates; reduce visual polish before removing either core case's end-to-end behavior.

| Time | Work | Exit gate |
| --- | --- | --- |
| 0–20 min | Inspect the two FITS samples, verify bands/WCS/coverage, fetch a catalog subset, freeze manifests; confirm Supabase project and Sodabase access | Two usable real fixtures and working service access; no ambiguity about the target project |
| 20–45 min | Create schema/RLS/Storage, submit-and-claim job path, basic worker; connect populated tables to Sodabase and verify one explicit rule | Browser-created job completes through the worker and returns a real rule result |
| 45–75 min | Implement Case 1 mosaicking and save outputs; wire progress into the viewer | NGC 1300 runs end to end from FITS to persistent image |
| 75–105 min | Implement Case 2 source extraction, catalog match, evidence views, and saved review | A real matched detection can be inspected and annotated |
| 105–130 min | Implement fault/correct/recheck flow, quality snapshots, Cron health task, and retry handling | Malformed staging data is blocked and shown in a real Sodabase result |
| 130–150 min | Run acceptance checks, rehearse, package startup instructions and dependency locks | Both core demos survive reload and a second run |

In a team, frontend work can run alongside the worker and database/integration work. Attempt Case 3 only after both core cases pass; allocate an additional 45–90 minutes if a suitable sequence is already secured. A solo build may need longer than the sprint estimate.

Cut first if time is short: arbitrary sky search, multiple archive connectors, JWST/Hubble downloads, custom model training, free-form AI chat, cloud worker hosting, public galleries, and asteroid support. Retain two fixed real samples, persistence, actual processing, and explicit Sodabase evidence.

## 8. Implementation deliverables

```text
web/                         React interface and Supabase client
worker/                      archive adapters, FITS processing, job loop, MCP client
supabase/migrations/         tables, constraints, RLS, job functions, Cron
supabase/functions/submit-run/
fixtures/manifests/          exact input URLs, identifiers, checksums, coordinates
fixtures/catalogs/           small reference catalog subsets with attribution
scripts/                    fixture preparation and acceptance checks
README.md                   setup, environment variable names, run commands, demo script
.env.example                variable names only
```

Keep large FITS files out of Git; cache them locally or in private Supabase Storage. The fixture manifest must be sufficient to retrieve or verify each input again. Record Python/package versions, processing parameters, source attribution, and source data-use requirements.

Provide these project commands during implementation, and verify that each works from the README:

- `npm run dev` — start the web interface.
- `python -m worker` — start the single processing worker.
- `python scripts/prepare_fixtures.py` — validate and cache the real sample inputs.
- `python scripts/check_demo.py` — exercise the core acceptance checks against the chosen demo project.

These are intended entry points to implement; they do not exist yet.

## 9. Acceptance and rehearsal checklist

- [ ] Two core fixtures open as FITS, have usable coverage, and have pinned provenance.
- [ ] Case 1 recomputes a correctly aligned color mosaic with a coverage layer.
- [ ] Case 2 computes actual source measurements and identifies at least one catalog match.
- [ ] Candidate labels never imply that an unmatched source is a confirmed new discovery.
- [ ] A browser action creates a real Supabase job; the worker claims it and writes progress/results.
- [ ] Image files and metadata persist; page reload restores a saved result.
- [ ] Another test user cannot access private jobs, reviews, or Storage outputs.
- [ ] Retrying a submission does not duplicate inputs or output measurements; expired lease owners cannot finish a replaced job.
- [ ] A failed archive fetch produces a useful error or explicitly labeled cached-input processing.
- [ ] Sodabase lists the intended tables, and the app shows at least one actual rule result with evidence.
- [ ] The malformed staging record is blocked, detected, corrected, and rechecked.
- [ ] Pending, unknown, failed, and stale quality results stay distinguishable from successful checks.
- [ ] Observation dates remain unchanged, and newly created processing records use real timestamps.
- [ ] The scheduled health task runs at least twice and records real outcomes without fabricated science rows.
- [ ] Source attributions and processing recipes are included in downloads.
- [ ] Case 3 is enabled only if a real three-epoch motion sequence and known-object comparison pass.

Suggested presentation: show the mosaic, inspect a faint source, inject the labeled metadata fault, show Sodabase's finding, correct it, and reopen the saved result. Preload the real input cache and complete a real baseline scan before the presentation; leave live processing and explicit rule checks visible.

## 10. Reference links

- [Legacy Survey DR10 data and cutout services](https://www.legacysurvey.org/dr10/description/)
- [NOIRLab Legacy Surveys catalog access](https://datalab.noirlab.edu/data/legacy-surveys)
- [Legacy Survey acknowledgments and source-specific image policies](https://www.legacysurvey.org/acknowledgment/)
- [reproject mosaicking](https://reproject.readthedocs.io/en/stable/api/reproject.mosaicking.reproject_and_coadd.html)
- [Astropy RGB rendering](https://docs.astropy.org/en/stable/visualization/ref_api.html)
- [WISE moving-object selection](https://irsa.ipac.caltech.edu/applications/ICORE/docs/movingupload.html)
- [JPL Horizons API](https://ssd-api.jpl.nasa.gov/doc/horizons.html)
- [Supabase Edge Function limits](https://supabase.com/docs/guides/functions/limits)
- [Supabase Cron](https://supabase.com/docs/guides/cron)
- [Supabase Storage access control](https://supabase.com/docs/guides/storage/security/access-control)
- [Sodabase MCP authentication](https://sodabase.io/docs/ask-your-agent)
- [Sodabase MCP tools](https://sodabase.io/docs/mcp-tools)
- [Sodabase database permissions](https://sodabase.io/docs/database-access)
- [Sodabase monitoring warm-up](https://sodabase.io/docs/warm-up)

Verification note: Sodabase's pages did not load through the text search fetcher during planning; its MCP, authentication, and warm-up documentation was read directly in the browser. The archive HEAD checks establish endpoint availability only, not completed pixel inspection or a working prototype.
