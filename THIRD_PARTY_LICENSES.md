# Third-Party Licenses & Attribution

This project (喵酱 Live2D Desktop Pet) is built on top of many open-source libraries,
frameworks, and third-party assets. This document lists every dependency and its license.

The project itself is licensed under the **MIT License** (see `LICENSE`), but each
third-party component is governed by its own license.

---

## 📦 Python Packages

| Package | Version | Purpose | License | Source |
|---------|---------|---------|---------|--------|
| **PySide6** | >= 6.6.0 | Qt6 GUI framework + WebEngine for Live2D rendering | **LGPL-3.0** / **GPL-3.0** | https://pypi.org/project/PySide6/ |
| **pynput** | >= 1.7.0 | Global hotkey monitoring (fallback) | **LGPL-3.0** | https://github.com/moses-palmer/pynput |
| **openai** | >= 1.0.0 | HTTP client for MiMo TTS API | **MIT** | https://pypi.org/project/openai/ |
| **keyboard** | >= 0.13.0 | Global hotkey registration (fallback) | **MIT** | https://github.com/boppreh/keyboard |
| **pytest** | *latest* | Test framework | **MIT** | https://github.com/pytest-dev/pytest |

**Artwork used by Qt/WebEngine:**
Qt (via PySide6) includes the Qt WebEngine module, which is distributed under LGPL-3.0.
Qt WebEngine is based on Chromium, which is governed by BSD-style licenses.

---

## 📦 Node.js Packages

| Package | Version | Purpose | License | Source |
|---------|---------|---------|---------|--------|
| **electron** | ^33.0.0 | Desktop application shell (alternative frontend) | **MIT** | https://github.com/electron/electron |
| **electron-builder** | ^25.1.8 | Build and packaging for Windows | **MIT** | https://github.com/electron-userland/electron-builder |
| **ws** | ^8.20.0 | WebSocket client for LLM backend communication | **MIT** | https://github.com/websockets/ws |

---

## 🌐 External Services / APIs

| Service | URL | Purpose | Terms |
|---------|-----|---------|-------|
| **Ollama** | https://ollama.ai | Local LLM inference engine (qwen2.5) | Apache 2.0 — https://github.com/ollama/ollama |
| **MiMo TTS API** | https://api.xiaomimimo.com/v1 | Cloud TTS voice synthesis | Proprietary — governed by 小米 company terms |
| **Open-LLM-VTuber** | https://github.com/Open-LLM-VTuber/Open-LLM-VTuber | LLM backend server (WebSocket + FastAPI) | **Apache 2.0** — see below |

### Open-LLM-VTuber

This project integrates with [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber)
as a backend dependency. That project is licensed under the **Apache License 2.0**.

> ⚠️ This repository does NOT include the full `Open-LLM-VTuber/` source code.
> Users must clone it separately:
> ```
> git clone https://github.com/Open-LLM-VTuber/Open-LLM-VTuber.git
> ```
> See `README.md` for setup instructions.

---

## 🎨 Live2D — Cubism SDK (Proprietary)

Live2D rendering uses **Live2D Cubism SDK 4** (or later), a proprietary SDK by
Live2D Inc. It is loaded at runtime by the Open-LLM-VTuber frontend.

| Component | License | Source |
|-----------|---------|--------|
| Live2D Cubism Core | Proprietary — requires license from Live2D Inc. | https://www.live2d.com/sdk/about/ |
| Live2D Cubism Framework | Proprietary (free for development) | https://github.com/Live2D/CubismWebFramework |

> **Important:** The Cubism SDK is NOT included in this repository. Users must
> obtain it from Live2D's official site and follow their licensing terms.
> For individual developers, Live2D offers a free software license agreement.

---

## 🧸 Live2D Model Assets

The Live2D models used by this project come from third-party sources. They are
**NOT** covered by the MIT license of this project.

### Default Model: `mao_pro`

The default cat-girl model (`mao_pro`) is bundled with Open-LLM-VTuber.
Its origin and license should be verified with the Open-LLM-VTuber project.

### Models from GitHub Community Repositories

| Source Repo | Models Included | Notes |
|-------------|----------------|-------|
| [imuncle/live2d](https://github.com/imuncle/live2d) | Azur Lane (碧蓝航线) series (~20 models) | Fan-collected models. Original copyright holders: Manjuu / Yongshi / bilibili. **License status unclear** — these are community-hosted model files. |
| [Eikanya/Live2d-model](https://github.com/Eikanya/Live2d-model) | Girls' Frontline (少女前线), Honkai Impact 3 (崩坏学园2), Warship Girls (战舰少女), KonoSuba (为美好的世界献上祝福！) | Fan-collected models from various games/anime. **License status unclear** — original copyright holders are various game studios. |

> ⚠️ **Copyright Notice on Models:**
> - The Live2D models of Azur Lane characters are copyrighted by **Manjuu Co., Ltd. / Yongshi Co., Ltd.**
> - The Live2D models of Girls' Frontline characters are copyrighted by **Sunglide / Digital Chess / MICA Team**
> - The Live2D models of KonoSuba characters are copyrighted by **Kadokawa Corporation / Studio Deen**
> - All other models belong to their respective copyright holders
>
> These models are fan-collected and their redistribution rights are unclear.
> **Use at your own risk.** If you are a copyright holder and want a model removed,
> please open an issue on the GitHub repository.

### Scripts for Model Download

The following Python scripts download models from the above sources and are
included in this repository (`scripts/` directory):

| Script | Source |
|--------|--------|
| `scripts/download_models.py` | Aggregated downloader from imuncle/live2d + Eikanya/Live2d-model |
| `scripts/download_azurlane_models.py` | Dedicated Azur Lane model downloader |
| `scripts/deploy_azurlane_models.py` | Deploy Azur Lane models from local git clone |
| `scripts/import_konosuba_models.py` | Import KonoSuba models from Eikanya/Live2d-model |
| `scripts/import_gfl_models.py` | Import Girls' Frontline models from Eikanya/Live2d-model |
| `scripts/build-versioned.js` | Electron build versioning utility |

---

## 🔧 Other Tools & Runtimes

| Component | Purpose | License | Source |
|-----------|---------|---------|--------|
| **Python 3.10+** | Runtime for the main application | **PSF License** | https://www.python.org/ |
| **Node.js** | Runtime for Electron frontend | **MIT** | https://nodejs.org/ |
| **npm** | Package manager for Node.js dependencies | **Artistic License 2.0** | https://www.npmjs.com/ |
| **uv** | Python package manager (recommended) | **Apache 2.0 / MIT** | https://github.com/astral-sh/uv |

---

## ✅ Compliance Checklist

- [x] MIT license for original project code
- [x] Full dependency table with versions and license types
- [x] Source URLs for every dependency
- [x] Separate attribution for model assets with copyright holders noted
- [x] Disclaimer for fan-collected model assets with unclear licensing
- [x] Note that Live2D Cubism SDK is proprietary and not included
- [x] Note that Open-LLM-VTuber is a separate project under Apache 2.0

---

*Last updated: 2025*
