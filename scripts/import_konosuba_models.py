"""Import KonoSuba Live2D models using git ls-tree + raw GitHub downloads."""
import json
import os
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Paths — adjust these to your setup ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OPEN_LLM_VTUBER_ROOT = PROJECT_ROOT.parent / "Open-LLM-VTuber"
EIKANYA_REPO = PROJECT_ROOT.parent / "Eikanya_Live2d-model"

REPO = EIKANYA_REPO
LIVE2D_DIR = OPEN_LLM_VTUBER_ROOT / "live2d-models"
CHARACTERS_DIR = OPEN_LLM_VTUBER_ROOT / "characters"
MODEL_DICT_PATH = OPEN_LLM_VTUBER_ROOT / "model_dict.json"

RAW_BASE = "https://raw.githubusercontent.com/Eikanya/Live2d-model/master"
KONOSUBA_DIR = "为美好的世界献上祝福！Fantastic Days"

CHAR_NAMES = {
    "1003104": "惠惠 (Megumin) 温泉",
    "1004100": "阿克娅 (Aqua) 默认",
    "1004107": "阿克娅 (Aqua) 礼服",
    "1009109": "爱丽丝 (Iris)",
    "1013104": "惠惠 (Megumin) 新年",
    "1014100aqua": "阿克娅 (Aqua) 新年",
    "1014107": "阿克娅 (Aqua) 花嫁",
    "1023104": "惠惠 (Megumin) 夏日",
    "1024100": "阿克娅 (Aqua) 夏日",
    "1024107": "阿克娅 (Aqua) 女仆",
    "1024113": "达克尼斯 (Darkness) 女仆",
    "1033104": "惠惠 (Megumin) 旗袍",
    "1034100": "阿克娅 (Aqua) 旗袍",
    "1034107": "阿克娅 (Aqua) 泳装",
    "1043104": "惠惠 (Megumin) 万圣",
    "1044100": "阿克娅 (Aqua) 万圣",
    "1044107": "阿克娅 (Aqua) 圣诞",
    "1053104": "惠惠 (Megumin) 偶像",
    "1054100": "阿克娅 (Aqua) 偶像",
    "1063104": "惠惠 (Megumin) 制服",
    "1073104": "惠惠 (Megumin)  default",
    "1083104": "惠惠 (Megumin) 女仆",
    "1093104": "惠惠 (Megumin) 魔王",
    "1103104": "惠惠 (Megumin) 泳装2",
    "1114100": "阿克娅 (Aqua) 修女",
}


def download_file(url, dest):
    if dest.exists():
        return True
    os.makedirs(dest.parent, exist_ok=True)
    try:
        # Encode non-ASCII chars in URL path
        parsed = urllib.parse.urlparse(url)
        encoded_path = urllib.parse.quote(parsed.path, safe='/:@!$&\'()*+,;=-._~')
        safe_url = urllib.parse.urlunparse(parsed._replace(path=encoded_path))
        req = urllib.request.Request(safe_url, headers={"User-Agent": "Python/3.0"})
        data = urllib.request.urlopen(req, timeout=60).read()
        dest.write_bytes(data)
        return True
    except Exception as e:
        print(f"    FAIL {dest.name}: {e}")
        return False


def fix_model3_paths(model_path):
    for mf in model_path.glob("*.model3.json"):
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            changed = False
            refs = data.get("FileReferences", {})
            textures = refs.get("Textures", [])
            for j, tex in enumerate(textures):
                base = Path(tex).name
                if "/" in tex or "\\" in tex:
                    if (model_path / base).exists():
                        textures[j] = base; changed = True
                    elif (model_path / "textures" / base).exists():
                        textures[j] = f"textures/{base}"; changed = True
            motions = refs.get("Motions", {})
            for grp, items in motions.items():
                for item in items:
                    fname = item.get("File", "")
                    if "/" in fname:
                        base = Path(fname).name
                        if (model_path / base).exists():
                            item["File"] = base; changed = True
                        elif (model_path / "motions" / base).exists():
                            item["File"] = f"motions/{base}"; changed = True
            if changed:
                mf.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"    Fix error: {e}")


