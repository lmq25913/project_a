"""
Flask 配置文件
包含数据库、邮件等基础配置
"""

import os

class Config:
    """
    Flask 应用基础配置
    """
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')
    # 修改为MySQL数据库连接，添加字符集参数
    SQLALCHEMY_DATABASE_URI = 'mysql+mysqlconnector://root:l2669906091@localhost/code2025?charset=utf8mb4'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # 邮件配置（可根据实际情况修改）
    MAIL_SERVER = 'smtp.example.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    
    # 文件上传配置
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}