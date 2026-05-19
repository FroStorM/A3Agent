# A3Agent Windows 发布包

## 推荐给最终用户

优先分发 `A3Agent-Setup-*.exe` 安装包。安装包会：

- 安装 A3Agent 到当前用户目录，不需要管理员权限
- 创建开始菜单快捷方式
- 可选创建桌面快捷方式
- 提供 Windows 卸载入口
- 保留 `%APPDATA%\A3Agent` 下的配置、聊天记录、备份和桌宠设置

## 开发测试/便携使用

`A3Agent-windows-*.zip` 继续保留，用于开发测试或便携运行。解压后请直接运行 `A3Agent.exe`，不要只单独拷贝 exe，必须保留同目录下的 `_internal` 文件夹。

## 用户数据位置

安装、升级或卸载程序本体时，默认不会删除用户数据：

- `%APPDATA%\A3Agent\workspace\ga_config`
- `%APPDATA%\A3Agent\conversations`
- `%APPDATA%\A3Agent\desktop_pet.json`
- `%APPDATA%\A3Agent\backups`
