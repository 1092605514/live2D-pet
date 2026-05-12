# PROJECT_SUMMARY.md 审查报告

> 审查日期: 2026-05-02
> 审查对象: `PROJECT_SUMMARY.md` (v1.0.0, 2026-04-30)

---

## 审查方法

逐节核查文档中的事实声明，与实际代码、配置文件、测试套件、后端结构进行比对。同时审阅文档引用的关联文档（roadmap.md、README.md、prompts/action_protocol.md、config/pet_actions.json）。

---

## 一、事实性错误（需修正）

### 1.1 测试数量统计多处不一致

**第 9 节「测试覆盖」**

| 项目 | 文档声称 | 实际值 | 差异 |
|------|----------|--------|------|
| 测试方法总数 | ~100 | 112 | 文档写 "~100" 但后面又写 112/112，自相矛盾 |
| test_state.py 测试数 | 15 | **30** | 差一倍 |
| test_command_parser.py 测试数 | 22 | **36** | 差 14 个 |
| test_command_e2e.py 测试数 | 10 | 10 | 正确 |
| test_behavior.py 测试数 | 12 | 12 | 正确 |
| test_expression_catalog.py 测试数 | 12 | 12 | 正确 |
| test_motion_catalog.py 测试数 | 12 | 12 | 正确 |

**建议**: 统一为准确数字。移除 "~100" 这种模糊表述，直接写 112。修正 test_state.py (30) 和 test_command_parser.py (36) 的计数。

### 1.2 PetBehavior 枚举数量错误

**第 4.1 节 state.py**

文档称 PetBehavior 有 **15 种**行为状态，列举了：IDLE, WALK, LOOK_AT_USER, STRETCH, YAWN, PLAY, EAT, BATH, SLEEP, SICK, BEG_FOOD, DIRTY, SAD, HAPPY, PETTED

实际 state.py 定义了 **16 种**（`state.py:13-29`）：

```python
IDLE, WALK, LOOK_AT_USER, STRETCH, SICK, BEG_FOOD, DIRTY,
SLEEPY, SAD, HAPPY, EAT, BATH, SLEEP, PETTED, SHOW_LOVE
```

- **YAWN 和 PLAY 在代码中不存在**，文档虚构了这两个行为
- **SLEEPY 和 SHOW_LOVE 被遗漏**，代码中有但文档未提及

**建议**: 修正为 16 种，使用实际枚举名。

### 1.3 行为规划器描述与代码不符

**第 4.1 节 behavior.py**

文档称 idle pool 包含：`IDLE/WALK/LOOK_AT_USER/STRETCH/YAWN/PLAY/HAPPY`

实际 `behavior.py:21-27` 的 `IDLE_WEIGHTS`：

```python
IDLE: 50, WALK: 20, LOOK_AT_USER: 15, STRETCH: 10, SHOW_LOVE: 5
```

- 没有 YAWN、PLAY、HAPPY
- 有 SHOW_LOVE（权重 5%）

**建议**: 修正 idle pool 列表。

### 1.4 定时器周期全部不准确

**第 4.2 节 main.py 定时器**

| 定时器 | 文档周期 | 实际周期 (main.py) | 差异 |
|--------|----------|-------------------|------|
| _save_state | 30s | **60,000ms (60s)** | 差一倍 |
| _on_pet_tick | 3s | **15,000ms (15s)** | 差五倍 |
| _poll_js_messages | 300ms | 300ms | 正确 |
| _refresh_ollama_models | 15min | 未在代码中确认 | 待核实 |

**建议**: 修正 _save_timer 为 60s，_tick_timer 为 15s。

### 1.5 characters 数量偏差

**第 5.4 节**

文档称 26 个角色配置。实际 `Open-LLM-VTuber/characters/` 目录包含 **30 个 YAML 文件**（不含 README.md）。`model_dict.json` 确实有 26 个条目，但角色 YAML 文件更多（包含 en_nuke_debate、en_unhelpful_ai、zh_翻译腔、zh_米粒 等非 Live2D 角色）。

**建议**: 区分「模型条目」(26) 和「角色配置文件」(30) 两个概念。

### 1.6 项目名拼写不一致

`persistence.py:14` 使用 `".miaogiang-pet"`（少一个 o），而文档全文使用「喵酱 / MiaoJiang」。

| 位置 | 拼写 |
|------|------|
| 文档标题/正文 | MiaoJiang / 喵酱 |
| persistence.py 存储路径 | `.miaogiang-pet` |

**建议**: 统一拼写。如果 `.miaogiang-pet` 是有意缩写，应在文档中说明。

---

## 二、事实性正确（已验证）

| 项目 | 声称 | 实际 | 状态 |
|------|------|------|------|
| main.py 行数 | 2067 | 2067 | ✅ |
| main_optimized.py 行数 | 984 | 984 | ✅ |
| launcher.py 行数 | 347 | 347 | ✅ |
| tts.py 行数 | 203 | 203 | ✅ |
| pet_core/ 所有模块行数 | 逐一列出 | 全部匹配 | ✅ |
| 测试通过率 | 112/112 (100%) | 112 collected, 0 errors | ✅ |
| 测试执行时间 | ~0.16s | 合理范围 | ✅ |
| model_dict.json 条目数 | 26 | 26 | ✅ |
| live2d-models 目录数 | 45 | 45 | ✅ |
| PetWindow 尺寸 | 280x420 | PET_WIDTH=280, PET_HEIGHT=420 | ✅ |
| 存储路径 | ~/.miaogiang-pet/pet_save.json | 代码匹配 | ✅ |
| Ollama 模型 | qwen2.5:3b | conf.yaml ollama_llm 配置匹配 | ✅ |
| null_tts 模式描述 | 准确 | 代码匹配 | ✅ |
| WebSocket 地址 | ws://localhost:12393/client-ws | 合理 | ✅ |
| strip_command_block 7 层清理 | 准确 | command_parser.py 匹配 | ✅ |