def main():
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("Step 1: Listing KonoSuba model subdirectories from git...")
    # First list the immediate children of KonoSuba directory (model names)
    result = subprocess.run(
        ['git', '-C', str(REPO), 'ls-tree', 'HEAD', '--', KONOSUBA_DIR],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        print(f"git ls-tree failed: {result.stderr}")
        return

    model_names_list = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        # line format: "mode type hash\tpath"
        meta, path = parts[0].split(" ", 2)[:2], parts[1]
        obj_type = meta[1] if len(meta) > 1 else ""
        if obj_type != "tree":
            continue
        # Extract model name (last component of path)
        model_name = path[len(KONOSUBA_DIR)+1:] if path.startswith(KONOSUBA_DIR) else path.split("/")[-1]
        model_names_list.append(model_name)

    print(f"Found {len(model_names_list)} KonoSuba model subdirectories")

    # Step 2: For each model dir, get its file list
    model_files: dict[str, list[tuple[str, str]]] = {}
    for model_name in model_names_list:
        model_path_full = f"{KONOSUBA_DIR}/{model_name}"
        result = subprocess.run(
            ['git', '-C', str(REPO), 'ls-tree', '-r', 'HEAD', '--', model_path_full],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            print(f"  Skipping {model_name}: git ls-tree failed")
            continue
        files = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue
            filepath = parts[1]
            # Get relative path within model dir
            rel = filepath[len(model_path_full)+1:]
            files.append((rel, filepath))
        model_files[model_name] = files
        print(f"  {model_name}: {len(files)} files")

    # Load existing model_dict
    model_dict = json.loads(MODEL_DICT_PATH.read_text(encoding="utf-8")) if MODEL_DICT_PATH.exists() else []
    existing_names = {m["name"] for m in model_dict}

    success = 0
    skip = 0
    new_count = 0

    for i, (model_name, files) in enumerate(sorted(model_files.items()), 1):
        safe_name = f"konosuba_{model_name}"
        model_path = LIVE2D_DIR / safe_name

        if safe_name in existing_names and model_path.exists() and any(model_path.rglob("*.png")):
            skip += 1
            continue

        print(f"[{i}/{len(model_files)}] {model_name} — {len(files)} files")
        model_path.mkdir(parents=True, exist_ok=True)

        # Download all files for this model
        dl_urls = []
        for file_rel, full_path in files:
            # Construct raw URL
            raw_url = f"{RAW_BASE}/{full_path}"
            dest = model_path / file_rel
            dl_urls.append((raw_url, dest))

        downloaded = 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(download_file, url, dest): (url, dest) for url, dest in dl_urls}
            for f in as_completed(futures):
                if f.result():
                    downloaded += 1

        if downloaded == 0:
            print(f"    No files downloaded, skip")
            continue

        # Fix paths in model3.json
        fix_model3_paths(model_path)

        # Verify model files
        if not any(model_path.rglob("*.moc3")) or not any(model_path.rglob("*.model3.json")):
            print(f"    No valid model files, skip")
            continue

        # Register if new
        if safe_name not in existing_names:
            display_name = CHAR_NAMES.get(model_name, model_name)
            yaml_path = CHARACTERS_DIR / f"{safe_name}.yaml"
            if not yaml_path.exists():
                yaml_path.write_text(
                    f"character_config:\n"
                    f"  conf_name: \"{display_name}\"\n"
                    f"  conf_uid: \"{safe_name}_001\"\n"
                    f"  live2d_model_name: \"{safe_name}\"\n",
                    encoding="utf-8",
                )

            motion_files = {}
            for mf in sorted(model_path.rglob("*.motion3.json")):
                parent = mf.parent.name
                key = parent if parent != model_path.name else ""
                if key not in motion_files:
                    motion_files[key] = []
                motion_files[key].append({"File": str(mf.relative_to(model_path)).replace("\\", "/")})

            model3_files = list(model_path.glob("*.model3.json"))
            if model3_files:
                url = f"/live2d-models/{safe_name}/{model3_files[0].name}"
                model_dict.append({
                    "name": safe_name,
                    "description": display_name,
                    "url": url,
                    "kScale": 1.0,
                    "initialXshift": 0.0,
                    "initialYshift": 0.0,
                    "kXOffset": 0.0,
                    "idleMotionGroupName": "Idle",
                    "emotionMap": {},
                    "tapMotions": motion_files,
                    "category": "konosuba",
                    "source": "Eikanya/Live2d-model",
                })
                new_count += 1
                existing_names.add(safe_name)

        success += 1

    # Save model_dict
    MODEL_DICT_PATH.write_text(
        json.dumps(model_dict, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nComplete: {success} processed, {skip} skipped, {new_count} new registrations")
    print(f"Total models in dict: {len(model_dict)}")


if __name__ == "__main__":
    main()
