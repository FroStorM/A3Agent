# A3Agent 通用智能体应用

## 项目概述

A3Agent 是一个基于 Tauri 框架构建的桌面智能体应用，集成了 Python 后端服务、Web 前端界面和浏览器自动化能力。应用支持多模型 LLM 对话、网页自动化操作、任务计划调度和 SOP 自动化执行。

## ⚠️ 重要提示：关于打包启动问题

如果打包后的应用运行时闪退，请查看 [BUILD_GUIDE.md](BUILD_GUIDE.md) 获取详细的问题诊断和解决方案。

**快速检查清单：**
1. ✅ 系统已安装 Python 3.8+ 并添加到 PATH
2. ✅ 已安装 Python 依赖：`python3 -m pip install -r python-backend/requirements.txt`
3. ✅ 查看启动日志：macOS 用户运行 `cat /tmp/a3agent_startup.log`

**最新改进：**
- ✅ 已添加详细的错误日志记录
- ✅ 已优化资源路径查找逻辑
- ✅ 已改进错误提示信息
- ✅ 已创建 .taurignore 优化打包体积
- ✅ 已修复窗口闪烁问题
- ✅ 支持打包为独立应用包（无需单独安装 Python 环境）

## 🎯 快速开始

### 浏览器 / 服务器模式

```bash
python3 -m pip install -r python-backend/requirements.txt
npm run build:frontend
npm run start:web
```

启动后直接访问 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

如果要部署到服务器：

```bash
python3 python-backend/web_main.py --host 0.0.0.0 --port 8000
```

可选参数：

- `--workspace /path/to/workspace`：指定工作目录
- `--no-frontend`：只暴露 API，不托管前端页面
- `--reload`：开发模式热重载

### 创建独立可运行的安装包

```bash
# 一键打包（macOS）
python3 -m pip install -r python-backend/requirements.txt
npm run build:mac
```

详见：[QUICKSTART.md](QUICKSTART.md) | [STANDALONE_BUILD.md](STANDALONE_BUILD.md) | [MAC_SETUP.md](MAC_SETUP.md)

### 开发模式

```bash
npm run tauri dev
```

---

## 目录结构

```
A3Agent/
├── python-backend/           # Python 后端核心代码
│   ├── api_server.py         # FastAPI HTTP 服务器
│   ├── agentmain.py          # Agent 主逻辑入口
│   ├── llmcore.py            # LLM 核心模块（包含 ToolClient）
│   ├── sidercall.py          # Sider API 调用模块（重复代码问题）
│   ├── agent_loop.py         # Agent 运行循环
│   ├── ga.py                 # 通用 Agent Handler
│   ├── simphtml.py           # HTML 简化处理
│   ├── TMWebDriver.py        # 浏览器驱动管理
│   ├── desktop_app.py         # PyQt5 桌面应用入口
│   ├── fsapp.py              # 飞书应用集成
│   ├── health_monitor.py      # 系统健康监控
│   ├── sop_executor.py        # SOP 执行器
│   ├── sop_validator.py       # SOP 验证器
│   ├── chatapp_common.py      # 聊天应用通用模块
│   ├── mykey.py / mykey.json  # API 密钥配置
│   ├── headless_main.py       # 无头模式入口
│   └── assets/               # 静态资源和工具定义
├── frontend/                 # Web 前端
│   └── app.js                # Vue 3 单文件应用
├── src-tauri/                # Tauri Rust 代码
└── README.md                # 本文档
```

---

## 核心模块详解

### 1. api_server.py (1170 行)

**功能**: FastAPI HTTP 服务器，提供所有 REST API 端点。

**主要类和函数**:
| 名称 | 类型 | 功能 |
|------|------|------|
| `StreamManager` | 类 | 管理 SSE 流广播，维护客户端连接队列 |
| `AppState` | 类 | 应用全局状态，包含 Agent 实例、运行状态、自动模式配置 |
| `FallbackAgent` | 类 | Agent 初始化失败时的降级处理 |
| `init_agent()` | 函数 | 初始化 Agent，加载 LLM 配置 |
| `process_agent_output()` | 函数 | 处理 Agent 输出并广播到 SSE 流 |
| `autonomous_monitor()` | 函数 | 自动模式监控线程 |
| `scheduler_monitor()` | 函数 | 计划任务调度监控 |

