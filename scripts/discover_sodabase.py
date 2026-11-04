import os,sys,asyncio,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from worker.backend import ROOT
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
async def main():
    token=os.environ.get('SODABASE_TOKEN')
    if not token: raise SystemExit('Set SODABASE_TOKEN in .env first.')
    async with streamablehttp_client('https://sodabase.io/mcp',headers={'Authorization':'Bearer '+token}) as (r,w,_):
        async with ClientSession(r,w) as s:
            await s.initialize()
            print(json.dumps([{'name':t.name,'inputSchema':t.inputSchema} for t in (await s.list_tools()).tools],indent=2))
asyncio.run(main())
