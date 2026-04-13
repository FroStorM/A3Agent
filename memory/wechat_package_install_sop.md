# 微信自动化包安装 SOP (macOS)

## 核心原则
1. **安装前检查**: 任何包使用前先 `pip3 show <package>` 确认
2. **禁止重复安装**: 已安装包勿重装，避免版本冲突
3. **权限优先**: macOS 自动化工具需辅助功能权限

---

## 已安装包清单 (2026-03-26 实测)

| 包名 | 版本 | 用途 | 状态 |
|------|------|------|------|
| PyAutoGUI | 0.9.54 | 鼠标键盘自动化 | ✅ 已安装 |
| PyScreeze | 1.0.1 | 屏幕截图 | ✅ 已安装 |
| pytesseract | 0.3.10 | OCR 识别接口 | ✅ 已安装 |
| Pillow | 9.5.0 | 图像处理 | ✅ 已安装 |
| MouseInfo | 0.1.3 | 鼠标信息获取 | ✅ 已安装 |
| PyGetWindow | 0.0.9 | 窗口控制 | ✅ 已安装 |
| PyMsgBox | 2.0.1 | 消息框 | ✅ 已安装 |
| pytweening | 1.2.0 | 动画缓动 | ✅ 已安装 |
| pyobjc-core | 9.2 | macOS Objective-C 桥接 | ✅ 已安装 |
| pyobjc-framework-Quartz | 9.2 | macOS Quartz 框架 | ✅ 已安装 |

---

## 系统级依赖

| 依赖 | 安装命令 | 用途 |
|------|---------|------|
| tesseract | `brew install tesseract` | OCR 引擎 |
| tesseract-lang | `brew install tesseract-lang` | 多语言包 (含中文) |

验证 tesseract:
```bash
which tesseract  # 应返回 /opt/homebrew/bin/tesseract
tesseract --version
```

---

## 安装检查脚本

```python
import subprocess
import sys

REQUIRED_PACKAGES = [
    'pyautogui', 'pyscreeze', 'pytesseract', 'Pillow',
    'mouseinfo', 'pygetwindow', 'pymsgbox', 'pytweening',
    'pyobjc-core', 'pyobjc-framework-Quartz'
]

def check_packages():
    """检查所有必需包是否已安装"""
    missing = []
    installed = {}
    
    for pkg in REQUIRED_PACKAGES:
        result = subprocess.run(
            ['pip3', 'show', pkg],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            # 提取版本
            for line in result.stdout.split('\n'):
                if line.startswith('Version:'):
                    installed[pkg] = line.split(':')[1].strip()
                    break
        else:
            missing.append(pkg)
    
    print("=== 已安装包 ===")
    for pkg, ver in installed.items():
        print(f"✅ {pkg}: {ver}")
    
    if missing:
        print("\n=== 缺失包 ===")
        for pkg in missing:
            print(f"❌ {pkg}")
        return False
    return True

if __name__ == '__main__':
    if check_packages():
        print("\n✅ 所有包已就绪")
    else:
        print("\n⚠️ 有包缺失，请运行安装命令")
```

---

## 安装命令 (仅首次)

```bash
# 核心自动化包
pip3 install pyautogui pyscreeze pytesseract Pillow

# 依赖包 (通常自动安装)
pip3 install mouseinfo pygetwindow pymsgbox pytweening

# macOS 专用
pip3 install pyobjc-core pyobjc-framework-Quartz

# 系统级 OCR 引擎
brew install tesseract tesseract-lang
```

---

## 权限配置 (macOS 关键)

PyAutoGUI 和 AppleScript 需要**辅助功能权限**:

1. 系统设置 → 隐私与安全性 → 辅助功能
2. 添加以下应用到允许列表:
   - 终端 (Terminal)
   - Python (python3)
   - 你的 IDE (VSCode/PyCharm 等)
3. 重启应用生效

验证权限:
```python
import pyautogui
print(pyautogui.position())  # 能返回坐标则权限正常
```

---

## 常见问题

| 问题 | 解决方案 |
|------|---------|
| `ImportError: No module named 'pyautogui'` | 运行 `pip3 install pyautogui` |
| 鼠标不移动 | 检查辅助功能权限 |
| OCR 识别中文乱码 | 安装 `tesseract-lang` 并指定 `lang='chi_sim'` |
| 屏幕坐标偏移 | Retina 屏幕需考虑缩放，用 `pyautogui.size()` 动态获取 |

---

## 记忆索引
- Python 路径：`/Library/Frameworks/Python.framework/Versions/3.7/bin/python3`
- 包安装位置：`/Library/Frameworks/Python.framework/Versions/3.7/lib/python3.7/site-packages`
- Tesseract 路径：`/opt/homebrew/bin/tesseract`
- **最后更新**: 2026-03-26