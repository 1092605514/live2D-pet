"""Download KonoSuba Live2D models — uses known model names + raw GitHub URLs."""
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

LIVE2D_DIR = Path(r"D:\obsidian\code\Open-LLM-VTuber\live2d-models")
CHARACTERS_DIR = Path(r"D:\obsidian\code\Open-LLM-VTuber\characters")
MODEL_DICT_PATH = Path(r"D:\obsidian\code\Open-LLM-VTuber\model_dict.json")

RAW_BASE = "https://raw.githubusercontent.com/Eikanya/Live2d-model/master"
KONOSUBA_DIR = "为美好的世界献上祝福！Fantastic Days"

# All known KonoSuba model directory names from the repo
MODEL_NAMES = [
    "1003104", "1004100", "1004107", "1009109",
    "1013104", "1014100aqua", "1014107",
    "1023104", "1024100", "1024107", "1024113",
    "1033104", "1034100", "1034107",
    "1043104", "1044100", "1044107",
    "1053104", "1054100",
    "1063104",
    "1073104",
    "1083104",
    "1093104",
    "1103104",
    "1114100",
]

# Known file types to download for each model
FILE_TYPES = {
    ".moc3": True,
    ".model3.json": True,
    ".physics3.json": True,
    ".pose3.json": True,
    ".cdi3.json": True,
    ".userdata3.json": True,
    ".png": True,
    ".motion3.json": True,
}

# Model subdirectories to scan
MODEL_SUBDIRS = ["", "motions", "textures", "expressions", "physics"]

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
    "1073104": "惠惠 (Megumin) default",
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
        parsed = urllib.parse.urlparse(url)
        encoded = urllib.parse.quote(parsed.path, safe='/:@!$&\'()*+,;=-._~')
        safe_url = urllib.parse.urlunparse(parsed._replace(path=encoded))
        req = urllib.request.Request(safe_url, headers={"User-Agent": "Python/3.0"})
        data = urllib.request.urlopen(req, timeout=60).read()
        dest.write_bytes(data)
        return True
    except urllib.error.HTTPError as e:
        # 404 is expected for files that don't exist
        if e.code != 404:
            print(f"    HTTP {e.code} {dest.name}")
        return False
    except Exception as e:
        print(f"    FAIL {dest.name}: {e}")
        return False


def try_download(base_url, dest):
    """Try to download a file, return True if successful."""
    return download_file(base_url, dest)


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

    # Load existing model_dict
    model_dict = json.loads(MODEL_DICT_PATH.read_text(encoding="utf-8")) if MODEL_DICT_PATH.exists() else []
    existing_names = {m["name"] for m in model_dict}

    total_new = 0
    for i, model_name in enumerate(MODEL_NAMES):
        safe_name = f"konosuba_{model_name}"
        model_path = LIVE2D_DIR / safe_name

        if safe_name in existing_names and model_path.exists() and any(model_path.rglob("*.png")):
            print(f"[{i+1}/{len(MODEL_NAMES)}] {model_name} — already exists, skip")
            continue

        print(f"[{i+1}/{len(MODEL_NAMES)}] {model_name} — downloading...")
        model_path.mkdir(parents=True, exist_ok=True)

        # Build list of potential files
        dl_tasks = []

        # Root files (moc3, model3.json, etc.)
        for ext in [".moc3", ".model3.json", ".physics3.json", ".pose3.json",
                     ".cdi3.json", ".userdata3.json"]:
            filename = f"{model_name}{ext}"
            url = f"{RAW_BASE}/{KONOSUBA_DIR}/{model_name}/{filename}"
            dest = model_path / filename
            dl_tasks.append((url, dest))

        # Textures
        for tex_idx in range(10):  # Try texture_00.png through texture_09.png
            filename = f"texture_0{tex_idx}.png"
            url = f"{RAW_BASE}/{KONOSUBA_DIR}/{model_name}/textures/{filename}"
            dest = model_path / "textures" / filename
            dl_tasks.append((url, dest))

        # Motions — common KonoSuba motion names
        motion_names = [
            "00_Anger_01", "00_Anger_02", "00_Anger_03",
            "00_Appeal_01", "00_Appeal_02",
            "00_Cry_01", "00_Cry_02",
            "00_Doubt_01",
            "00_Happy_01", "00_Happy_02",
            "00_Pride_01", "00_Puzzle_01", "00_Sad_01",
            "00_Serious_01", "00_Shame_01",
            "00_Surprise_01", "00_Surprise_02",
            "00_Upset_01", "00_Wait_01",
            "20_Expression_Anger_01", "20_Expression_Appeal_01",
            "20_Expression_Appeal_02", "20_Expression_Appeal_03",
            "20_Expression_Cry_01", "20_Expression_Normal_01",
            "20_Expression_Puzzle_01", "20_Expression_Sad_01",
            "20_Expression_Serious_01", "20_Expression_Shame_01",
            "20_Expression_Shame_02", "20_Expression_Smile_01",
            "20_Expression_Smile_02", "20_Expression_Tears_01",
            "20_Expression_Tooth_01", "20_Expression_Upset_01",
            "bound", "bound_double", "bound_down",
        ]
        for mn in motion_names:
            url = f"{RAW_BASE}/{KONOSUBA_DIR}/{model_name}/motions/{mn}.motion3.json"
            dest = model_path / "motions" / f"{mn}.motion3.json"
            dl_tasks.append((url, dest))

        # Download in parallel
        downloaded = 0
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {pool.submit(try_download, url, dest): dest for url, dest in dl_tasks}
            for f in as_completed(futures):
                if f.result():
                    downloaded += 1

        print(f"    Downloaded {downloaded} files")

        # Verify model files
        has_moc3 = any(model_path.rglob("*.moc3"))
        has_model3 = any(model_path.rglob("*.model3.json"))
        has_png = any(model_path.rglob("*.png"))

        if not has_moc3 or not has_model3 or not has_png:
            print(f"    Missing required files! moc3={has_moc3} model3={has_model3} png={has_png}")
            continue

        # Fix paths in model3.json
        fix_model3_paths(model_path)

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
                total_new += 1
                existing_names.add(safe_name)
                print(f"    Registered as '{safe_name}' ({display_name})")

    # Save model_dict
    MODEL_DICT_PATH.write_text(
        json.dumps(model_dict, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nComplete! {total_new} new models registered.")
    print(f"Total models in dict: {len(model_dict)}")


if __name__ == "__main__":
    main()
