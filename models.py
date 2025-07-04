"""
数据模型定义
包含设备、维护记录、去向记录、用户、通知等表结构
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class Equipment(db.Model):
    """
    设备信息表
    """
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False)  # 设备编号
    name = db.Column(db.String(128), nullable=False)  # 设备名称
    model = db.Column(db.String(64))  # 型号
    purchase_date = db.Column(db.Date)
    price = db.Column(db.Float)
    department = db.Column(db.String(64))
    status = db.Column(db.String(16), default='可用')  # 可用、维修中、报废
    maintenances = db.relationship('Maintenance', backref='equipment', lazy=True)
    usages = db.relationship('Usage', backref='equipment', lazy=True)

class Maintenance(db.Model):
    """
    维护周期记录表
    """
    id = db.Column(db.Integer, primary_key=True)
    equipment_id = db.Column(db.Integer, db.ForeignKey('equipment.id'), nullable=False)
    last_maintenance = db.Column(db.Date)
    next_maintenance = db.Column(db.Date)
    content = db.Column(db.String(256))
    responsible = db.Column(db.String(64))

class Usage(db.Model):
    """
    设备去向记录表
    """
    id = db.Column(db.Integer, primary_key=True)
    equipment_id = db.Column(db.Integer, db.ForeignKey('equipment.id'), nullable=False)
    borrower = db.Column(db.String(64))
    borrow_time = db.Column(db.DateTime, default=datetime.utcnow)
    expected_return_time = db.Column(db.DateTime)
    actual_return_time = db.Column(db.DateTime)
    remark = db.Column(db.String(256))

class User(db.Model, UserMixin):
    """
    用户表
    """
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(16), default='user')  # user/admin

class Notification(db.Model):
    """
    通知与提醒表
    """
    id = db.Column(db.Integer, primary_key=True)
    equipment_id = db.Column(db.Integer, db.ForeignKey('equipment.id'))
    equipment = db.relationship('Equipment', backref='notifications', lazy=True)
    type = db.Column(db.String(32))  # 提醒类型
    send_time = db.Column(db.DateTime, default=datetime.utcnow)
    receiver = db.Column(db.String(64))
    is_read = db.Column(db.Boolean, default=False)  # 是否已读
    is_deleted = db.Column(db.Boolean, default=False)  # 是否删除 