**API 端点**:
| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/chat` | POST | 发送聊天消息 |
| `/api/stream` | GET | SSE 流订阅 |
| `/api/status` | GET | 获取状态 |
| `/api/control` | POST | 控制操作（停止/切换模型等） |
| `/api/workspace/set` | POST | 设置工作区 |
| `/api/llm_configs` | GET/POST | LLM 配置管理 |
| `/api/sop/*` | * | SOP 文件操作 |
| `/api/schedule/*` | * | 计划任务操作 |

---

### 2. agentmain.py (380 行)

**功能**: Agent 主逻辑模块，定义 `GeneraticAgent` 类。

**主要类和函数**:
| 名称 | 类型 | 功能 |
|------|------|------|
| `GeneraticAgent` | 类 | 核心 Agent，包含 LLM 客户端、任务队列、历史管理 |
| `LLMClientLogger` | 类 | LLM 调用日志记录装饰器 |
| `start_scheduled_scheduler()` | 函数 | 计划任务调度器入口 |

**GeneraticAgent 核心方法**:
| 方法 | 功能 |
|------|------|
| `__init__()` | 初始化，加载 LLM 配置、启动健康监控 |
| `put_task()` | 向任务队列添加任务 |
| `run()` | 主运行循环，处理队列中的任务 |
| `next_llm()` | 切换到下一个 LLM |
| `abort()` | 中止当前任务 |
| `clear_history()` | 清空对话历史 |
| `reload_config()` | 重新加载 LLM 配置 |

---

### 3. llmcore.py (689 行)

**功能**: LLM 核心模块，定义各种 LLM 会话类。

**主要类和函数**:
| 名称 | 类型 | 功能 |
|------|------|------|
| `SiderLLMSession` | 类 | Sider AI API 会话 |
| `ClaudeSession` | 类 | Claude API 会话（流式） |
| `LLMSession` | 类 | OpenAI 兼容 API 会话 |
| `GeminiSession` | 类 | Google Gemini API 会话 |
| `XaiSession` | 类 | xAI API 会话 |
| `ToolClient` | 类 | 工具调用客户端，封装多个后端 |
| `MockToolCall` | 类 | 模拟工具调用 |
| `MockResponse` | 类 | 模拟响应 |
| `compress_history_tags()` | 函数 | 压缩历史消息中的标签 |
| `auto_make_url()` | 函数 | 自动构造 API URL |
| `build_multimedia_content()` | 函数 | 构建多模态内容 |

**注意**: 此模块与 `sidercall.py` 有大量重复代码，存在维护问题。

---

### 4. sidercall.py (697 行)

**功能**: Sider API 调用模块（与 `llmcore.py` 功能重复）。

**主要类**: 与 `llmcore.py` 基本相同
- `SiderLLMSession`
- `ClaudeSession`
- `LLMSession`
- `GeminiSession`
- `XaiSession`
- `ToolClient`

**问题**: 与 `llmcore.py` 存在 90%+ 重复代码，应该统一。

---

### 5. agent_loop.py (97 行)

**功能**: Agent 运行循环引擎。

**主要类和函数**:
| 名称 | 类型 | 功能 |
|------|------|------|
| `StepOutcome` | 数据类 | 步骤执行结果 |
| `BaseHandler` | 类 | 工具处理器基类 |
| `try_call_generator()` | 函数 | 尝试调用生成器 |
| `agent_runner_loop()` | 函数 | Agent 主循环 |

**StepOutcome 字段**:
- `data`: 执行结果数据
- `next_prompt`: 下一轮提示词
- `should_exit`: 是否退出循环

---

### 6. ga.py (510 行)

**功能**: 通用 Agent Handler，实现各种工具。

**主要类和函数**:
| 名称 | 类型 | 功能 |
|------|------|------|
| `A3AgentHandler` | 类 | 工具实现，包含 file_*/web_*/code_run 等 |
| `code_run()` | 生成器函数 | 代码执行器（Python/PowerShell/Bash） |
| `ask_user()` | 函数 | 请求用户输入 |
| `web_scan()` | 函数 | 获取网页简化 HTML |
| `web_execute_js()` | 函数 | 执行 JavaScript |
| `file_read()` | 函数 | 读取文件 |
| `file_patch()` | 函数 | 补丁式修改文件 |
| `file_write()` | 函数 | 写入文件 |
| `get_global_memory()` | 函数 | 获取全局记忆 |
| `format_error()` | 函数 | 格式化错误信息 |

**工具方法前缀**: `do_` + 工具名 (如 `do_file_read`)

---

### 7. simphtml.py (880 行)

