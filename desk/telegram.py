"""Telegram notifier + owner-only command desk (long polling)."""
import asyncio, json, os, time, logging, re, httpx
import db, links, config as settings
log = logging.getLogger("telegram")
HELP = ("Commands:\n buy X · sell X · why X · pause/resume Scanner|Auditor|Analyst|Executor|Risk\n"
        " set stop to -8% (any setting) · stack 1240 · status · paper | live · invite · report")
class Telegram:
    def __init__(self, token=None, chat_id=None):
        self.token = token or os.environ.get("TG_TOKEN"); self.chat = chat_id or settings.get("desk.owner_chat_id")
        self.c = httpx.AsyncClient(timeout=40); self.desk = None; self.sent = []
    def _u(self, m): return f"https://api.telegram.org/bot{self.token}/{m}"
    async def send(self, text, buttons=None):
        body = {"chat_id": self.chat, "text": text, "disable_web_page_preview": True}
        if buttons: body["reply_markup"] = {"inline_keyboard": buttons}
        for i in range(3):
            try:
                r = await self.c.post(self._u("sendMessage"), json=body)
                if r.status_code == 200 and r.json().get("ok"):
                    self.sent.append(body); return True
                log.warning("send failed %s", r.status_code)
            except Exception as e: log.warning("send error %s", type(e).__name__)
            await asyncio.sleep(1 + i)
        return False
    async def poll(self):
        off = db.kv_get("tg_offset", 0)
        while True:
            try:
                r = await self.c.get(self._u("getUpdates"), params={"offset": off, "timeout": 30}, timeout=40)
                for u in r.json().get("result", []):
                    off = u["update_id"] + 1; db.kv_set("tg_offset", off)
                    try: await self.handle(u)
                    except Exception as e: log.exception("cmd %s", e)
            except Exception as e:
                log.warning("poll error %s", type(e).__name__); await asyncio.sleep(5)
            db.heartbeat("telegram")
    async def handle(self, u):
        if "callback_query" in u:
            cq = u["callback_query"]
            if cq["from"]["id"] != self.chat: return
            await self.c.post(self._u("answerCallbackQuery"), json={"callback_query_id": cq["id"]})
            return await self.reply(await self.desk.callback(cq.get("data", "")))
        m = u.get("message") or {}
        if (m.get("chat") or {}).get("id") != self.chat: return   # owner only
        t = (m.get("text") or "").strip()
        if t.startswith("/start"): return await self.send("Desk connected. PAPER mode.\n" + HELP)
        res = await self.desk.command(t.lstrip("/"))
        await self.reply(res)
    async def reply(self, res):
        if not res: return
        if isinstance(res, str): res = (res, None)
        await self.send(*res)
class NullNotifier:
    def __init__(self): self.sent = []
    async def send(self, text, buttons=None):
        self.sent.append({"text": text, "reply_markup": {"inline_keyboard": buttons} if buttons else None}); return True
