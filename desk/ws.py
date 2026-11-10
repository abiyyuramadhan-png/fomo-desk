import asyncio,json,websockets,time
async def m():
  out=[]
  async with websockets.connect("wss://pumpportal.fun/api/data") as w:
    await w.send(json.dumps({"method":"subscribeMigration"}))
    t=time.time()
    while time.time()-t<600 and len([o for o in out if 'mint' in o])<2:
      try: msg=await asyncio.wait_for(w.recv(),timeout=600-(time.time()-t))
      except asyncio.TimeoutError: break
      out.append(json.loads(msg)); print(msg[:300],flush=True)
  json.dump(out,open("logs/raw/pumpportal_migration.json","w"),indent=1)
asyncio.run(m())
