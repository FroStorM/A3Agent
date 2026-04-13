# A3Agent macOS 首次打包清单

## 先准备这些

1. `python3`
2. `node` 和 `npm`
3. `cargo`
4. Xcode Command Line Tools
5. Python 依赖：`python3 -m pip install -r python-backend/requirements.txt`

## 一键检查和打包

```bash
npm run check:mac
npm run build:mac
```

## 你会得到什么

- `src-tauri/target/release/bundle/macos/A3Agent.app`
- `src-tauri/target/release/bundle/dmg/`

## 首次运行时的数据目录

默认会放到：

`~/Library/Application Support/A3Agent/workspace/ga_config/`

里面主要有：

- `mykey.json`
- `memory/`
- `sche_tasks/`
- `temp/`

## 如果启动失败

1. 先看环境检查：`npm run check:mac`
2. 再看启动日志：`cat /tmp/a3agent_startup.log`
3. 确认 `src-tauri/binaries/` 下有对应架构的 sidecar

## 如果你是 Apple Silicon

sidecar 名字要是：

`src-tauri/binaries/python-backend-aarch64-apple-darwin`

## 如果你是 Intel Mac

sidecar 名字要是：

`src-tauri/binaries/python-backend-x86_64-apple-darwin`
