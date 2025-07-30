"""
Flask-Admin 补丁文件
修复 Flask-Admin 1.6.1 与 Flask 2.x/3.x 的兼容性问题
"""
import os
import sys
import importlib.util
from pathlib import Path

def find_flask_admin_base_path():
    """查找 Flask-Admin base.py 文件路径"""
    try:
        import flask_admin
        base_path = os.path.join(os.path.dirname(flask_admin.__file__), 'base.py')
        return base_path
    except ImportError:
        print("无法导入 flask_admin 模块")
        return None

def patch_flask_admin():
    """修补 Flask-Admin 的 _run_view 方法"""
    base_path = find_flask_admin_base_path()
    if not base_path or not os.path.exists(base_path):
        print(f"找不到 Flask-Admin base.py 文件: {base_path}")
        return False
    
    # 读取原始文件
    with open(base_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 备份原始文件
    backup_path = base_path + '.bak'
    if not os.path.exists(backup_path):
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"已备份原始文件到: {backup_path}")
    
    # 查找并替换有问题的代码
    if 'return fn(cls=self, **kwargs)' in content:
        patched_content = content.replace(
            'return fn(cls=self, **kwargs)',
            'return fn(self, **kwargs) if "cls" not in fn.__code__.co_varnames else fn(cls=self, **kwargs)'
        )
        
        # 写入修补后的文件
        with open(base_path, 'w', encoding='utf-8') as f:
            f.write(patched_content)
        
        print(f"成功修补 Flask-Admin base.py 文件: {base_path}")
        return True
    else:
        print("未找到需要修补的代码行")
        return False

if __name__ == "__main__":
    success = patch_flask_admin()
    if success:
        print("修补成功！请重启应用程序。")
    else:
        print("修补失败！") 