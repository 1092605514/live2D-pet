# 喵酱 Live2D Desktop Pet — 项目总结文档

> 生成日期: 2026-04-30
> 版本: v1.0.0

---

## 目录

1. [项目概述](#1-项目概述)
2. [系统架构](#2-系统架构)
3. [目录结构与文件说明](#3-目录结构与文件说明)
4. [核心模块详解](#4-核心模块详解)
5. [后端集成 (Open-LLM-VTuber)](#5-后端集成-open-llm-vtuber)
6. [通信协议](#6-通信协议)
7. [外部依赖](#7-外部依赖)
8. [项目进度](#8-项目进度)
9. [测试覆盖](#9-测试覆盖)
10. [代码审查](#10-代码审查)
11. [已知问题与待办](#11-已知问题与待办)

---

## 1. 项目概述

**喵酱 (MiaoJiang)** 是一个基于 Live2D 技术的桌面虚拟宠物应用。它在桌面上渲染一个 Live2D 角色，支持 LLM 驱动的对话、表情/动作控制、语音合成 (TTS)、宠物养成系统等功能。

### 核心特性

- **Live2D 渲染**: 通过 QWebEngineView 加载 Cubism SDK 渲染 26 个可切换角色模型
- **LLM 对话**: 接入 Open-LLM-VTuber 后端，支持 Ollama 本地 LLM
- **语音合成**: 集成小米 MiMo TTS API，支持预置音色、音色设计、音色复刻三种模式
- **宠物养成**: 饥饿/清洁/心情/健康/疲劳五维属性，等级/经验值系统
- **智能行为**: 优先级行为规划器，自动选择待机/进食/清洁/睡觉等行为
- **指令解析**: 从 LLM 回复中提取 JSON 指令，驱动动作和表情
- **系统托盘**: 完整的右键菜单，支持模型/音色/TTS 模型切换
- **全局热键**: Ctrl+Shift+Space/H/L 控制聊天/显隐/切换模型
- **点击穿透**: WS_EX_TRANSPARENT 实现鼠标穿透，Ctrl+拖动

### 技术栈

| 层级 | 技术 |
|------|------|
| GUI 框架 | PySide6 (Qt6) + QWebEngineView |
| 替代前端 | Electron (main.js) |
| Live2D | Cubism SDK 4 (前端 JS) |
| LLM 后端 | Open-LLM-VTuber (FastAPI + WebSocket) |
| LLM 引擎 | Ollama (qwen2.5:3b) |
| TTS | MiMo V2.5 TTS API (小米) |
| 音频播放 | winsound (Windows) |
| 域逻辑 | pet_core/ (纯 Python，零框架依赖) |

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    喵酱桌面宠物 (live2d-pet)                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  PetWindow (PySide6 QWidget)                         │   │
│  │  ┌─────────────────────────────────────────────────┐ │   │
│  │  │  QWebEngineView → 加载后端前端页面               │ │   │
│  │  │  ┌───────────────────────────────────────────┐  │ │   │
│  │  │  │  Live2D Canvas (Cubism SDK)               │  │ │   │
│  │  │  │  ┌─────────────────────────────────────┐  │  │ │   │
│  │  │  │  │  JS Bridge (注入 ~400行 JS)          │  │  │ │   │
│  │  │  │  │  - WebSocket 拦截器                  │  │  │ │   │
│  │  │  │  │  - __petPlayMotion()                 │  │  │ │   │
│  │  │  │  │  - __petSetExpressionByName()        │  │  │ │   │
│  │  │  │  │  - __petSendMessage()                │  │  │ │   │
│  │  │  │  │  - __petDrainMessages() (轮询桥)     │  │  │ │   │
│  │  │  │  └─────────────────────────────────────┘  │  │ │   │
│  │  │  └───────────────────────────────────────────┘  │ │   │
│  │  │  SpeechBubble (浮动气泡)   ChatBar (聊天输入)    │ │   │
│  │  └─────────────────────────────────────────────────┘ │   │
│  │  QSystemTrayIcon (系统托盘菜单)                       │   │
│  │  MiMoTTS (语音合成队列)                               │   │
│  │  BehaviorPlanner (行为规划器)                         │   │
│  │  PetPersistence (存档持久化)                          │   │
│  │  MotionAdapter / ExpressionCatalog / MotionCatalog   │   │
│  └──────────────────────────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────────┘
                            │ WebSocket (ws://localhost:12393/client-ws)
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              Open-LLM-VTuber 后端服务器                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ FastAPI/WS    │  │ ServiceContext│  │ 静态文件服务       │  │
│  │ websocket_    │  │ - Live2D模型  │  │ /live2d-models   │  │
│  │ handler.py    │  │ - ASR引擎     │  │ /bg              │  │
│  │               │  │ - TTS(null)   │  │ /avatars         │  │
│  │               │  │ - Agent(LLM)  │  │ / (前端)          │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│                            │                                 │
│                            ▼                                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Ollama (localhost:11434) → qwen2.5:3b               │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                 MiMo TTS API (小米)                          │
│  api.xiaomimimo.com/v1                                      │
│  模型: mimo-v2.5-tts / voicedesign / voiceclone             │
└─────────────────────────────────────────────────────────────┘
```

### 数据流

```
用户输入文字 → ChatBar → WebSocket → 后端 LLM → 生成回复
                                         │
                                         ▼
                              后端发送 audio 消息
                              (display_text + actions)
                                         │
                                         ▼
                              JS Bridge 拦截 → __petPendingMessages
                                         │
                                         ▼
                              Python 轮询 (300ms) → _on_poll_result()
                                         │
                              ┌──────────┼──────────┐
                              ▼          ▼          ▼
                        解析JSON指令  显示气泡   MiMoTTS语音
                              │
                              ▼
                        JS Bridge → Live2D 动作/表情
```

### 模型切换数据流

```
托盘菜单/快捷键 → _switch_l2d(model_id)
  → JS: __petSwitchConfig → wsInstances[0].send (前端原生 WS)
  → 后端处理 switch-config
  → 发送 set-model-and-conf + config-switched
  → React useEffect 原生加载模型 (updateModelConfig → initializeLive2D)
  → _bridgeResponse 捕获两个消息 → __petPendingMessages
  → Python 轮询:
      set-model-and-conf → 存储 model_info
      config-switched → 停止超时 → 1.5s 后 _verify_l2d_switch
  → 验证: getLAppAdapter().getModel() + canvas 状态
  → 气泡反馈: 「模型已切换: xxx」/「模型切换超时」/「模型切换可能失败」
```

---

## 3. 目录结构与文件说明

### live2d-pet/ (桌面宠物应用)

```
live2d-pet/
├── main.py                    # 主应用 (PySide6, 2189行)
├── main_optimized.py          # 优化版 (984行, 备用)
├── main.js                    # Electron 版 (替代方案)
├── launcher.py                # CLI 启动器 (347行)
├── tts.py                     # MiMo TTS 引擎 (203行)
├── preload.js                 # Electron 预加载
├── chat_preload.js            # Electron 聊天预加载
├── chat_overlay.html          # Electron 聊天界面
├── start.bat                  # Windows 启动脚本
├── start_pet.bat              # Electron 启动脚本
├── .env                       # MIMO_API_KEY
├── pyproject.toml             # Python 项目配置
├── requirements.txt           # Python 依赖
├── package.json               # Electron/Node 配置
├── config/
│   └── pet_actions.json       # Live2D 动作/表情目录配置
├── prompts/
│   └── action_protocol.md     # LLM 系统提示词 (JSON 指令协议)
├── pet_core/                  # 域逻辑层 (框架无关)
│   ├── __init__.py            # 公共 API 导出
│   ├── state.py               # 宠物状态机 (264行)
│   ├── behavior.py            # 行为规划器 (142行)
│   ├── persistence.py         # JSON 存档持久化 (91行)
│   ├── commands.py            # PetCommand 数据类 (89行)
│   ├── command_parser.py      # LLM 回复解析器 (153行)
│   ├── motion_adapter.py      # 行为→Live2D 映射 (106行)
│   ├── expression_catalog.py  # 表情名称→索引解析 (113行)
│   ├── motion_catalog.py      # 动作名称→(组,索引)解析 (129行)
│   └── tts_preprocessor.py    # TTS 文本清洗与分段 (160行)
├── tests/                     # 测试套件 (190个测试)
│   ├── test_state.py          # 状态机测试 (30个)
│   ├── test_behavior.py       # 行为规划测试 (12个)
│   ├── test_expression_catalog.py  # 表情目录测试 (12个)
│   ├── test_motion_catalog.py      # 动作目录测试 (12个)
│   ├── test_command_parser.py      # 指令解析测试 (36个)
│   ├── test_command_e2e.py         # 端到端测试 (10个)
│   ├── test_motion_adapter.py      # 动作适配器测试 (19个)
│   ├── test_persistence.py         # 持久化测试 (17个)
│   └── test_tts_preprocessor.py    # TTS 预处理测试 (42个)
└── scripts/
    ├── build-versioned.js     # Electron 构建脚本
    ├── download_azurlane_models.py  # 碧蓝航线模型下载器
    └── deploy_azurlane_models.py    # 模型部署脚本
```

### Open-LLM-VTuber/ (后端服务器)

```
Open-LLM-VTuber/
├── run_server.py              # 服务器入口
├── conf.yaml                  # 主配置文件
├── model_dict.json            # Live2D 模型注册表 (26个模型)
├── characters/                # 角色配置 YAML (26个)
│   ├── mao_pro.yaml           # 默认角色 (猫娘)
│   ├── hiyori.yaml            # 日系角色
│   ├── shizuku.yaml           # 日系角色
│   └── ...                    # 碧蓝航线角色等
├── live2d-models/             # Live2D 模型文件 (45个目录, 26个有效)
│   ├── mao_pro/runtime/mao_pro.model3.json
│   ├── hiyori/Hiyori.model3.json
│   └── ...
├── frontend/                  # 前端 React 应用 (预构建)
│   ├── index.html
│   ├── assets/main-nu7uwxNJ.js   # 打包的 JS
│   └── libs/                     # Cubism SDK, ONNX Runtime
└── src/open_llm_vtuber/       # 后端源码
    ├── server.py              # FastAPI 服务器
    ├── routes.py              # 路由定义
    ├── websocket_handler.py   # WebSocket 消息处理
    ├── service_context.py     # 服务上下文 (引擎容器)
    ├── live2d_model.py        # Live2D 模型管理
    ├── config_manager/        # Pydantic 配置验证
    │   ├── main.py            # Config 模型
    │   ├── tts.py             # TTS 配置 (含 NullTTSConfig)
    │   └── ...
    ├── tts/                   # TTS 引擎工厂
    │   ├── tts_factory.py     # 18+ TTS 后端
    │   ├── null_tts.py        # 空 TTS (桌宠用)
    │   └── ...
    ├── agent/                 # LLM Agent
    ├── asr/                   # 语音识别
    └── conversations/         # 对话管理
```

---

## 4. 核心模块详解

### 4.1 pet_core/ — 域逻辑层

这是项目的核心设计亮点：**零框架依赖的纯 Python 域逻辑**。所有状态变更都是纯函数，返回新对象，不修改原对象。

#### state.py — 宠物状态机

| 组件 | 说明 |
|------|------|
| `PetBehavior` 枚举 | 16 种行为状态: IDLE, WALK, LOOK_AT_USER, STRETCH, SICK, BEG_FOOD, DIRTY, SLEEPY, SAD, HAPPY, EAT, BATH, SLEEP, PETTED, SHOW_LOVE |
| `PetState` 数据类 | 9 个属性: hunger, cleanliness, mood, health, fatigue, affection, level, exp, coins + 时间戳 |
| `tick_pet()` | 时间衰减函数，支持 8 小时离线上限 |
| `feed()/clean()/pet_action()/sleep_action()` | 交互函数，修改属性并返回新状态 |
| `compute_health()` | 从 hunger/cleanliness/fatigue 计算健康值 |

#### behavior.py — 行为规划器

优先级层次:
1. 健康紧急 → SICK
2. 饥饿 → BEG_FOOD
3. 清洁 → DIRTY
4. 疲劳 → SLEEPY
5. 心情低 → SAD
6. 正常 → 加权随机待机池 (IDLE/WALK/LOOK_AT_USER/STRETCH/SHOW_LOVE)

特性: 可播种 RNG、不可打断行为最小持续时间、防重复逻辑。

#### command_parser.py — LLM 指令解析

解析策略 (容错设计):
1. 查找 ` ```json {...} ``` ` 围栏块 (最后一个生效)
2. 回退到裸 JSON 对象扫描 (`raw_decode`)
3. 交给 `validate()` 白名单验证

`strip_command_block()` 清理策略 (7 层):
1. 完整围栏块
2. 孤立开围栏 (```json\n{...)
3. 孤立闭围栏 (}\n```)
4. 完整/不完整 JSON 对象
5. 未闭合 JSON 对象 ({...无})
6. 裸 JSON 键值对 ("action": "wave")
7. 残留引号/花括号

#### persistence.py — 存档持久化

存储路径: `~/.miaogiang-pet/pet_save.json`
特性: 原子写入 (临时文件+重命名)、Schema 版本管理、损坏文件备份恢复。

### 4.2 main.py — GUI 层

#### 核心类

| 类 | 功能 |
|----|------|
| `PetWindow(QWidget)` | 主窗口: 无边框、透明、置顶、280x420 |
| `SpeechBubble(QFrame)` | 浮动气泡: 渐入渐出动画、多行文本 |
| `ChatBar(QFrame)` | 聊天输入: 文字输入+发送按钮 |
| `CommandLogPanel(QFrame)` | AI 指令日志面板 |

#### JS Bridge 注入

页面加载后注入 ~400 行 JavaScript:
- WebSocket 拦截器: 猴子补丁 `window.WebSocket`，捕获所有消息
- 专用宠物 WebSocket: `_petSocket` 独立连接
- 轮询桥: `__petPendingMessages` + `__petDrainMessages()`
- 动作/表情/发送接口: `__petPlayMotion()`, `__petSetExpressionByName()`, `__petSendMessage()`
- 模型切换: `__petSwitchConfig()` 优先走前端原生 WS，`_petSocket` 降级
- 消息捕获: `_bridgeResponse` 处理 `config-switched` + `set-model-and-conf`

#### 定时器

| 定时器 | 周期 | 功能 |
|--------|------|------|
| `_save_state` | 30s | 自动存档 |
| `_on_pet_tick` | 3s | 行为规划 |
| `_poll_js_messages` | 300ms | JS 消息轮询 |
| `_refresh_ollama_models` | 15min | 刷新 Ollama 模型列表 |

### 4.3 tts.py — MiMo TTS 引擎

支持三种 MiMo TTS 模型:

| 模型 | Model ID | 功能 | 音色参数 |
|------|----------|------|----------|
| 预置音色 | `mimo-v2.5-tts` | 精品音色合成 | 音色名称 (冰糖/茉莉/苏打/白桦/Mia/Chloe/Milo/Dean) |
| 音色设计 | `mimo-v2.5-tts-voicedesign` | 文本描述定制音色 | 音色描述 (温柔甜美的少女/活泼开朗的少年/...) |
| 音色复刻 | `mimo-v2.5-tts-voiceclone` | 音频样本复刻 | 音频文件路径 |

架构: 队列式顺序播放，同步 `winsound.PlaySound`，支持停止/切换/变速。

新增功能:
- `speak_segments()`: 多段顺序播放，每段独立合成，句间自然停顿
- `speed` 参数: 语速控制 (0.5-2.0，默认 1.0)

### 4.4 tts_preprocessor.py — TTS 文本预处理

LLM 输出含有 markdown、emoji、JSON 片段等，直接朗读会很生硬。此模块在 TTS 前清洗文本:

| 处理步骤 | 说明 |
|----------|------|
| JSON 清理 | 移除泄漏的 JSON 指令片段、围栏残留 |
| Markdown 清理 | 粗体/斜体/代码块/链接/图片/标题/引用 |
| Emoji 移除 | 移除 Unicode emoji (不影响 CJK 字符) |
| URL/提及移除 | 移除 http 链接和 @mentions |
| 标点规范化 | 重复标点折叠、中英文标点间距修正 |
| 分句分段 | 按句号/叹号/问号分句，按逗号/分号分从句，控制每段长度 |

`prepare_tts_text()` 组合以上步骤: 清洗 → 分段 → 添加自然结尾符。

---

## 5. 后端集成 (Open-LLM-VTuber)

### 5.1 配置系统

**主配置** `conf.yaml`:
```yaml
system_config:
  host: localhost
  port: 12393
  config_alts_dir: characters

character_config:
  conf_name: mao_pro
  live2d_model_name: mao_pro
  tts_config:
    tts_model: 'null_tts'  # 关键: 禁用后端 TTS
  agent_config:
    agent_settings:
      basic_memory_agent:
        llm_provider: 'ollama_llm'
```

**角色配置** `characters/*.yaml`: 仅覆盖 `character_config`，与主配置深度合并。

**模型注册表** `model_dict.json`: 26 个模型条目，每个包含:
- `name`, `url` (模型文件路径), `kScale`
- `emotionMap` (表情名→索引映射)
- `tapMotions` (点击动作映射)

### 5.2 null_tts 模式

这是桌宠集成的关键设计:

1. 后端 `tts_model: 'null_tts'` → `NullTTSEngine` 返回 `None`
2. 后端仍发送 `audio` 消息 (携带 `display_text` + `actions`，`audio` 字段为 null)
3. 桌宠 JS Bridge 拦截 `audio` 消息，提取文本和表情
4. 桌宠本地 MiMoTTS 负责语音合成

### 5.3 Live2D 模型切换流程

```
桌宠 → switch-config(file.yaml)
  → 后端加载 YAML → 深度合并 → validate_config()
  → Live2dModel(name) → 查找 model_dict.json
  → 发送 set-model-and-conf + config-switched
  → 桌宠收到 config-switched → _apply_l2d_switch()
  → 读取 model_dict.json → 注入 JS → updateModelConfig() + initializeLive2D()
```

### 5.4 可用模型 (26个)

| 模型名 | 说明 |
|--------|------|
| mao_pro | 猫娘 (默认) |
| shizuku | 日系少女 |
| hiyori | 日系少女 |
| natori | 日系角色 |
| haru | 日系角色 |
| lafei | 碧蓝航线 |
| aidang_2 ~ zhala_2 | 碧蓝航线系列 (20个) |

---

## 6. 通信协议

### 服务端 → 客户端

| 类型 | 载荷 | 说明 |
|------|------|------|
| `set-model-and-conf` | `{model_info, conf_name, conf_uid}` | 模型/配置信息 (客户端捕获并存储 model_info) |
| `config-switched` | `{message}` | 配置切换确认 (客户端触发 1.5s 后验证) |
| `audio` | `{audio, volumes, display_text, actions}` | 主要响应消息 |
| `full-text` | `{text}` | 完整文本 (开始/非TTS) |
| `control` | `{text}` | 控制信号 (start-mic, interrupt 等) |
| `heartbeat-ack` | `{}` | 心跳响应 |

### 客户端 → 服务端

| 类型 | 载荷 | 说明 |
|------|------|------|
| `text-input` | `{text}` | 用户文字输入 |
| `switch-config` | `{file}` | 切换角色/模型 |
| `heartbeat` | `{}` | 心跳保活 |
| `interrupt-signal` | `{text}` | 中断对话 |

---

## 7. 外部依赖

### Python

| 包 | 用途 |
|----|------|
| PySide6 >= 6.6.0 | Qt6 GUI + WebEngine |
| openai >= 1.0.0 | MiMo TTS API 客户端 |
| pynput >= 1.7.0 | 全局热键 (备选) |
| pytest | 测试框架 |
| winsound (stdlib) | Windows 音频播放 |

### Node.js (Electron 版)

| 包 | 用途 |
|----|------|
| electron ^33.0.0 | 桌面应用框架 |
| electron-builder ^25.1.8 | 打包构建 |
| ws ^8.20.0 | WebSocket 客户端 |

### 外部服务

| 服务 | 地址 | 用途 |
|------|------|------|
| Open-LLM-VTuber | localhost:12393 | LLM 后端服务器 |
| Ollama | localhost:11434 | 本地 LLM 推理 |
| MiMo TTS | api.xiaomimimo.com/v1 | 小米语音合成 |

---

## 8. 项目进度

### Roadmap 完成状态 (A-G 全部完成)

| 阶段 | 内容 | 状态 |
|------|------|------|
| A1 | 宠物核心数据模型 | ✅ |
| A2 | 行为规划器 | ✅ |
| A3 | 存档持久化 | ✅ |
| B1 | JSON 指令协议 | ✅ |
| B2 | LLM 回复解析器 | ✅ |
| B3 | 指令队列与执行 | ✅ |
| C1 | 表情目录 | ✅ |
| C2 | 动作目录 | ✅ |
| C3 | 动作适配器 | ✅ |
| D1 | 系统托盘菜单 | ✅ |
| D2 | 快捷关键词 | ✅ |
| D3 | AI 指令日志 | ✅ |
| E1 | MiMo TTS 集成 | ✅ |
| E2 | 语音队列播放 | ✅ |
| E3 | 音色设计/复刻 | ✅ |
| F1 | 全局热键 | ✅ |
| F2 | 点击穿透+拖动 | ✅ |
| F3 | Live2D 模型切换 | ✅ |
| G1 | null_tts 后端集成 | ✅ |
| G2 | 音频切片缓冲 | ✅ |
| G3 | JSON 片段清理 | ✅ |

### 后端修改

| 文件 | 修改内容 |
|------|----------|
| `config_manager/tts.py` | 添加 `NullTTSConfig` + `"null_tts"` Literal 值 |
| `service_context.py` | `init_tts()` 支持 None config; `init_live2d()` 保留异常传播 |
| `model_dict.json` | 从 2 个扩展到 26 个模型条目 |
| `conf.yaml` | `tts_model: 'null_tts'` |
| `characters/aierdeliqi_4.yaml` | 新增角色配置 |

---

## 9. 测试覆盖

### 测试概览

| 指标 | 数值 |
|------|------|
| 测试文件 | 9 |
| 测试方法 | 190 |
| 通过率 | 190/190 (100%) |
| 执行时间 | ~0.4s |

### 模块覆盖

| 模块 | 测试文件 | 测试数 | 覆盖评估 |
|------|----------|--------|----------|
| `state.py` | test_state.py | 30 | ✅ 完整 |
| `behavior.py` | test_behavior.py | 12 | ✅ 完整 |
| `commands.py` + `command_parser.py` | test_command_parser.py + test_command_e2e.py | 46 | ✅ 完整 |
| `expression_catalog.py` | test_expression_catalog.py | 12 | ✅ 完整 |
| `motion_catalog.py` | test_motion_catalog.py | 12 | ✅ 完整 |
| `motion_adapter.py` | test_motion_adapter.py | 19 | ✅ 完整 |
| `persistence.py` | test_persistence.py | 17 | ✅ 完整 |
| `tts_preprocessor.py` | test_tts_preprocessor.py | 42 | ✅ 完整 |
| `tts.py` | — | 0 | ❌ 未覆盖 (外部 API) |
| `main.py` | — | 0 | ❌ 未覆盖 (UI 层) |

**pet_core/ 估算覆盖率**: ~85-90%

### 关键测试用例

**command_parser.py** (36 个测试 — 最全面):
- 围栏 JSON 块解析 (4 个)
- 裸 JSON 对象解析 (3 个)
- 鲁棒性测试 (8 个): 空输入、None、畸形 JSON、优先级
- validate() 验证 (11 个): 白名单、规范化、类型安全
- strip_command_block() 清理 (10 个): 各种 JSON 片段模式

---

## 10. 代码审查

### 优点

1. **清晰的分层架构**: pet_core/ 零框架依赖，纯函数设计，高度可测试
2. **容错的指令解析**: 7 层清理策略，处理各种畸形 JSON 片段
3. **队列式 TTS**: 顺序播放，防重叠，防打断
4. **音频切片缓冲**: 3 秒超时收集完整响应后再处理
5. **null_tts 模式**: 优雅地禁用后端 TTS，保留文本/表情流

### 需要改进

1. ~~**motion_adapter.py 无测试**:~~ 已补充 22 个测试 (test_motion_adapter.py)
2. ~~**persistence.py 无测试**:~~ 已补充 16 个测试 (test_persistence.py)
3. ~~**BehaviorPlanner._pick() 使用 time.time()**:~~ 已修复: `_pick()` 接受 `now` 参数，`choose()` 传入
4. ~~**commands.py 白名单未更新**:~~ 已修复: `parse()` 支持 `allowed_actions`/`allowed_expressions` 参数，main.py 传入 catalog 集合
5. ~~**set-model-and-conf 仅发送到发起连接**:~~ 已重构: `__petSwitchConfig` 优先走前端原生 WS，`_bridgeResponse` 捕获 `set-model-and-conf`，添加超时+验证机制
6. ~~**TTS 语音自然度**:~~ 已优化: 新增 tts_preprocessor.py 文本清洗+分段，移除硬编码 "~喵" 后缀，支持语速控制
7. ~~**JSON 片段仍偶现**:~~ 已优化: tts_preprocessor 清理泄漏的 JSON 片段、围栏残留
8. **main.py 过大 (2189行)**: 考虑拆分 JS 注入、托盘菜单等模块

---

## 11. 已知问题与待办

### 已修复 (本次会话)

- [x] 后端启动失败: null_tts 未在 Pydantic Literal 中注册
- [x] 模型切换不生效: 重构为 `__petSwitchConfig` 优先走前端原生 WS + `_bridgeResponse` 捕获 `set-model-and-conf` + 10s 超时 + 1.5s 后验证
- [x] TTS JSON 片段: 音频切片过早刷新 (800ms→3000ms)
- [x] 音色列表错误: 使用了不存在的音色名称
- [x] 点击穿透无法拖动: Ctrl+Click 检测
- [x] 全局热键不工作: PySide6 shiboken 指针转换
- [x] 双重语音: 后端 TTS + 桌宠 TTS 同时播放
- [x] 模型切换后恢复 mao_pro: 移除 webview.reload()

### 待改进

- [ ] TTS 语音自然度: AI 味道重，需要更好的音色/模型选择
- [ ] JSON 片段仍偶现: 需要更激进的清理策略
- [ ] TTS 文本验证: 确保生成的文本是自然语言
- [ ] motion_adapter.py 测试补充
- [ ] persistence.py 测试补充
- [ ] BehaviorPlanner 使用可注入的时间源
- [ ] commands.py 白名单改用 catalog
- [ ] 项目初始化 Git 仓库
- [ ] 清理根目录的 `=1.7.0` / `=6.6.0` 文件

### 架构改进方向

1. **TTS 文本预处理管线**: 在 TTS 前增加文本清洗/校验步骤
2. **消息完成检测**: 使用完成标志位而非超时来判断响应结束
3. **后端广播机制**: switch-config 后广播到所有连接的 WebSocket
4. **模型验证**: 在切换前验证目标模型文件完整性
5. **Electron/PySide6 统一**: 合并两套实现为单一代码库

---

*本文档由 Claude Code 自动生成，基于代码审查和项目分析。*