**功能**: HTML 简化处理，用于减少 token 消耗。

**主要函数**:
| 名称 | 功能 |
|------|------|
| `optimize_html_for_tokens()` | 优化 HTML 减少 token |
| `get_html()` | 获取简化的页面 HTML |
| `execute_js_rich()` | 执行 JS 并捕获结果和变化 |
| `get_main_block()` | 获取页面主内容块 |
| `find_changed_elements()` | 查找 DOM 变化 |
| `get_temp_texts()` | 获取临时文本变化 |

---

### 8. TMWebDriver.py (269 行)

**功能**: 浏览器会话管理，支持 WebSocket 和 HTTP 长轮询。

**主要类和函数**:
| 名称 | 类型 | 功能 |
|------|------|------|
| `Session` | 类 | 浏览器会话 |
| `TMWebDriver` | 类 | 驱动管理类 |
| `execute_js()` | 方法 | 执行 JavaScript |
| `get_all_sessions()` | 方法 | 获取所有会话 |
| `set_session()` | 方法 | 设置默认会话 |
| `jump()` | 方法 | 跳转到 URL |
| `newtab()` | 方法 | 打开新标签页 |

---

### 9. desktop_app.py (555 行)

**功能**: PyQt5 桌面应用入口。

**主要类和函数**:
| 名称 | 类型 | 功能 |
|------|------|------|
| `FloatingLogo` | 类 | 悬浮 Logo 窗口 |
| `MainWindow` | 类 | 主窗口，包含浏览器 |
| `start_server()` | 函数 | 启动 API 服务器 |
| `stop_server()` | 函数 | 停止服务器 |
| `configure_qt_runtime()` | 函数 | 配置 Qt 运行时 |
| `wait_for_server()` | 函数 | 等待服务器就绪 |

**FloatingLogo 特性**:
- 悬浮可拖动
- 根据状态变色（空闲蓝色，运行绿色）
- 点击打开主窗口

---

### 10. health_monitor.py (68 行)

**功能**: 系统健康监控。

**主要类和函数**:
| 名称 | 类型 | 功能 |
|------|------|------|
| `HealthMonitor` | 类 | 健康监控器 |
| `start_monitor()` | 函数 | 启动监控 |

**监控指标**:
- CPU 使用率
- 内存使用率
- 网络延迟

---

### 11. sop_executor.py (215 行)

**功能**: SOP 文档自动执行器。

**主要类和函数**:
| 名称 | 类型 | 功能 |
|------|------|------|
| `SOPExecutor` | 类 | SOP 执行器 |
| `execute()` | 方法 | 执行 SOP 代码 |
| `dry_run()` | 方法 | 语法检查 |
| `list_code_blocks()` | 方法 | 列出代码块 |

---

### 12. sop_validator.py (308 行)

**功能**: SOP 文档验证工具。

**主要类和函数**:
| 名称 | 类型 | 功能 |
|------|------|------|
| `SOPValidator` | 类 | SOP 验证器 |
| `validate()` | 方法 | 执行所有验证 |
| `check_structure()` | 方法 | 检查文档结构 |
| `check_code_blocks()` | 方法 | 检查代码块 |
| `generate_report()` | 方法 | 生成验证报告 |

---

### 13. fsapp.py (466 行)

**功能**: 飞书（Feishu/Lark）应用集成。

**主要函数**:
| 名称 | 功能 |
|------|------|
| `create_client()` | 创建飞书客户端 |
| `send_message()` | 发送消息 |
| `update_message()` | 更新消息 |
| `handle_message()` | 处理接收消息 |
| `handle_command()` | 处理命令 |

---

### 14. chatapp_common.py

**功能**: 聊天应用通用函数。

**主要函数**:
- `clean_reply()`: 清理回复
- `extract_files()`: 提取文件路径
- `format_restore()`: 格式化恢复
- `public_access()`: 公共访问检查
- `to_allowed_set()`: 转换为允许集合

---

## 已识别的问题和 Bug

### 🔴 严重问题

#### 1. 代码重复问题 (llmcore.py vs sidercall.py)

**问题**: `llmcore.py` 和 `sidercall.py` 存在 90%+ 重复代码。

**影响**:
- `agentmain.py` 导入的是 `sidercall` 模块
- `llmcore.py` 导入 `sidercall` 中的类
- `ToolClient` 在两个文件中都有定义

**建议修复**: 统一使用一个模块，删除重复代码。

