from common import *
import re, glob, logging, links, api
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
check("CHAIN_ID exact", links.CHAIN_ID == {"solana": 1399811149, "robinhood": 4663, "base": 8453, "bnb": 56})
check("SIGNUP_URL exact", links.SIGNUP_URL == "https://fomo.family/r/savipww")
check("coin_url solana exact", links.coin_url("Abc") == "https://fomo.family/coin?address=Abc&chainId=1399811149&r=savipww&source=share_link", links.coin_url("Abc"))
for ch, cid in (("robinhood", 4663), ("base", 8453), ("bnb", 56)):
    check(f"coin_url {ch} exact", links.coin_url("Abc", ch) == f"https://fomo.family/coin?address=Abc&chainId={cid}&r=savipww&source=share_link")
class H(logging.Handler):
    def __init__(s): super().__init__(); s.n = 0
    def emit(s, r): s.n += 1
h = H(); logging.getLogger().addHandler(h)
check("unknown chain -> SIGNUP_URL and logged", links.coin_url("Abc", "ethereum") == links.SIGNUP_URL and h.n >= 1)
check("profile_url exact (strips @)", links.profile_url("@13ckngMad") == links.profile_url("13ckngMad") == "https://fomo.family/profile/13ckngMad?source=share_link&r=savipww")
SKIP = (".db", ".db-wal", ".db-shm", ".png", ".pyc", ".zip")
files = [f for f in glob.glob(ROOT + "/**/*", recursive=True) if os.path.isfile(f) and "/.git/" not in f and not f.endswith(SKIP) and not f.endswith("test_links.py")]
OLD = "fomo.family/" + "tokens"
bad = [f for f in files if OLD in open(f, errors="ignore").read()]
check("no 'fomo.family/tokens' anywhere: repo, published data, logs", not bad, bad[:5])
for t in ("activity", "kv", "events", "signals", "scans", "audits", "verdicts"):
    pass
dbt = "".join(str(dict(r)) for t in ("activity", "signals", "events", "kv") for r in db.q(f"select * from {t}"))
URL = re.compile(r"https://fomo\.family/[^\s\"'<>)\]`,}]*")
ok_url = lambda u: u == links.SIGNUP_URL or re.fullmatch(r"https://fomo\.family/coin\?address=[^&]+&chainId=\d+&r=savipww&source=share_link", u) or re.fullmatch(r"https://fomo\.family/profile/[^?]+\?source=share_link&r=savipww", u)
dp = api.data_path(); pub = ""
for f in glob.glob(os.path.join(ROOT, "publish/data/d", dp, "**/*.json"), recursive=True): pub += open(f).read()
badu = [u for u in URL.findall(pub) if not ok_url(u)]
check("every published FOMO URL is an exact links.py format", not badu and "r=savipww" in pub, badu[:3])
web = "".join(open(f).read() for f in glob.glob(ROOT + "/web/*.*"))
check("web app builds no FOMO URL itself", "fomo.family" not in web)
src = [f for f in glob.glob(ROOT + "/*.py") + glob.glob(ROOT + "/agents/*.py") if not f.endswith("links.py")]
check("only links.py writes fomo.family", not [f for f in src if "fomo.family" in open(f).read()])
summary("test_links")
