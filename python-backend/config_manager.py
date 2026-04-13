"""
配置文件管理模块
负责初始化workspace和复制默认配置文件
"""
import os
import sys
import shutil


def get_resource_path(relative_path):
    """获取打包资源的路径（与api_server.py保持一致）"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)


def initialize_workspace_config():
    """
    初始化workspace配置
    如果配置文件不存在，从打包的默认配置复制
    如果存在，则跳过

    注意：此函数依赖Tauri设置的环境变量：
    - GA_WORKSPACE_ROOT: workspace根目录
    - GA_USER_DATA_DIR: ga_config目录
    """
    # 从环境变量获取路径（Tauri已经设置好了）
    workspace_root = os.environ.get('GA_WORKSPACE_ROOT')
    user_data_dir = os.environ.get('GA_USER_DATA_DIR')

    if not workspace_root or not user_data_dir:
        print("[ConfigManager] 警告: 环境变量未设置，使用默认路径")
        # 如果环境变量没有设置（开发模式），使用默认路径
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
        else:
            exe_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        workspace_root = os.path.join(exe_dir, 'workspace')
        user_data_dir = os.path.join(workspace_root, 'ga_config')
        os.environ['GA_WORKSPACE_ROOT'] = workspace_root
        os.environ['GA_USER_DATA_DIR'] = user_data_dir

    print(f"[ConfigManager] Workspace根目录: {workspace_root}")
    print(f"[ConfigManager] 配置目录: {user_data_dir}")

    # 确保目录存在
    os.makedirs(user_data_dir, exist_ok=True)

    # 检查是否需要初始化配置文件
    mykey_file = os.path.join(user_data_dir, 'mykey.json')

    if not os.path.exists(mykey_file):
        # 首次运行，复制所有默认配置
        print(f"[ConfigManager] 首次运行，初始化配置文件...")

        bundled_config = get_resource_path('ga_config')
        print(f"[ConfigManager] 从 {bundled_config} 复制到 {user_data_dir}")

        if os.path.exists(bundled_config):
            # 复制所有文件和子目录
            copied_count = 0
            for item in os.listdir(bundled_config):
                src = os.path.join(bundled_config, item)
                dst = os.path.join(user_data_dir, item)

                try:
                    if os.path.isdir(src):
                        if not os.path.exists(dst):
                            shutil.copytree(src, dst)
                            print(f"[ConfigManager] 复制目录: {item}")
                            copied_count += 1
                    else:
                        shutil.copy2(src, dst)
                        print(f"[ConfigManager] 复制文件: {item}")
                        copied_count += 1
                except Exception as e:
                    print(f"[ConfigManager] 复制失败 {item}: {e}")

            print(f"[ConfigManager] 配置初始化完成，共复制 {copied_count} 项")
        else:
            print(f"[ConfigManager] 警告: 找不到默认配置目录 {bundled_config}")
    else:
        print(f"[ConfigManager] 配置文件已存在，使用现有配置")

    return workspace_root