#### 2. 文件路径问题

**问题**: `sidercall.py` 第 387 行:
```python
with open(f'./temp/model_responses_{os.getpid()}.txt', 'a', ...) as f:
```
硬编码使用 `./temp/` 而不是 `_data_dir`。

**影响**: 在非预期目录下运行时可能失败。

---

### 🟡 中等问题

#### 3. 错误处理不完整

多处异常捕获过于宽泛，仅打印错误后继续执行，可能导致静默失败。

示例 (`api_server.py`):
```python
except Exception:
    pass  # 静默忽略
```

#### 4. 前端 marked 库依赖

`frontend/app.js` 使用 `marked.parse()` 但没有导入 `marked` 库。

**影响**: 如果 HTML 没有加载 marked，前端会报错。

#### 5. LLM 客户端初始化时没有正确传递 proxy

`agentmain.py` 中:
```python
if tp == "oai" ... or 'model' in k:
    s = LLMSession(api_key=cfg['apikey'], api_base=cfg['apibase'], model=cfg['model'], proxy=cfg.get('proxy'))
```
但 `reload_config()` 方法使用的是 `llmcore.LLMSession`，而不是 `sidercall.LLMSession`。

---

### 🟢 轻微问题

#### 6. 日志文件路径

多个模块使用 `/tmp/generic-agent-api.log`，在多用户环境下可能冲突。

#### 7. 类型检查不足

多处使用 `isinstance()` 检查但不够严格。

#### 8. 魔法数字

代码中存在大量硬编码的数字，如超时时间、重试次数等。

---

## 环境准备

### 依赖安装

```bash
# Python 依赖
pip install fastapi uvicorn requests beautifulsoup4
pip install psutil  # 健康监控（可选）

# 飞书应用额外依赖
pip install lark-oapi

# xAI 依赖（如果使用）
pip install xai-sdk
```

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `GA_BASE_DIR` | 应用根目录 | 脚本所在目录 |
| `GA_USER_DATA_DIR` | 用户数据目录 | 当前目录 |
| `GA_FRONTEND_DIR` | 前端目录 | `<BASE_DIR>/frontend` |
| `GA_MAX_HISTORY_ITEMS` | 最大历史条数 | 80 |
| `GA_MAX_HISTORY_CHARS` | 最大历史字符数 | 240000 |

---

## 构建和运行

### 开发模式

```bash
cd A3Agent
npm install
npm run tauri dev
```

### 生产构建

```bash
npm run build:frontend
npm run tauri build
```

### 直接运行 Python 后端

```bash
cd python-backend
python headless_main.py
```

### 运行桌面应用

```bash
cd python-backend
python desktop_app.py
```

---

## 配置说明

### mykey.json 配置

```json
{
    "oai_config": {
        "type": "oai",
        "apikey": "your-api-key",
        "apibase": "https://api.openai.com/v1",
        "model": "gpt-4o-mini"
    },
    "claude_config": {
        "type": "claude",
        "apikey": "your-anthropic-key",
        "apibase": "https://api.anthropic.com",
        "model": "claude-3-opus-20240229"
    }
}
```

### 工作目录结构

```
<user_data_dir>/
├── memory/              # SOP 和记忆文件
│   ├── global_mem.txt
│   ├── global_mem_insight.txt
│   └── *.md             # SOP 文档
├── temp/                # 临时文件
│   ├── model_responses_*.txt
│   └── scheduler.log
├── sche_tasks/          # 计划任务
│   ├── pending/
│   ├── running/
│   └── done/
├── mykey.json           # API 密钥
└── ToDo.txt             # 待办事项
```

---

## API 使用示例

### 发送聊天消息

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "你好，帮我写一个 Hello World 程序"}'
```

### 获取状态

```bash
curl http://localhost:8000/api/status
```

### SSE 流订阅

```javascript
const es = new EventSource('/api/stream');
es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    console.log(data);
};
```

---

## 常见问题

### 1. Agent 初始化失败

检查 `mykey.json` 配置是否正确，确保 API 密钥有效。

### 2. 前端无法加载

确认 `frontend/` 目录存在且包含 `index.html`。

### 3. 浏览器会话未连接

确保 TM WebDriver 扩展已安装并连接到 `ws://127.0.0.1:18765`。

---

## 版本信息

- Tauri: 2.x
- Python: 3.10+
- Vue: 3.x
- PyQt5: 5.x

---

*本文档由代码审查自动生成，如有问题请联系维护者。*
