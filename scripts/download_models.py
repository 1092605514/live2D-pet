"""Download Live2D models from multiple GitHub repos with category support."""
import json
import os
import sys
import io
import urllib.request
import time
import random
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Paths ─────────────────────────────────────────────────
# These resolve relative to the Open-LLM-VTuber project expected
# to be a sibling of this project's root.
# Adjust OPEN_LLM_VTUBER_ROOT to match your setup.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OPEN_LLM_VTUBER_ROOT = PROJECT_ROOT.parent / "Open-LLM-VTuber"

LIVE2D_DIR = OPEN_LLM_VTUBER_ROOT / "live2d-models"
CHARACTERS_DIR = OPEN_LLM_VTUBER_ROOT / "characters"
MODEL_DICT_PATH = OPEN_LLM_VTUBER_ROOT / "model_dict.json"

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

# ── Source registry ─────────────────────────────────────────
SOURCES = [
    {
        "name": "imuncle/live2d",
        "api_url": "https://api.github.com/repos/imuncle/live2d/contents/"
                   + urllib.request.quote("live2d_3/model/Azue Lane(JP)"),
        "category": "azurlane",
        "label": "碧蓝航线 (Azur Lane)",
        "safe_name": "_azurlane",
    },
    {
        "name": "Eikanya/Live2d-model",
        "api_url": "https://api.github.com/repos/Eikanya/Live2d-model/contents/"
                   + urllib.request.quote("少女前线 girls Frontline"),
        "category": "gfl",
        "label": "少女前线 (Girls Frontline)",
        "safe_name": "_gfl",
    },
    {
        "name": "Eikanya/Live2d-model",
        "api_url": "https://api.github.com/repos/Eikanya/Live2d-model/contents/"
                   + urllib.request.quote("崩坏学园2"),
        "category": "honkai",
        "label": "崩坏学园2",
        "safe_name": "_honkai2",
    },
    {
        "name": "Eikanya/Live2d-model",
        "api_url": "https://api.github.com/repos/Eikanya/Live2d-model/contents/"
                   + urllib.request.quote("战舰少女"),
        "category": "warship",
        "label": "战舰少女",
        "safe_name": "_warship",
    },
]

CATEGORIES = {
    "official": {"label": "📦 官方示例", "priority": 1},
    "azurlane": {"label": "🎮 碧蓝航线", "priority": 2},
    "gfl": {"label": "🔫 少女前线", "priority": 3},
    "honkai": {"label": "🏫 崩坏学园2", "priority": 4},
    "warship": {"label": "🚢 战舰少女", "priority": 5},
    "other": {"label": "📁 其他", "priority": 99},
}


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
            return json.loads(urllib.request.urlopen(req, timeout=20).read())
        except urllib.error.HTTPError as e:
            if e.code == 403 and attempt < retries - 1:
                wait = (2 ** attempt) + random.uniform(0, 1)
                print(f"    Rate limited, waiting {wait:.0f}s...")
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


def collect_files_recursive(api_url, model_path):
    """Recursively collect all files from a GitHub API directory, preserving subdirs."""
    files = fetch_json(api_url)
    dl_tasks = []

    for f in files:
        if f["type"] == "dir":
            # Recurse into subdirectory
            sub_path = model_path / f["name"]
            sub_tasks = collect_files_recursive(f["url"], sub_path)
            dl_tasks.extend(sub_tasks)
        elif f.get("download_url"):
            dest = model_path / f["name"]
            dl_tasks.append((f["download_url"], dest))

    return dl_tasks


def fix_model3_paths(model_path):
    """Fix common path issues in .model3.json files."""
    for mf in model_path.glob("*.model3.json"):
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            changed = False
            refs = data.get("FileReferences", {})

            # Fix texture paths: textures/xxx.png -> texture_00.png style
            textures = refs.get("Textures", [])
            for i, tex in enumerate(textures):
                basename = os.path.basename(tex)
                if basename in tex and basename != tex:
                    actual = model_path / basename
                    if actual.exists():
                        textures[i] = basename
                        changed = True

            # Fix motion paths: motions/xxx.motion3.json -> xxx.motion3.json
            motions = refs.get("Motions", {})
            for group, items in motions.items():
                for item in items:
                    fname = item.get("File", "")
                    if fname.startswith("motions/") or "/" in fname:
                        basename = os.path.basename(fname)
                        # Check if file exists at root or in motions/
                        if (model_path / basename).exists():
                            item["File"] = basename
                            changed = True
                        elif (model_path / "motions" / basename).exists():
                            item["File"] = "motions/" + basename
                            changed = True

            if changed:
                mf.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"    Fixed paths in {mf.name}")
        except Exception as e:
            print(f"    Error fixing {mf}: {e}")


