# A3Agent

A3Agent 是基于 GenericAgent 改造的本地桌面 Agent 应用。当前工程的目标不是继续维护原始 Streamlit 前端，而是提供一套前后端分离、可桌面打包、可长期替换后端能力的本地智能体工作台。

这个版本的重点是：

- 前端固定为 `frontend/` 下的 Web UI，负责聊天、模型配置、SOP、历史会话、记忆文件、数据备份和桌宠配置。
- 后端由 `api_server.py` 暴露 REST API 与 SSE 流式输出，核心执行仍由 `agentmain.py`、`agent_loop.py`、`ga.py`、`llmcore.py` 驱动。
- 桌面应用由 `launch_app.py` 启动本地后端，并用 macOS 原生 WebKit 打开窗口，不依赖用户浏览器。
- 数据、配置、SOP、历史和桌宠设置写入用户目录，应用包内文件只作为默认模板，避免每次升级覆盖用户工作结果。

## 目录结构

```text
.
├── api_server.py                 # FastAPI 后端，提供聊天、配置、SOP、历史、备份、桌宠 API
├── launch_app.py                 # macOS 桌面启动器，内置 WebKit 窗口与桌宠控制
├── frontend/                     # 当前主前端，不再依赖浏览器打开
├── frontends/                    # 原 GenericAgent 自带前端与桌宠资源，保留兼容能力
├── memory/                       # 默认 SOP/记忆模板，首次启动或缺失时复制到用户数据目录
├── assets/                       # 工具 schema、系统提示词、报告等资源
├── reflect/                      # 自主运行和计划任务模块
├── plugins/                      # 可选插件
├── build_macos_standalone_app.sh # 打包独立 macOS App
└── dist/standalone/A3Agent.app   # 打包输出位置
```

## 数据目录

开发目录和应用目录要分清：

- 开发环境：`/Users/guofang/Documents/06code/GenericAgent-20260430`
- 应用环境：`/Applications/A3Agent.app`
- 用户数据：`~/Library/Application Support/A3Agent`
- 默认工作区：`~/Library/Application Support/A3Agent/workspace`
- 默认配置库：`~/Library/Application Support/A3Agent/workspace/ga_config`
- SOP/记忆主库：`~/Library/Application Support/A3Agent/workspace/ga_config/memory`
- 历史会话：`~/Library/Application Support/A3Agent/conversations`
- 自动备份：`~/Library/Application Support/A3Agent/backups`
- 桌宠配置：`~/Library/Application Support/A3Agent/desktop_pet.json`

注意：`memory/` 是随包模板，不应作为用户长期编辑主库。用户运行后产生的配置、SOP、历史、记忆和桌宠设置都应以用户数据目录为准。

## 开发运行

推荐使用 Python 3.12。

```bash
cd /Users/guofang/Documents/06code/GenericAgent-20260430
python3 -m pip install -e .
python3 -m pip install fastapi uvicorn requests beautifulsoup4 pillow pyobjc pyinstaller
python3 api_server.py
```

开发后端默认监听：

```text
http://127.0.0.1:8000
```

开发时也可以直接打开：

```text
frontend/index.html
```

但桌宠、原生窗口、应用内快捷键和完整打包效果需要通过桌面 App 测试。

## 主要功能

- 聊天执行：通过 `/api/chat` 提交任务，通过 `/api/stream` 获取 SSE 流式输出。
- 模型管理：前端支持新增、测试、保存、切换模型配置。
- 模式入口：输入框上方提供 `@plan`、`@watch`、`@sop`、`@review` 快捷入口。
- SOP 技能库：可查看、编辑、保存用户 SOP 文件。
- 历史会话：按 session 记录，可以恢复到历史对话并继续上下文。
- 记忆文件：可查看完整记忆文件。
- 数据备份：关键配置、历史、记忆和桌宠设置会自动备份，也可手动创建快照。
- 桌面宠物：支持开关、尺寸和皮肤选择，配置保存后运行中自动应用。
- Workspace：支持切换工作区，配置会跟随工作区隔离。

## 常用接口

```text
GET  /api/status
POST /api/chat
GET  /api/stream
POST /api/control
GET  /api/conversation/current
GET  /api/conversations
POST /api/conversations/{session_id}/restore
GET  /api/memory/list
GET  /api/memory/read
GET  /api/sop/list
GET  /api/sop/read
POST /api/sop/write
GET  /api/backups
POST /api/backups/create
GET  /api/desktop_pet/config
POST /api/desktop_pet/config
GET  /api/desktop_pet/skins
```

SSE 空闲时后端会定期发送 heartbeat，前端也有 watchdog，会在长时间不用或窗口恢复焦点时自动重连，避免界面假死。

## 打包 macOS App

独立 App 打包使用 Python 3.12 和 PyInstaller。打包结果会包含 Python 运行环境，用户双击即可使用，不需要单独配置 Python。

```bash
cd /Users/guofang/Documents/06code/GenericAgent-20260430
./build_macos_standalone_app.sh standalone-$(date +%Y%m%d)
```

输出：

```text
dist/standalone/A3Agent.app
dist/A3Agent-standalone-YYYYMMDD.zip
```

替换应用版时，先确认开发版稳定，再替换：

```bash
cp -R dist/standalone/A3Agent.app /Applications/A3Agent.app
open -n /Applications/A3Agent.app
```

如果需要保留旧应用，可先手动复制 `/Applications/A3Agent.app` 到备份位置。用户数据不在 App 包内，正常替换 App 不会删除历史对话和配置。

## 升级与备份原则

为了避免覆盖用户工作结果，后续更新应遵守：

- 先改开发环境，验证通过后再打包替换 `/Applications/A3Agent.app`。
- 不要直接覆盖 `~/Library/Application Support/A3Agent/workspace/ga_config/memory`。
- 包内 `memory/` 新增的 SOP 应作为默认模板或迁移来源，不应强制覆盖用户主库。
- 写入配置、SOP、桌宠、workspace history 前会创建备份。
- 发布前建议在前端“数据备份”中手动创建一次快照。

## 后续后端替换方式

这个工程的前端尽量保持稳定，后续后端开发可以主要替换：

- `api_server.py`
- `ga.py`
- `llmcore.py`
- `agentmain.py`
- `agent_loop.py`
- `assets/tools_schema.json`
- `assets/sys_prompt.txt`
- `memory/*.md` 中需要新增的 SOP 模板

只要接口语义保持一致，前端通常不需要同步修改。

## 验证清单

每次修改后建议至少执行：

```bash
python3 -m py_compile api_server.py launch_app.py ga.py llmcore.py agentmain.py agent_loop.py
node --check frontend/app.js
curl -sS --max-time 5 http://127.0.0.1:8000/api/status
```

打包后建议验证：

- App 能双击启动。
- 不会额外打开空白浏览器窗口。
- `Command+C / Command+V` 可在输入框和输出区域正常使用。
- 新建对话、恢复历史会话、SOP 编辑、记忆文件查看正常。
- 桌宠无边框、无黑底，保存配置后能自动切换。
- 重启 App 后配置和历史仍保留。

## License

本工程基于 GenericAgent 的 MIT License 继续开发。详见 [LICENSE](LICENSE)。