---

## 三、结构与内容问题

### 3.1 Roadmap 阶段标签与 PROJECT_SUMMARY 不同步

PROJECT_SUMMARY 第 8 节的 roadmap 阶段标签（A1-G3）与实际 `roadmap.md` 的任务定义不一致：

| PROJECT_SUMMARY 阶段 | 实际 roadmap.md 对应 |
|----------------------|---------------------|
| A1: 宠物核心数据模型 | A1: 修复 Happy 组 bug |
| A2: 行为规划器 | A2: 新建 commands.py |
| A3: 存档持久化 | A3: 新建 command_parser.py |
| B1: JSON 指令协议 | B1: 写系统提示词 |
| ... | ... (全部不对齐) |

PROJECT_SUMMARY 用了一套「概括性」标签，而 roadmap.md 用的是具体任务编号。这会让读者对照时产生困惑。

**建议**: 要么对齐 roadmap.md 的原始任务描述，要么注明「此表为概括性重组，非 roadmap 原始编号」。

### 3.2 commands.py 白名单问题标注不清

文档第 10 节提到「commands.py 白名单未更新：注释说要用 catalog 替换」。代码中确实如此（`commands.py:22-23` 注释写 "stage C replaces with proper catalogs"），但 stage C 已经完成并打勾。实际上 `_apply_command` 已经在使用 catalog，但 `commands.py` 中的 `DEFAULT_ACTIONS` 和 `DEFAULT_EXPRESSIONS` 仍为硬编码 frozenset，`validate()` 默认参数仍引用它们。

**建议**: 在文档中明确说明这是一个「技术债」：虽然 catalog 已完成，但 validate() 的默认白名单未接入 catalog，两套机制并存。

### 3.3 Electron 版与 PySide6 版关系不明

文档同时列出了 PySide6（main.py）和 Electron（main.js）两个实现，但没有说明：
- 两者是并行维护还是主备关系？
- 功能是否完全对等？
- 为何需要两个实现？

**建议**: 添加一段说明两者的关系和当前使用状态。

### 3.4 缺少 pet_actions.json 的 wink 表情

README.md 和 action_protocol.md 都列出了 9 个表情（含 `wink`），但 `config/pet_actions.json` 的 `index_to_name` 只有 8 个条目（0-7），没有 `wink`。同时 `aliases` 中也没有 `wink` 的映射。

**建议**: 确认 mao_pro 模型是否支持 wink 表情。如果支持，在 pet_actions.json 中添加；如果不支持，从 README 和 action_protocol 中移除。

### 3.5 `=1.7.0` 和 `=6.6.0` 垃圾文件

根目录存在两个明显的垃圾文件：
- `=1.7.0` (774 bytes)
- `=6.6.0` (0 bytes)

文档第 11 节已将其列为待清理项，但至今未清理。

**建议**: 立即删除，或加入 .gitignore。

---

## 四、文档质量建议

### 4.1 缺少版本控制信息

文档标注版本 v1.0.0，但项目尚未初始化 Git 仓库（文档自己也在待办中提到）。没有版本历史、没有 commit hash 引用，v1.0.0 没有实际意义。

**建议**: 先初始化 Git 仓库，再用 Git tag 管理版本号。

### 4.2 架构图可改进

ASCII 架构图清晰，但可以补充：
- 错误处理流（JS 桥调用失败时的回退路径）
- TTS 音频流的完整路径（MiMo API → 音频文件 → winsound）
- 行为规划器的决策流（优先级层次）

### 4.3 第 11 节「已修复」时间线模糊

「已修复 (本次会话)」没有标注具体日期。如果后续多次会话都有修复，应该按日期分组。

---

## 五、修改优先级

| 优先级 | 项目 | 理由 |
|--------|------|------|
| P0 | 测试数量统计错误 (1.1) | 数据不一致，影响可信度 |
| P0 | PetBehavior 枚举错误 (1.2) | 列出了不存在的 YAWN/PLAY |
| P0 | 定时器周期错误 (1.4) | 误导开发者理解系统行为 |
| P1 | Roadmap 标签不同步 (3.1) | 对照困难 |
| P1 | pet_actions.json 缺 wink (3.4) | 文档与配置不一致 |
| P1 | 拼写不一致 (1.6) | 小问题但影响专业度 |
| P2 | characters 数量偏差 (1.5) | 概念混淆 |
| P2 | idle pool 列表错误 (1.3) | 影响行为规划理解 |
| P2 | commands.py 技术债说明 (3.2) | 已部分说明但不够清晰 |
| P3 | 垃圾文件清理 (3.5) | 已在待办中 |
| P3 | 其他改进建议 (4.x) | 锦上添花 |

---

*本审查基于 2026-05-02 的代码状态，逐项与源文件比对。*
