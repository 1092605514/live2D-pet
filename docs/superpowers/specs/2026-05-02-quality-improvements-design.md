# live2d-pet 质量改进设计

> 2026-05-02

## 目标

修复已知 bug、补全测试覆盖、外部化配置、清理技术债。不添加新功能。

## 改动清单

### 1. Bug 修复: wink 表情幻影

`action_protocol.md` 和 `README.md` 列出 `wink` 为可用表情，但 `pet_actions.json` 只有 8 个表情（无 wink）。LLM 输出 `{"expression": "wink"}` 会静默失败。

**方案**: 从 `action_protocol.md` 和 `README.md` 移除 `wink`，保持与实际 catalog 一致。

### 2. 配置外部化: config/settings.json

当前 main.py 中硬编码的常量：

| 常量 | 当前值 | 配置键 |
|------|--------|--------|
| BACKEND_URL | `http://localhost:12393` | `backend_url` |
| PET_WIDTH / PET_HEIGHT | 280 / 420 | `window_width` / `window_height` |
| _save_timer interval | 60000 | `save_interval_ms` |
| _tick_timer interval | 15000 | `tick_interval_ms` |
| _poll_timer interval | 300 | `poll_interval_ms` |
| _cmd_cooldown_sec | 3.0 | `command_cooldown_sec` |
| _queue_timer interval | 2500 | `command_queue_interval_ms` |
| TTS voice | "冰糖" | `tts_voice` |
| _proactive_interval | 90 | `proactive_interval_sec` |

**方案**: 创建 `config/settings.json`，main.py 启动时加载，用 `.get(key, default)` 容错。

### 3. 测试补全: motion_adapter.py

测试 `MotionAdapter` 的 5 个公开方法：
- `get_motion(behavior)` → 返回正确的 motion group
- `get_expression(behavior)` → 返回正确的 expression name 或 None
- `should_play_motion(motion, now)` → 冷却检查
- `record_motion(motion, now)` → 记录时间戳
- `get_message(behavior)` → 返回 BEHAVIOR_MESSAGE

### 4. 测试补全: persistence.py

测试 `PetPersistence` 的核心路径：
- `save()` + `load()` roundtrip
- 缺失文件 → 返回默认状态
- 损坏 JSON → 备份 + 返回默认状态
- `exists()` / `delete()`
- Schema migration (version < 1)

### 5. 代码修复: BehaviorPlanner._pick() 时间源

`_pick()` 内部调用 `time.time()` 而非使用传入的 `now` 参数，导致不可测试。

**方案**: `_pick()` 接受 `now` 参数，`choose()` 传入它。

### 6. 代码修复: commands.py 白名单接入 catalog

`validate()` 默认使用硬编码 `frozenset`，应改用 catalog 驱动。

**方案**: 在 `main.py` 中调用 `validate()` 时传入 catalog 的 actions/expressions 集合。`commands.py` 的默认值保留作为 fallback。

### 7. 清理: 垃圾文件

删除根目录的 `=1.7.0` 和 `=6.6.0`（pip install 误产生的文件）。

### 8. 文档修正

根据之前 PROJECT_SUMMARY_REVIEW.md 的发现：
- 测试数量: test_state.py 30 (非 15), test_command_parser.py 36 (非 22)
- PetBehavior: 16 种 (非 15)，移除 YAWN/PLAY，补上 SLEEPY/SHOW_LOVE
- 定时器: save=60s (非 30s), tick=15s (非 3s)
- idle pool: IDLE/WALK/LOOK_AT_USER/STRETCH/SHOW_LOVE (非 YAWN/PLAY/HAPPY)

## 文件变更

| 文件 | 操作 |
|------|------|
| `config/settings.json` | 新建 |
| `main.py` | 修改: 读取配置、传入 catalog 白名单 |
| `pet_core/behavior.py` | 修改: `_pick()` 接受 `now` 参数 |
| `tests/test_motion_adapter.py` | 新建 |
| `tests/test_persistence.py` | 新建 |
| `prompts/action_protocol.md` | 修改: 移除 wink |
| `README.md` | 修改: 移除 wink |
| `PROJECT_SUMMARY.md` | 修改: 修正数据 |
| `=1.7.0`, `=6.6.0` | 删除 |

## 验证

1. `python -m pytest tests/ -v` — 全部通过（含新增测试）
2. `python -c "import py_compile; py_compile.compile('main.py', doraise=True)"` — 语法正确
3. 配置文件缺失时 main.py 使用默认值正常启动
