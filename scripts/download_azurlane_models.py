"""Fast parallel download of Azur Lane Live2D models from GitHub raw."""
import json
import os
import urllib.request
import sys
import time
import random
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil

BASE_URL = "https://raw.githubusercontent.com/imuncle/live2d/master/live2d_3/model/Azue%20Lane(JP)"
API_URL = "https://api.github.com/repos/imuncle/live2d/contents/live2d_3/model/Azue%20Lane(JP)"
# ── Paths — adjust OPEN_LLM_VTUBER_ROOT to your setup ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OPEN_LLM_VTUBER_ROOT = PROJECT_ROOT.parent / "Open-LLM-VTuber"
LIVE2D_DIR = OPEN_LLM_VTUBER_ROOT / "live2d-models"
CHARACTERS_DIR = OPEN_LLM_VTUBER_ROOT / "characters"

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

def _make_headers():
    headers = {"User-Agent": "Python/3.0"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers

def fetch_json(url, retries=3):
    last_exc = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=_make_headers())
            return json.loads(urllib.request.urlopen(req, timeout=15).read())
        except urllib.error.HTTPError as e:
            if e.code == 403 and attempt < retries - 1:
                wait = (2 ** attempt) + random.uniform(0, 1)
                print(f"    Rate limited, retrying in {wait:.0f}s...")
                time.sleep(wait)
                continue
            raise
        except Exception as e:
            last_exc = e
            if attempt < retries - 1:
                time.sleep(1)
                continue
            raise
    raise last_exc

def download_file(url, dest):
    if dest.exists():
        return True
    os.makedirs(dest.parent, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers=_make_headers())
        data = urllib.request.urlopen(req, timeout=60).read()
        dest.write_bytes(data)
        return True
    except Exception as e:
        print(f"    FAIL {dest.name}: {e}")
        return False

def download_model(model_name):
    safe_name = model_name.replace(" ", "_").replace("(", "").replace(")", "")
    model_path = LIVE2D_DIR / safe_name
    if model_path.exists():
        return f"  {model_name} — exists, skip"

    model_path.mkdir(parents=True, exist_ok=True)
    enc_name = urllib.request.quote(model_name)

    time.sleep(0.3 + random.uniform(0, 0.2))  # be nice to GitHub API
    files = fetch_json(f"{API_URL}/{enc_name}")

    dl_tasks = []
    for f in files:
        if f["type"] == "dir":
            time.sleep(0.3 + random.uniform(0, 0.2))
            sub_files = fetch_json(f["url"])
            for sf in sub_files:
                if sf.get("download_url"):
                    dest = model_path / sf["name"]
                    dl_tasks.append((sf["download_url"], dest))
        elif f.get("download_url"):
            dest = model_path / f["name"]
            dl_tasks.append((f["download_url"], dest))

    # Download files in parallel
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(lambda args: download_file(*args), dl_tasks))

    # Create character YAML
    yaml_path = CHARACTERS_DIR / f"{safe_name}.yaml"
    if not yaml_path.exists():
        yaml_path.write_text(
            f"character_config:\n"
            f"  conf_name: \"{model_name}\"\n"
            f"  conf_uid: \"{safe_name}_001\"\n"
            f"  live2d_model_name: \"{safe_name}\"\n",
            encoding="utf-8",
        )

    return f"  {model_name} — {len(dl_tasks)} files"

def main():
    print("Fetching Azur Lane model list...")
    models = fetch_json(API_URL)
    model_dirs = [d["name"] for d in models if d["type"] == "dir"]
    print(f"Found {len(model_dirs)} models\n")

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(download_model, m): m for m in model_dirs}
        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            print(f"[{i}/{len(model_dirs)}] {result}")

    print("\nDone! Models added to live2d-models/")

if __name__ == "__main__":
    main()
