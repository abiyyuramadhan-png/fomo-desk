import sys, os, asyncio, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import httpx, links
from telegram import Telegram
async def go():
    tg = Telegram(); mint = "HQUk9fNaMUn3jPGsbBKdbmWBF2D1JCc3VaoP5GGhpump"; url = links.coin_url(mint)
    text = f"PAPER · Test push from your desk · Graft Model · this is a test, no trade\n{url}"
    body = {"chat_id": tg.chat, "text": text, "disable_web_page_preview": True, "reply_markup": {"inline_keyboard": [[{"text": "Buy on FOMO", "url": url}]]}}
    r = await tg.c.post(tg._u("sendMessage"), json=body); j = r.json()
    m = j.get("result", {})
    btn = m.get("reply_markup", {}).get("inline_keyboard", [[{}]])[0][0].get("url")
    ok = j.get("ok") and btn == url and url in m.get("text", "") and m["text"].startswith("PAPER · ") and "r=savipww" in btn
    print(("PASS" if ok else "FAIL"), "test_notify telegram", {"ok": j.get("ok"), "message_id": m.get("message_id"), "button_url": btn, "text_has_url": url in m.get("text", "")})
asyncio.run(go())
