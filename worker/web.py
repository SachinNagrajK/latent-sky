import os
import threading
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route

from .backend import Backend, run_job


database = Backend()
stop_event = threading.Event()
wake_event = threading.Event()
worker_thread: threading.Thread | None = None


def consume_jobs():
    print('Hosted worker ready; polling Supabase.', flush=True)
    while not stop_event.is_set():
        try:
            jobs = database.rpc('claim_job', {})
            if jobs:
                run_job(database, jobs[0])
                continue
        except Exception as error:
            # Avoid printing responses or credentials. Render logs only need the
            # exception type to distinguish connectivity from processing errors.
            print('Worker poll failed:', type(error).__name__, flush=True)
        wake_event.wait(3)
        wake_event.clear()


@asynccontextmanager
async def lifespan(_app):
    global worker_thread
    worker_thread = threading.Thread(target=consume_jobs, daemon=True, name='latent-sky-worker')
    worker_thread.start()
    yield
    stop_event.set()
    wake_event.set()
    worker_thread.join(timeout=25)
    database.client.close()


async def health(_request):
    alive = bool(worker_thread and worker_thread.is_alive())
    return JSONResponse({'status': 'ok' if alive else 'starting'}, status_code=200 if alive else 503)


async def wake(_request):
    wake_event.set()
    return JSONResponse({'accepted': True}, status_code=202)


app = Starlette(
    routes=[Route('/health', health, methods=['GET']), Route('/wake', wake, methods=['GET'])],
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv('APP_ORIGIN', 'https://sachinnagrajk.github.io')],
    allow_methods=['GET'],
    allow_headers=['*'],
)
