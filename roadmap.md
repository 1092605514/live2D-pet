# live2d-pet AI 化改造路线图

> 本文件由 Claude `/loop` 自动消费。每轮认领第一个未打勾任务实施 → 跑测试 → 在对应行打勾 + 追加一条 changelog。
>
> 计划详情：`C:\Users\10926\.claude\plans\rippling-mapping-rocket.md`
>
> 目标：把桌宠从"状态机驱动表情"升级为"LLM 输出 JSON 指令直接驱动表情和动作"。

## 任务清单

### 阶段 A — 基础设施（让 LLM 能驱动桌宠）

- [x] **A1**. 修复 `pet_core/motion_adapter.py` Happy 组 bug：mao_pro 模型只有 `"Idle"` 和 `""`(空)两个动作组，把指向不存在的 `"Happy"` 的映射改成可用动作（建议 EAT/PETTED/SHOW_LOVE → `""` 组的某个 special motion）。
- [x] **A2**. 在 `pet_core/` 新建 `commands.py`：定义 `PetCommand` 数据类（`action`, `expression`, `text`），加白名单校验。
- [x] **A3**. 在 `pet_core/` 新建 `command_parser.py`：从 LLM 文本里提取 ` ```json ``` ` 块或裸 JSON，宽松容错，返回 `PetCommand | None`。配 `tests/test_command_parser.py`。
- [x] **A4**. 扩展 JS 桥：`window.__petPlayMotion(group, index, priority)` 已注入（`main.py:529-540`），直接调 `model.startMotion`。
- [x] **A5**. Python 侧 `main.py` 加 `_apply_command(cmd: PetCommand)`：根据 cmd 调 `_send_l2d_motion` / `__petSetExpressionByName` / 气泡。

### 阶段 B — 让 LLM 学会输出 JSON

- [x] **B1**. 写系统提示词补丁 `prompts/action_protocol.md`：列可用 action / expression + JSON 示例，要求 LLM 在每条回复末尾追加 ` ```json``` ` 块。
- [x] **B2**. 把提示词注入到 `Open-LLM-VTuber/conf.yaml` persona：在 `persona_prompt` 末尾追加结构化动作指令（JSON 块协议），与旧版表情标签共存。
- [x] **B3**. 改 `_on_js_console` + `_on_poll_result`：接收 LLM 回复时用 `command_parser.parse` 提取 JSON 指令，调用 `_apply_command`，气泡显示清洗后的纯文本。

### 阶段 C — 表情/动作语义化

- [x] **C1**. 新建 `pet_core/expression_catalog.py`：8 个 `exp_0X` 各配语义名 + 中英文 alias 表 + 测试。JS 桥 `__petSetExpressionByName` 改用 catalog 驱动。
- [x] **C2**. 新建 `pet_core/motion_catalog.py`：7 个 motion 配语义名 + 别名表 + 测试。`_apply_command` 改用 catalog 做精确动作调度。
- [x] **C3**. 给两份 catalog 写 fallback：未知名→默认（已有）；`_apply_command` 加冷却检查（3s 内同动作/表情跳过）。

### 阶段 D — 用户直触发

- [x] **D1**. Python `ChatBar` + `chat_overlay.html`（Electron）加快捷按钮（😊😢👋🔄），点击直接触发动作 / 表情。
- [x] **D2**. `_on_chat_submit` 加关键词检测（"挥个手"/"转圈"/"跳舞"/"做个鬼脸"等），命中不走 LLM 直接触发。

### 阶段 E — 鲁棒性

- [x] **E1**. 动作冷却 + 队列：`_cmd_queue` + `_queue_timer`（2.5s 间隔），LLM 指令排队执行，用户直触发跳过队列。
- [x] **E2**. 异常恢复：所有 JS 桥调用加 `_log_js_result` 回调 + 队列 `try/except`，单条失败不阻塞。
- [x] **E3**. 端到端集成测试 `tests/test_command_e2e.py`（10 项）：模拟 LLM 回复 → parse → validate → PetCommand 全链路。

