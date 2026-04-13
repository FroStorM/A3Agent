# 微信消息读取 SOP (macOS) - OCR 方案

## 核心方案

**工具组合**: pyautogui + pyscreeze + tesseract OCR + pytesseract

**原理**: 微信数据库加密无法直接读取，采用屏幕截图 + OCR 识别聊天窗口内容

---

## 前置检查 (必须执行)

### 1. 辅助功能权限检查
```python
import subprocess

def check_accessibility():
    result = subprocess.run(
        ['osascript', '-e', 'tell application "System Events" to get name of processes'],
        capture_output=True, text=True
    )
    if "WeChat" not in result.stdout:
        raise PermissionError("需要辅助功能权限：系统设置→隐私→辅助功能→添加终端/Python")
    return True
```

### 2. 依赖检查
```python
import pip3

def check_deps():
    required = ['pyautogui', 'pyscreeze', 'pytesseract', 'PIL']
    for pkg in required:
        try:
            __import__(pkg.lower().replace('pytesseract', 'pytesseract').replace('pil', 'PIL'))
        except ImportError:
            pip3.main(['install', pkg])
```

### 3. Tesseract 检查
```bash
which tesseract  # 必须返回路径，否则 brew install tesseract
```

---

## 窗口定位 (动态获取，非硬编码)

```python
import subprocess
import json

def get_wechat_window():
    """获取微信窗口真实位置，避免硬编码坐标"""
    script = '''
        tell application "System Events"
            if not (exists process "WeChat") then
                return {"error": "WeChat not running"}
            end if
            set winPos to position of window 1 of process "WeChat"
            set winSize to size of window 1 of process "WeChat"
            return {x:item 1 of winPos, y:item 2 of winPos, w:item 1 of winSize, h:item 2 of winSize}
        end tell
    '''
    result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=5)
    if result.returncode != 0:
        return None
    # 解析返回：x:83, y:157, w:881, h:701
    coords = {}
    for part in result.stdout.strip().split(', '):
        k, v = part.split(':')
        coords[k] = int(v)
    return coords
```

**实测参考值** (2026-03-26, MacBook Pro):
- 窗口位置：x:83, y:157
- 窗口大小：w:881, h:701
- 屏幕分辨率：1512x982

---

## 消息区域定位

```python
def get_chat_area(window):
    """
    计算聊天消息区域坐标
    微信窗口布局：左侧联系人列表 (~250px)，右侧聊天区
    聊天区：顶部标题栏 (~50px)，底部输入框 (~80px)
    """
    if not window:
        return None
    
    # 聊天消息区域 (右侧，排除输入框和标题栏)
    chat_x = window['x'] + 250  # 左侧联系人列表宽度
    chat_y = window['y'] + 50   # 顶部标题栏高度
    chat_w = window['w'] - 250 - 50  # 减去左侧和右侧边距
    chat_h = window['h'] - 50 - 80   # 减去顶部和底部输入框
    
    return {
        'x': chat_x,
        'y': chat_y,
        'w': chat_w,
        'h': chat_h
    }
```

---

## OCR 识别流程

```python
import pyautogui
import pytesseract
from PIL import Image
import io

def read_wechat_messages(retries=3):
    """读取微信最新消息，带重试机制"""
    
    # 1. 权限和依赖检查
    check_accessibility()
    
    # 2. 获取窗口位置 (动态)
    window = None
    for i in range(retries):
        window = get_wechat_window()
        if window and 'error' not in str(window):
            break
        time.sleep(1)
    
    if not window:
        raise RuntimeError("无法获取微信窗口位置")
    
    # 3. 计算消息区域
    chat_area = get_chat_area(window)
    if not chat_area:
        raise RuntimeError("无法计算聊天区域")
    
    # 4. 截图 (使用区域截图提高效率)
    screenshot = pyautogui.screenshot(
        region=(chat_area['x'], chat_area['y'], chat_area['w'], chat_area['h'])
    )
    
    # 5. 图像预处理 (提高 OCR 准确率)
    # 转灰度
    gray = screenshot.convert('L')
    # 二值化 (可选，根据实际效果调整)
    # gray = gray.point(lambda x: 0 if x < 128 else 255, '1')
    
    # 6. OCR 识别 (中文配置)
    text = pytesseract.image_to_string(gray, lang='chi_sim+eng')
    
    return {
        'raw_text': text,
        'window': window,
        'chat_area': chat_area,
        'timestamp': time.time()
    }
```

---

## 错误处理与重试

| 错误类型 | 处理方案 |
|---------|---------|
| 辅助功能权限不足 | 引导用户到系统设置添加权限 |
| 微信未运行 | 提示用户启动微信或尝试 osascript 打开 |
| 窗口获取失败 | 重试 3 次，间隔 1 秒 |
| OCR 识别为空 | 检查截图区域是否正确，调整坐标偏移 |
| tesseract 未安装 | brew install tesseract tesseract-lang |

---

## 性能优化建议

1. **区域截图**: 只截取聊天区域，避免全屏截图
2. **坐标缓存**: 窗口位置变化不大时可缓存，定期刷新
3. **图像预处理**: 根据实际效果调整二值化阈值
4. **语言包**: 确保安装中文语言包 `brew install tesseract-lang`

---

## 使用示例

```python
from wechat_response_sop import read_wechat_messages

try:
    result = read_wechat_messages()
    print("最新消息:", result['raw_text'][-500:])  # 打印最后 500 字符
except PermissionError as e:
    print("权限错误:", e)
except RuntimeError as e:
    print("运行错误:", e)
```

---

## 注意事项

1. **不要直接读取微信数据库**: ~/Library/Containers/com.tencent.xinWeChat/Data/ 下数据库已加密
2. **坐标非固定**: 不同分辨率/窗口大小需动态获取
3. **OCR 准确率**: 受字体大小、背景色影响，必要时调整预处理
4. **隐私合规**: 仅用于自动化测试，勿用于非法用途