"""Git over HTTPS with the token passed as a per-process header (never in .git/config or URLs)."""
import os, base64, subprocess, asyncio, signal
REPO = "https://github.com/abiyyuramadhan-png/fomo-desk.git"
def env():
    tok = os.environ["GH_PAGES_TOKEN"]
    e = dict(os.environ)
    e.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
              "GIT_CONFIG_VALUE_0": "AUTHORIZATION: basic " + base64.b64encode(f"x-access-token:{tok}".encode()).decode(),
              "GIT_TERMINAL_PROMPT": "0", "GIT_AUTHOR_NAME": "fomo-desk", "GIT_AUTHOR_EMAIL": "desk@users.noreply.github.com",
              "GIT_COMMITTER_NAME": "fomo-desk", "GIT_COMMITTER_EMAIL": "desk@users.noreply.github.com"})
    return e
def git(cwd, *args, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, env=env(), capture_output=True, text=True, timeout=25)
    if check and r.returncode: raise RuntimeError(f"git {args[0]} failed: {r.stderr.strip()[-300:]}")
    return r.stdout
def init(dirpath, branch):
    os.makedirs(dirpath, exist_ok=True)
    if not os.path.isdir(os.path.join(dirpath, ".git")):
        git(dirpath, "init", "-q", "-b", branch)
        git(dirpath, "remote", "add", "origin", REPO)

PUSH_TIMEOUT = 25
async def agit(cwd, *args, check=True, timeout=None):
    """Async git for the event loop: never blocks other agents. On timeout the whole process group is killed."""
    p = await asyncio.create_subprocess_exec("git", *args, cwd=cwd, env=env(), stdout=asyncio.subprocess.PIPE,
                                             stderr=asyncio.subprocess.PIPE, start_new_session=True)
    try: out, err = await asyncio.wait_for(p.communicate(), timeout or PUSH_TIMEOUT)
    except BaseException as e:
        try: os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        await asyncio.shield(p.wait())
        if not isinstance(e, asyncio.TimeoutError): raise
        raise RuntimeError(f"git {args[0]} killed after {timeout or PUSH_TIMEOUT}s")
    if check and p.returncode: raise RuntimeError(f"git {args[0]} failed: {err.decode(errors='ignore').strip()[-300:]}")
    return out.decode(errors="ignore")
