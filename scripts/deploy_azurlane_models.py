"""Deploy Azur Lane Live2D models from local git clone to live2d-models/."""
import os
import shutil
import urllib.request
from pathlib import Path

# ── Paths — adjust these to your setup ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OPEN_LLM_VTUBER_ROOT = PROJECT_ROOT.parent / "Open-LLM-VTuber"

# Source: local git clone of imuncle/live2d (adjust as needed)
SRC = Path("/tmp/live2d/live2d_3/model/Azue Lane(JP)")
LIVE2D_DIR = OPEN_LLM_VTUBER_ROOT / "live2d-models"
CHARACTERS_DIR = OPEN_LLM_VTUBER_ROOT / "characters"

def deploy_model(model_name):
    safe_name = model_name.replace(" ", "_").replace("(", "").replace(")", "")
    dest_dir = LIVE2D_DIR / safe_name
    src_dir = SRC / model_name

    if dest_dir.exists():
        return f"  {model_name} — exists, skip"

    if not src_dir.is_dir():
        return f"  {model_name} — source dir not found, skip"

    shutil.copytree(src_dir, dest_dir)
    print(f"  {model_name} — copied {len(list(src_dir.iterdir()))} files")

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
        print(f"    -> created {yaml_path.name}")

    return f"  {model_name} — done"

def main():
    model_dirs = sorted([d.name for d in SRC.iterdir() if d.is_dir()])
    print(f"Found {len(model_dirs)} models in local clone\n")
    for i, name in enumerate(model_dirs, 1):
        result = deploy_model(name)
        print(f"[{i}/{len(model_dirs)}] {result}")
    print("\nDone!")

if __name__ == "__main__":
    main()
