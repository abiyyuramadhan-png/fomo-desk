from common import *
from commands import Desk
from telegram import NullNotifier
db.x("insert into coins(mint,name,symbol,state) values('MINTAAAA','Graft Model','GRAFT','killed')")
db.x("insert into skips(ts,mint,agent,reason) values(?,?,?,?)", time.time(), "MINTAAAA", "scanner", "liq $25.6K")
d = Desk({}, NullNotifier())
for c in ["set stop to -8%", "set stop to -95%", "why GRAFT", "pause Risk", "pause Scanner", "status", "invite", "live", "LIVE", "stack 1240", "buy NOPE", "hello"]:
    r = asyncio.run(d.command(c)); print(">", c, "|", (r if isinstance(r, str) else r[0]).replace("\n", " / ")[:160])