### 阶段 F — Polish

- [x] **F1**. 把 catalog 抽到 `config/pet_actions.json`，两个 catalog 均支持 `from_config()` 类方法加载。
- [x] **F2**. 托盘菜单加"📋 AI 指令日志"面板（`CommandLogPanel`），浮动窗口显示最近 20 条指令。
- [x] **F3**. README 章节："如何让 AI 控制桌宠"。

### 阶段 G — 主动 AI 交互

- [x] **G1**. AI 主动聊天：闲置 90s 后自动触发 LLM 对话，8 条随机提示词，托盘菜单开关。

## Changelog

- 2026-04-29 第一轮：确认 A1-A4 已就绪，修复缺失的 `window.__petSendMotion` 桥接函数
- 2026-04-29 完成 A5：添加 `_apply_command` + `__petSetExpressionByName` JS 桥
- 2026-04-29 完成 B1：创建 `prompts/action_protocol.md`，定义动作/表情清单 + JSON 格式规范
- 2026-04-29 完成 B2：注入 `conf.yaml` persona_prompt，追加结构化动作指令
- 2026-04-29 完成 B3：两个桥接方法解析 LLM 回复中的 JSON 指令并自动应用
- 2026-04-29 完成 C1：创建 `expression_catalog.py` + 12 项测试，JS 桥改用 catalog 驱动
- 2026-04-29 完成 C2：创建 `motion_catalog.py` + 测试，`_apply_command` 用 catalog 精确调度动作
- 2026-04-29 完成 C3：两个 catalog 的 fallback + `_apply_command` 冷却检查
- 2026-04-29 完成 D1：Python ChatBar + Electron chat_overlay 加快捷按钮
- 2026-04-29 完成 D2：关键词检测，命中不走 LLM 直接触发动作/表情
- 2026-04-29 完成 E1：动作队列（2.5s 间隔），LLM 指令排队执行
- 2026-04-29 完成 E2：JS 桥错误日志 + 队列 try/except 异常恢复
- 2026-04-29 完成 E3：端到端集成测试（10 项），覆盖 parse→validate→PetCommand 全链路
- 2026-04-29 完成 F1：catalog 配置化，`config/pet_actions.json` + `from_config()`
- 2026-04-29 完成 F2：托盘菜单 🤖 AI 指令日志面板（浮动窗口，显示最近 20 条）
- 2026-04-29 完成 F3：README 架构文档，含快速开始、JSON 协议、动作/表情表、文件清单
- 2026-04-29 完成 G1：AI 主动聊天 — 闲置 90s 后通过 WS 发送随机提示词触发 LLM 对话，托盘菜单开关
- 2026-04-29 17:30 修复气泡换行：多行/多段 LLM 回复不再只显示最后一行，改为逐条排队显示（间隔 3s），QFontMetrics 精确计算气泡高度
- 2026-04-29 17:55 新增全局快捷键：Ctrl+Shift+H 显隐窗口，Ctrl+Shift+L 切换 Live2D 模型；Chat 快捷键改为 toggle 行为
- 2026-05-02 重构 Live2D 模型切换：`__petSwitchConfig` 优先走前端原生 WS，`_bridgeResponse` 捕获 `set-model-and-conf`，添加 10s 超时 + 1.5s 后 canvas 验证 + 气泡反馈（正在切换/已切换/超时/失败）
- 2026-05-03 TTS 自然度优化：新增 `pet_core/tts_preprocessor.py` 文本清洗（markdown/emoji/JSON 片段/URL）+ 分句分段；移除硬编码 "~喵" 后缀；MiMoTTS 新增 `speak_segments()` 多段播放和 `speed` 语速参数；TTS 调用链全面接入预处理器；新增 42 个测试

## Blocked

路线图全阶段（A-G）所有任务均已打勾完成，无未完成任务可认领。如需继续，请在路线图中追加新阶段/新任务。
