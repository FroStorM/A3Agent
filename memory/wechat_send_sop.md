# 微信发送消息 SOP (macOS) - 全自动版

## 核心方案

**工具组合**: pyautogui + 剪贴板 (pbcopy)

**流程**:
1. 激活微信窗口
2. 获取窗口位置 → 计算搜索框坐标
3. 点击搜索框
4. 输入联系人名称
5. 方向键选择搜索结果
6. 剪贴板粘贴消息 (Cmd+V)
7. 回车发送

## 关键参数

```python
# 微信窗口位置（需动态获取）
win_x, win_y = 动态获取  # 左上角坐标，每次运行前获取
win_w, win_h = 动态获取  # 窗口尺寸

# 搜索框位置（窗口左侧边栏顶部）
# 方法 1：相对坐标（窗口左上角附近）
search_x = win_x + 120
search_y = win_y + 25
# 方法 2：用户手动定位（最准确）
# 将鼠标放在搜索框上，用 pyautogui.position() 获取

# 搜索结果选择：区分置顶/非置顶聊天
# is_pinned=True: 置顶聊天，直接 enter 选中（按 down 会跳过置顶项）
# is_pinned=False: 非置顶，需 down+enter 选择第一个搜索结果
if is_pinned:
    pyautogui.press('enter')  # 直接确认，选中置顶聊天
else:
    pyautogui.press('down')  # 选择第一个搜索结果
    pyautogui.press('enter')  # 确认选择

# 聊天输入框位置（窗口底部）
input_x = win_x + 300
input_y = win_y + 650
```

## 代码模板

```python
import pyautogui
import subprocess
import time

def get_wechat_window():
    """获取微信窗口位置"""
    result = subprocess.run(
        ['osascript', '-e', 'tell application "System Events" to tell process "WeChat" to get position of window 1'],
        capture_output=True, text=True
    )
    output = result.stdout.strip()
    if ', ' in output:
        x, y = map(int, output.split(', '))
    else:
        x = int(output[:2])
        y = int(output[2:])
    
    result = subprocess.run(
        ['osascript', '-e', 'tell application "System Events" to tell process "WeChat" to get size of window 1'],
        capture_output=True, text=True
    )
    output = result.stdout.strip()
    if ', ' in output:
        w, h = map(int, output.split(', '))
    else:
        w = int(output[:3])
        h = int(output[3:])
    
    return x, y, w, h

def wechat_send_full(contact, message, is_pinned=False):
    """全自动微信发送
    Args:
        contact: 联系人名称
        message: 消息内容
        is_pinned: 是否置顶聊天（True=直接 enter，False=down+enter）
    """
    pyautogui.PAUSE = 0.5
    pyautogui.FAILSAFE = False
    
    # 1. 激活微信
    subprocess.run(['osascript', '-e', 'tell application "WeChat" to activate'])
    time.sleep(1.0)
    
    # 2. 获取窗口位置
    win_x, win_y, win_w, win_h = get_wechat_window()
    
    # 3. 点击搜索框（左侧聊天列表顶部）
    search_x, search_y = win_x + 120, win_y + 25
    # 先移动光标再点击，避免直接 click 远距离坐标失败
    pyautogui.moveTo(search_x, search_y, duration=0.3)
    time.sleep(0.2)
    pyautogui.click(search_x, search_y)
    time.sleep(0.5)
    
    # 4. 清空搜索框
    pyautogui.hotkey('command', 'a')
    time.sleep(0.2)
    pyautogui.press('backspace')
    time.sleep(0.3)
    
    # 5. 输入联系人（用剪贴板粘贴中文）
    subprocess.run(['pbcopy'], input=contact.encode('utf-8'))
    time.sleep(1.0)
    pyautogui.hotkey('command', 'v')
    time.sleep(2.0)  # 等待搜索结果加载
    
    # 6. 选择搜索结果：区分置顶/非置顶
    # 置顶聊天：直接 enter（按 down 会跳过置顶项）
    # 非置顶：down+enter 选择第一个搜索结果
    if is_pinned:
        pyautogui.press('enter')  # 直接确认，选中置顶聊天
    else:
        pyautogui.press('down')  # 选择第一个搜索结果
        time.sleep(0.3)
        pyautogui.press('enter')  # 确认选择
    time.sleep(1.0)
    
    # 7. 粘贴消息
    subprocess.run(['pbcopy'], input=message.encode('utf-8'))
    time.sleep(1.0)  # 等待剪贴板就绪
    pyautogui.hotkey('command', 'v')
    time.sleep(0.5)
    
    # 9. 发送
    pyautogui.press('enter')
    time.sleep(0.5)
```

## 避坑指南

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 中文乱码 | pyautogui.write 不支持中文 | 用剪贴板粘贴 (pbcopy + Cmd+V) |
| 选错联系人 | 键盘 down+enter 不可靠 | 直接点击搜索结果坐标 |
| 窗口位置变化 | 微信窗口可移动 | 每次执行前动态获取窗口位置 |
| 搜索结果延迟 | 输入后需要等待 | 增加 time.sleep(2) 等待加载 |
| 粘贴失败只输入"v" | 剪贴板未就绪/焦点丢失 | 点击输入框确保焦点 + 等待 1s |
| 搜索框有残留内容 | 上次搜索未清空 | 先 Cmd+A 全选再 Backspace 清空 |
| 消息需加后缀 | 用户要求 | 每条消息末尾添加"——AI" |
| 坐标会变化 | 窗口位置可能改变 | 使用相对偏移坐标 (win_x+xxx, win_y+xxx) |
| 点击无反应 | 光标未移动到目标位置 | 先 pyautogui.moveTo() 再 click，避免直接 click 远距离坐标 |

## 历史验证

- 2026-03-26: pyautogui 方案流程验证完成
- 关键修复:
  - 窗口坐标动态获取 (83,157,881x701)
  - 搜索结果点击坐标：win_y+90
  - 输入框焦点点击：win_x+300, win_y+650
  - 剪贴板等待：pbcopy 后 sleep(1.0)
- 状态：✅ 全自动方案验证完成