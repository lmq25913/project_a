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
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///lab_equipment.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # 邮件配置（可根据实际情况修改）
    MAIL_SERVER = 'smtp.example.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') 