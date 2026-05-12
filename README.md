# 喵酱 Live2D Desktop Pet

A virtual desktop pet with Live2D avatar and LLM-powered conversation.

## How AI Controls the Pet

The LLM (Large Language Model) can control the pet's expressions and actions by appending a structured JSON block at the end of each reply.

### Quick Start

The system works automatically once configured:

1. Start the backend (`uv run run_server.py` in `Open-LLM-VTuber/`)
2. Run the pet (`python main.py`)
3. Type in the chat bar or use quick-action buttons (😊😢👋🔄)

The LLM will output JSON commands automatically. No manual intervention needed.

### How It Works

```
User: "挥个手"
  → Pet detects keyword, bypasses LLM
  → Directly plays "wave" motion
  → (D2: Keyword bypass)

User: "今天好开心！"
  → Pet sends text to LLM via WebSocket
  → LLM replies with text + JSON block:
    "是呀~ 天气这么好！ 
    ```json
    {"action": "dance", "expression": "happy", "text": "好开心~"}
    ```"
  → Python parses JSON → calls JS bridge → pet dances + smiles + shows bubble
  → (A5: _apply_command + C1/C2: catalogs + B3: response parsing)
```

### JSON Protocol

The LLM appends a fenced JSON block at the end of each reply:

```json
{"action": "<action_name>", "expression": "<expression_name>", "text": "<bubble_text>"}
```

All fields are optional. Only include fields you want to change.

### Available Actions

| Action      | Description         |
|-------------|---------------------|
| `idle`      | Stand still         |
| `wave`      | Wave paw            |
| `dance`     | Dance               |
| `nod`       | Nod head            |
| `shake_head`| Shake head          |
| `spin`      | Twirl around        |
| `jump`      | Hop                 |
| `stretch`   | Stretch (random)    |
| `bow`       | Bow (random)        |
| `clap`      | Clap (random)       |

### Available Expressions

| Expression   | Description      |
|--------------|------------------|
| `neutral`    | Default face     |
| `happy`      | Smile            |
| `shy`        | Blush            |
| `surprised`  | Eyes wide        |
| `angry`      | Glare            |
| `sad`        | Droopy           |
| `sleepy`     | Half-closed      |
| `love`       | Heart eyes       |

### Architecture

```
LLM (Ollama)
  │ WebSocket JSON
  ▼
Open-LLM-VTuber (backend server)
  │ WebSocket
  ▼
main.py (PySide6 + QWebEngineView)
  │
  ├─ _inject_js(): intercept WS → parse JSON command
  ├─ command_parser.py: extract PetCommand from LLM text
  ├─ _enqueue_command(): queue commands (2.5s interval)
  └─ _apply_command():
       ├─ MotionCatalog → __petPlayMotion(group, index)
       ├─ ExpressionCatalog → __petSetExpressionByName(name)
       └─ strip_command_block → SpeechBubble.show_text()
```

### Files

| File | Purpose |
|------|---------|
| `pet_core/commands.py` | `PetCommand` data class + validation |
| `pet_core/command_parser.py` | Extract JSON from LLM text |
| `pet_core/expression_catalog.py` | Expression name → index mapping |
| `pet_core/motion_catalog.py` | Action name → (group, index) mapping |
| `config/pet_actions.json` | Configurable catalogs for different models |
| `prompts/action_protocol.md` | LLM system prompt for JSON output |
| `tests/test_command_parser.py` | Parser unit tests |
| `tests/test_expression_catalog.py` | Expression catalog tests |
| `tests/test_motion_catalog.py` | Motion catalog tests |
| `tests/test_command_e2e.py` | End-to-end pipeline tests |
