"""Import GFL models from local Eikanya/Live2d-model git repo (fast version)."""
import json
import shutil
import subprocess
from pathlib import Path

# ── Paths — adjust these to your setup ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OPEN_LLM_VTUBER_ROOT = PROJECT_ROOT.parent / "Open-LLM-VTuber"
EIKANYA_REPO = PROJECT_ROOT.parent / "Eikanya_Live2d-model"

REPO = EIKANYA_REPO
LIVE2D_DIR = OPEN_LLM_VTUBER_ROOT / "live2d-models"
CHARACTERS_DIR = OPEN_LLM_VTUBER_ROOT / "characters"
MODEL_DICT_PATH = OPEN_LLM_VTUBER_ROOT / "model_dict.json"

GFL_SUBDIR = "少女前线 girls Frontline"  # 少女前线 girls Frontline


def main():
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    # Step 1: Checkout the entire GFL directory into the working tree
    print("Step 1: Checkout GFL directory from git...")
    subprocess.run(
        ['git', '-C', str(REPO), 'checkout', 'HEAD', '--', GFL_SUBDIR],
        capture_output=True, check=False)

    gfl_path = REPO / GFL_SUBDIR / "live2dnew"
    model_dirs = sorted(d for d in gfl_path.iterdir() if d.is_dir())
    print(f"Found {len(model_dirs)} GFL model directories")

    # Load existing model_dict
    model_dict = json.loads(MODEL_DICT_PATH.read_text(encoding="utf-8")) if MODEL_DICT_PATH.exists() else []
    existing_names = {m["name"] for m in model_dict}

    success = 0
    skip = 0
    new_count = 0

    for i, src_dir in enumerate(model_dirs, 1):
        safe_name = f"gfl_{src_dir.name}"
        model_path = LIVE2D_DIR / safe_name

        # Skip if already complete
        if model_path.exists() and any(model_path.rglob("*.png")):
            if safe_name in existing_names:
                skip += 1
                continue

        model_path.mkdir(parents=True, exist_ok=True)

        # Look for the normal variant
        normal_dir = src_dir / "normal"
        if normal_dir.is_dir():
            source_dir = normal_dir
        else:
            source_dir = src_dir

        # Copy all files
        file_count = 0
        for f in source_dir.rglob("*"):
            if f.is_file():
                rel = f.relative_to(source_dir)
                dest = model_path / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
                file_count += 1

        # Fix paths in model3.json
        for mf in model_path.glob("*.model3.json"):
            try:
                data = json.loads(mf.read_text(encoding="utf-8"))
                changed = False
                refs = data.get("FileReferences", {})

                textures = refs.get("Textures", [])
                for j, tex in enumerate(textures):
                    basename = Path(tex).name
                    if "/" in tex or "\\" in tex:
                        if (model_path / basename).exists():
                            textures[j] = basename
                            changed = True
                        elif (model_path / "textures" / basename).exists():
                            textures[j] = "textures/" + basename
                            changed = True

                motions = refs.get("Motions", {})
                for group, items in motions.items():
                    for item in items:
                        fname = item.get("File", "")
                        if "/" in fname:
                            basename = Path(fname).name
                            if (model_path / basename).exists():
                                item["File"] = basename
                                changed = True
                            elif (model_path / "motions" / basename).exists():
                                item["File"] = "motions/" + basename
                                changed = True

                if changed:
                    mf.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                print(f"  Error fixing {mf}: {e}")

        # Register if not already
        if safe_name not in existing_names:
            # Create character YAML
            yaml_path = CHARACTERS_DIR / f"{safe_name}.yaml"
            if not yaml_path.exists():
                display_name = src_dir.name.replace("_", " ").strip()
                yaml_path.write_text(
                    f"character_config:\n"
                    f"  conf_name: \"{display_name}\"\n"
                    f"  conf_uid: \"{safe_name}_001\"\n"
                    f"  live2d_model_name: \"{safe_name}\"\n",
                    encoding="utf-8",
                )

            # Discover motion files
            motion_files = {}
            for mf in sorted(model_path.rglob("*.motion3.json")):
                parent = mf.parent.name
                group = parent if parent != model_path.name else ""
                key = group if group else ""
                if key not in motion_files:
                    motion_files[key] = []
                relative_path = str(mf.relative_to(model_path)).replace("\\", "/")
                motion_files[key].append({"File": relative_path})

            # Find model3.json
            model3_files = list(model_path.glob("*.model3.json"))
            if model3_files:
                url = f"/live2d-models/{safe_name}/{model3_files[0].name}"
                model_dict.append({
                    "name": safe_name,
                    "description": src_dir.name.replace("_", " ").strip(),
                    "url": url,
                    "kScale": 1.0,
                    "initialXshift": 0,
                    "initialYshift": 0,
                    "kXOffset": 0,
                    "idleMotionGroupName": "Idle",
                    "emotionMap": {},
                    "tapMotions": motion_files,
                    "category": "gfl",
                    "source": "Eikanya/Live2d-model",
                })
                new_count += 1
                existing_names.add(safe_name)

        success += 1
        if i % 20 == 0 or i == len(model_dirs):
            print(f"[{i}/{len(model_dirs)}] {src_dir.name} — {file_count} files")

    # Save model_dict
    MODEL_DICT_PATH.write_text(
        json.dumps(model_dict, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nImport complete: {success} imported, {skip} skipped, {new_count} new registrations")
    print(f"Total models in dict: {len(model_dict)}")


if __name__ == "__main__":
    main()
