# 关联文档审查报告

> 审查日期: 2026-05-02
> 审查范围: roadmap.md、README.md、prompts/action_protocol.md、config/pet_actions.json

---

## 1. roadmap.md

### 优点
- 任务清单清晰，A-G 阶段划分合理
- 每条 changelog 标注了完成日期
- 与 `/loop` 自动消费机制配合良好

### 问题

#### 1.1 所有任务已打勾但无后续规划

文档底部 `Blocked` 节写明全阶段已完成，但没有新阶段的规划。建议追加：
- **阶段 H**: 测试补全（motion_adapter、persistence、tts）
- **阶段 I**: Electron/PySide6 统一
- **阶段 J**: Git 初始化 + CI/CD

#### 1.2 Changelog 全部标注 2026-04-29

18 条 changelog 全部在同一天完成，缺乏时间段区分。如果确实是一天内完成的，建议标注具体时间段（部分已有，如 17:30、17:55）。

#### 1.3 缺少验收标准

每个任务只有标题，没有明确的完成标准（Definition of Done）。例如 A1「修复 Happy 组 bug」，怎样算修好了？建议为关键任务补充验收条件。

---

## 2. README.md

### 优点
- Quick Start 三步走简洁明了
- JSON Protocol 示例清晰
- Actions/Expresssions 表格方便查阅
- Architecture 图直观

### 问题

#### 2.1 Expressions 表包含 `wink` 但配置中不存在

README 列出 9 个表情（含 `wink`），但 `config/pet_actions.json` 的 `index_to_name` 只映射了 0-7（8 个），没有 wink。`aliases` 中也没有 wink。

可能情况：
- mao_pro 模型不支持第 9 个表情 → 应从 README 移除
- pet_actions.json 遗漏 → 应补上

#### 2.2 Actions 表的 `stretch`/`bow`/`clap` 标注为 "(random)"

这三个在 pet_actions.json 中被归为 `random_actions`，README 标注 "(random)" 含义不明。读者会疑惑：是随机选择？还是随机触发？

**建议**: 改为「随机动作组中的一个」或添加脚注说明。

#### 2.3 缺少安装/依赖说明

README 没有提到：
- Python 版本要求
- `pip install -r requirements.txt`
- Ollama 安装和模型下载
- Open-LLM-VTuber 后端的启动方式（仅提到 `uv run run_server.py`，未说明 uv 是什么）

**建议**: 补充 Prerequisites 和 Installation 章节。

#### 2.4 Architecture 图中 `_inject_js()` 已不存在

代码中 JS 注入在 `main.py` 的 `_setup_web_channel()` 方法中，没有叫 `_inject_js()` 的函数。图中引用的函数名应与实际代码一致。

---

## 3. prompts/action_protocol.md

### 优点
- 结构清晰，Actions/Expressions 表格完整
- JSON 格式示例覆盖了三种场景（带动作、仅表情、仅文本）
- Rules 部分实用

### 问题

#### 3.1 示例的 Markdown 围栏嵌套有误

```markdown
```
你好呀~今天过得怎么样？
```json
{"action": "wave", "expression": "happy", "text": "你好呀~"}
```
```
```

外层用三个反引号围栏，内层也有三个反引号，渲染时可能产生嵌套解析问题。

**建议**: 外层用四个反引号，或改用缩进代码块。

#### 3.2 缺少「不输出 JSON」的指引

Rules 第 1 条说「Always end your reply with a ```json block」，但有时 LLM 可能不需要改变动作/表情。虽然第 3 条说了可以省略字段，但仍要求输出空 JSON 块 `{"text": "..."}`。

**建议**: 明确说明：如果不需要任何动作/表情变更，可以只输出 `{"text": "简短回应"}`，或完全省略 JSON 块。

#### 3.3 text 字段 200 字符限制与代码不一致

action_protocol.md 说 `text` 不超过 200 字符，但 `commands.py:33` 的 `MAX_TEXT_LEN = 500`。

**建议**: 统一为 500（代码值），或收紧代码为 200。

---

## 4. config/pet_actions.json

### 优点
- 结构清晰，index_to_name + aliases 双向映射
- 支持中英文别名
- random_actions 设计巧妙

### 问题

#### 4.1 缺少 `wink` 表情映射

与 README/action_protocol 的 9 表情列表不一致。需确认并补齐或移除文档中的 wink。

#### 4.2 中文别名 `眨眼` 映射到 `3`（happy）

`pet_actions.json:31` 中 `"眨眼": 3` 映射到 happy（索引 3），但「眨眼」语义上应该对应 wink。如果模型不支持 wink，这个映射可以接受但应在注释中说明。

#### 4.3 缺少 `idle` 动作到 Idle 组的映射

`motion_groups.Idle` 只有 `["idle"]`，但 `motion_groups.""` 有 6 个动作。代码中 `MotionAdapter.get_motion()` 返回的是组名，具体 index 由 JS 桥决定。这里 idle 映射到 Idle 组是正确的，但建议在 JSON 中添加注释说明组名与 Live2D model3.json 的 motion group 对应关系。

---

## 5. 跨文档一致性矩阵

| 声明 | PROJECT_SUMMARY | README | action_protocol | pet_actions.json | 代码实际 |
|------|-----------------|--------|-----------------|------------------|----------|
| 动作数 | 未明确列 | 10 | 10 | 10 | 10 ✅ |
| 表情数 | 未明确列 | 9 (含 wink) | 9 (含 wink) | 8 (无 wink) | 8 (代码) |
| text 最大长度 | 未提及 | 未提及 | 200 | N/A | 500 |
| 行为数 | 15 (错误) | N/A | N/A | N/A | 16 |
| 测试数 | ~100 (错误) | N/A | N/A | N/A | 112 |
| 角色数 | 26 | N/A | N/A | N/A | 26 模型 + 30 YAML |
| 保存路径 | ~/.miaogiang-pet | N/A | N/A | N/A | ✅ |

---

## 6. 综合修改建议（按优先级）

### P0 — 必须修正
1. **PROJECT_SUMMARY 测试数量** — test_state.py (30)、test_command_parser.py (36)
2. **PROJECT_SUMMARY PetBehavior** — 移除 YAWN/PLAY，补上 SLEEPY/SHOW_LOVE，改为 16 种
3. **PROJECT_SUMMARY 定时器周期** — _save_timer=60s, _tick_timer=15s

### P1 — 建议修正
4. **wink 表情一致性** — 四个文档/pet_actions.json 需统一
5. **text 长度限制** — action_protocol (200) vs 代码 (500) 统一
6. **roadmap 阶段标签** — 与 PROJECT_SUMMARY 对齐或注明差异
7. **README 补充安装说明**

### P2 — 改善建议
8. 补充 motion_adapter/persistence/tts 测试
9. 删除 =1.7.0 / =6.6.0 垃圾文件
10. 初始化 Git 仓库
11. 统一项目名拼写 (miaogiang vs miaojiang)

---

*本审查基于 2026-05-02 的代码状态。*
