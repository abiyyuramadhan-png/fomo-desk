import os, subprocess, sys, glob, httpx, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); import api as publisher
vals = {k: os.environ.get(k) for k in ("TG_TOKEN", "GH_PAGES_TOKEN", "TYPESAFE_API_KEY", "VAPID_PRIVATE_KEY")}
vals = {k: v for k, v in vals.items() if v}
dp = publisher.data_path(); res = []
def grep(label, text, keys):
    hits = [k for k, v in keys.items() if v in text]; res.append((label, hits)); print(("PASS" if not hits else "FAIL"), label, hits or "empty")
blob = ""
for f in glob.glob(ROOT + "/**/*", recursive=True):
    if os.path.isfile(f) and "/.git/" not in f and not f.endswith(".secrets"):
        try: blob += open(f, errors="ignore").read()
        except Exception: pass
for d in glob.glob(ROOT + "/publish/*/.git"):
    blob += subprocess.run(["git", "-C", d[:-5], "log", "-p", "--all"], capture_output=True, text=True).stdout
    blob += open(d + "/config").read()
grep("token values in web/, logs/, repo, git history, .git/config", blob, vals)
main = httpx.get("https://raw.githubusercontent.com/abiyyuramadhan-png/fomo-desk/main/index.html").text
slot = int(time.time() // 15) - 2
state = httpx.get(f"https://raw.githubusercontent.com/abiyyuramadhan-png/fomo-desk/s{slot}/d/{dp}/state.json").text
grep("token values in published app + state.json", main + state, vals)
src = "".join(open(f).read() for f in glob.glob(ROOT + "/*.py") + glob.glob(ROOT + "/agents/*.py") + glob.glob(ROOT + "/web/*.*") if not f.endswith(".png"))
site = subprocess.run(["git", "-C", ROOT + "/publish/site", "log", "-p", "--all"], capture_output=True, text=True).stdout
print("PASS" if dp not in src and dp not in site else "FAIL", "DATA_PATH not in source code or app (main) branch")
r1 = httpx.get(f"https://raw.githubusercontent.com/abiyyuramadhan-png/fomo-desk/s{slot}/d/state.json")
r2 = httpx.get(f"https://raw.githubusercontent.com/abiyyuramadhan-png/fomo-desk/s{slot}/d/WRONGPATH/state.json")
print("PASS" if r1.status_code == 404 and r2.status_code == 404 else "FAIL", "path without DATA_PATH -> 404", r1.status_code, r2.status_code)
print("PASS" if ".secrets" in open(ROOT + "/.gitignore").read() and oct(os.stat(ROOT + "/.secrets").st_mode)[-3:] == "600" else "FAIL", ".secrets chmod 600 + gitignored")
