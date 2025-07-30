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

- Python 3.11.3
- pip
- MySQL数据库服务器

### 安装步骤

1. 克隆或下载项目到本地

```bash
git clone git@github.com:lmq25913/project_a.git
git clone https://github.com/lmq25913/project_a.git
```

2. 创建并激活虚拟环境

```bash
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

4. 连接到现有数据库

本项目已配置为连接到MySQL数据库code2025，使用以下连接信息：
- 数据库：code2025
- 用户名：root
- 密码：l2669906091
- 主机：localhost

可以通过以下命令测试数据库连接：

```bash
python init_users.py
```

5. 运行应用

```bash
python app.py
```

应用将在 http://127.0.0.1:5000/ 启动

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

## 项目结构

- `app.py` - 主应用文件
- `models.py` - 数据库模型
- `config.py` - 配置文件
- `init_users.py` - 数据库连接测试脚本
- `templates/` - HTML模板 