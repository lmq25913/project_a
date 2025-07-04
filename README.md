# 设备管理系统

这是一个基于Flask的设备管理系统，用于管理设备借用、维护和通知。

## 功能特点

- 用户认证与授权（管理员/普通用户）
- 设备借用与归还
- 设备维护记录
- 通知系统
- 使用记录统计

## 安装指南

### 前置要求

- Python 3.8+
- pip

### 安装步骤

1. 克隆或下载项目到本地

git clone git@github.com:lmq25913/project_a.git
git clone https://github.com/lmq25913/project_a.git

2. 创建并激活虚拟环境

```bash
# 安装virtualenv（如果尚未安装）
pip install virtualenv

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/Mac:
# source venv/bin/activate
```

3. 安装依赖包

```bash
pip install -r requirements.txt
```

4. 初始化数据库

```bash
# 应用数据库迁移
flask db upgrade

# 或者手动创建数据库表
flask shell
>>> from models import db
>>> db.create_all()
>>> exit()

# 初始化用户数据
python init_users.py
```

5. 运行应用

```bash
flask run
```

应用将在 http://127.0.0.1:5000/ 启动

## 初始账户

- 管理员账户: admin / password
- 普通用户: user / password

## 使用指南

1. 使用提供的账户登录系统
2. 管理员可以:
   - 添加、编辑和删除设备
   - 查看所有借用记录
   - 管理用户
   - 查看统计报告
   - 发送通知
3. 普通用户可以:
   - 浏览可用设备
   - 借用和归还设备
   - 查看个人借用历史
   - 接收通知

## 数据导入

系统支持从CSV文件导入数据:
- sample_users.csv - 用户数据
- sample_equipments.csv - 设备数据
- sample_maintenances.csv - 维护记录
- sample_usages.csv - 使用记录
- sample_notifications.csv - 通知数据

## 项目结构

- `app.py` - 主应用文件
- `models.py` - 数据库模型
- `config.py` - 配置文件
- `init_users.py` - 初始化用户脚本
- `migrations/` - 数据库迁移文件
- `templates/` - HTML模板 