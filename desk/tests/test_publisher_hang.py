"""A hung git push must not stall the event loop or other agents' heartbeats."""
from common import *
import tempfile, stat, gitpush, api
tmp = tempfile.mkdtemp(); fake = os.path.join(tmp, "git")
open(fake, "w").write("#!/bin/sh\necho $$ >> %s/pids\nexec sleep 300\n" % tmp); os.chmod(fake, 0o755)
os.environ.setdefault("GH_PAGES_TOKEN", "x")
class P(api.Publisher):
    def __init__(s): s.dir = tmp; s.slots = []; s.last_ok = None; s.fails = 0
    def write(s): time.sleep(0.2)
    def cleanup_remote(s): pass
gitpush.PUSH_TIMEOUT = 3
async def main():
    os.environ["PATH"] = tmp + ":" + os.environ["PATH"]
    gaps, last = [], time.monotonic()
    async def agent():
        nonlocal last
        while True:
            await asyncio.sleep(0.25); now = time.monotonic(); gaps.append(now - last); last = now; db.heartbeat("scanner")
    t1 = asyncio.create_task(agent()); p = P(); t2 = asyncio.create_task(p.loop())
    await asyncio.sleep(10); t1.cancel(); t2.cancel()
    return gaps, p
gaps, p = asyncio.run(main())
check("heartbeats kept ticking while git hung (max gap < 1s)", max(gaps) < 1.0, round(max(gaps), 3))
check("hung push killed after timeout, counted as a skipped slot", p.fails >= 1, p.fails)
pids = [int(x) for x in open(os.path.join(tmp, "pids")).read().split()]
alive = []
for pid in pids:
    try: os.kill(pid, 0); alive.append(pid)
    except ProcessLookupError: pass
check("no git process left behind", not alive, alive)
check("scanner heartbeat fresh", time.time() - db.q1("select ts from heartbeats where agent='scanner'")["ts"] < 2)
summary("test_publisher_hang")