def register_model(model_name, category, source, model_path):
    """Register a downloaded model in model_dict.json and create character YAML."""
    # Create character YAML
    safe_name = model_name.replace(" ", "_").replace("(", "").replace(")", "")
    yaml_path = CHARACTERS_DIR / f"{safe_name}.yaml"
    if not yaml_path.exists():
        display_name = model_name.replace("_", " ").strip()
        yaml_path.write_text(
            f"character_config:\n"
            f"  conf_name: \"{display_name}\"\n"
            f"  conf_uid: \"{safe_name}_001\"\n"
            f"  live2d_model_name: \"{safe_name}\"\n",
            encoding="utf-8",
        )
        print(f"    Created {safe_name}.yaml")

    # Auto-discover motion files in the model directory
    motion_files = {}
    for mf in sorted(model_path.rglob("*.motion3.json")):
        # Determine group from parent dir or file prefix
        parent = mf.parent.name
        group = parent if parent != model_path.name else ""
        key = group if group else ""
        if key not in motion_files:
            motion_files[key] = []
        relative_path = str(mf.relative_to(model_path)).replace("\\", "/")
        motion_files[key].append({"File": relative_path})

    # Find model3.json URL
    model3_files = list(model_path.glob("*.model3.json"))
    if not model3_files:
        print(f"    WARNING: No .model3.json found in {model_path}")
        return
    url = f"/live2d-models/{safe_name}/{model3_files[0].name}"

    # Update model_dict.json
    model_dict = []
    if MODEL_DICT_PATH.exists():
        model_dict = json.loads(MODEL_DICT_PATH.read_text(encoding="utf-8"))

    # Check if already registered
    existing = [m for m in model_dict if m.get("name") == safe_name]
    if existing:
        # Update existing entry
        existing[0]["category"] = category
        existing[0]["source"] = source
        existing[0]["url"] = url
        existing[0]["tapMotions"] = motion_files
        existing[0].setdefault("description",
            model_name.replace("_", " ").title())
    else:
        model_dict.append({
            "name": safe_name,
            "description": model_name.replace("_", " ").title(),
            "url": url,
            "kScale": 1.0,
            "initialXshift": 0,
            "initialYshift": 0,
            "kXOffset": 0,
            "idleMotionGroupName": "Idle",
            "emotionMap": {},
            "tapMotions": motion_files,
            "category": category,
            "source": source,
        })

    MODEL_DICT_PATH.write_text(
        json.dumps(model_dict, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"    Registered in model_dict.json")


def download_model(source_info, model_name, force=False):
    """Download a single Live2D model from a GitHub source."""
    safe_name = model_name.replace(" ", "_").replace("(", "").replace(")", "")
    model_path = LIVE2D_DIR / safe_name

    # Skip if already complete (has textures)
    if not force and model_path.exists():
        if any(model_path.rglob("*.png")):
            return (True, f"  {model_name} [{source_info['label']}] — exists, skip")

    model_path.mkdir(parents=True, exist_ok=True)

    enc_name = urllib.request.quote(model_name)
    api_url = source_info["api_url"]

    # Collect files
    try:
        dl_tasks = collect_files_recursive(f"{api_url}/{enc_name}", model_path)
    except Exception as e:
        return (False, f"  {model_name} — API error: {e}")

    if not dl_tasks:
        return (False, f"  {model_name} — no files found")

    # Download all files in parallel
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda args: download_file(*args), dl_tasks))

    # Fix model3.json paths
    fix_model3_paths(model_path)

    # Register the model
    register_model(model_name, source_info["category"], source_info["name"],
                   model_path)

    return (True, f"  {model_name} [{source_info['label']}] — {len(dl_tasks)} files")


def download_from_source(source_info, force=False):
    """Download all models from a GitHub source directory."""
    print(f"\n{'=' * 60}")
    print(f"Source: {source_info['label']}")
    print(f"Repo: {source_info['name']}")
    print(f"Category: {source_info['category']}")
    print(f"{'=' * 60}")

    try:
        files = fetch_json(source_info["api_url"])
    except Exception as e:
        print(f"  Failed to fetch model list: {e}")
        return

    model_dirs = [f["name"] for f in files if f["type"] == "dir"]
    print(f"Found {len(model_dirs)} models")

    success = 0
    fail = 0
    skip = 0

    for i, model_name in enumerate(model_dirs, 1):
        time.sleep(0.3 + random.uniform(0, 0.3))
        ok, msg = download_model(source_info, model_name, force=force)
        print(f"[{i}/{len(model_dirs)}] {msg}")
        if ok:
            success += 1
        else:
            fail += 1

    print(f"Done: {success} success, {fail} fail")


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("Live2D Model Downloader")
    print("=" * 60)

    import argparse
    parser = argparse.ArgumentParser(description="Download Live2D models")
    parser.add_argument("--force", action="store_true",
                        help="Re-download existing models")
    parser.add_argument("--source", type=str, default=None,
                        help="Download from specific source index (0-based)")
    args = parser.parse_args()

    sources = SOURCES
    if args.source is not None:
        idx = int(args.source)
        if 0 <= idx < len(SOURCES):
            sources = [SOURCES[idx]]
        else:
            print(f"Invalid source index: {idx}")
            return

    for src in sources:
        download_from_source(src, force=args.force)

    print("\n" + "=" * 60)
    print("All downloads complete!")

    # Final summary
    model_dict = json.loads(MODEL_DICT_PATH.read_text(encoding="utf-8"))
    cats = {}
    for m in model_dict:
        cat = m.get("category", "other")
        cats[cat] = cats.get(cat, 0) + 1
    print("\nModel inventory by category:")
    for cat, label_info in sorted(CATEGORIES.items()):
        count = cats.get(cat, 0)
        if count > 0:
            print(f"  {label_info['label']}: {count} models")
    print(f"  Total: {len(model_dict)} models")


if __name__ == "__main__":
    main()
