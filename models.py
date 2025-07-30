"""
数据模型定义
根据code2025数据库中的表结构修改
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class Admin(db.Model):
    """
    管理员表
    """
    __tablename__ = 'admin'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))  # 管理员姓名
    username = db.Column(db.String(255))  # 用户名
    password = db.Column(db.String(255))  # 密码
    email = db.Column(db.String(255))  # 邮箱
    phone = db.Column(db.String(255))  # 手机号
    
    def __init__(self, username=None, password=None, name=None, email=None, phone=None):
        self.username = username
        self.password = password
        self.name = name
        self.email = email
        self.phone = phone

class Category(db.Model):
    """
    分类表，用于设备所属部门
    """
    __tablename__ = 'category'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255))  # 分类名称/部门名称
    # 移除不存在的字段

class Equipment(db.Model):
    """
    设备信息表
    """
    __tablename__ = 'equipment'
    id = db.Column(db.Integer, primary_key=True)
    img = db.Column(db.LargeBinary(length=(2**32)-1))  # 使用LONGBLOB类型存储图片二进制数据
    name = db.Column(db.String(255), nullable=False)  # 设备名称
    number = db.Column(db.String(255))  # 设备编号
    model = db.Column(db.String(255))  # 型号
    department = db.Column(db.String(255))  # 所属部门
    purchase_date = db.Column(db.String(255))  # 购置日期
    price = db.Column(db.String(255))  # 价格
    num = db.Column(db.Integer)  # 数量
    status = db.Column(db.String(255), default='可用')  # 状态：可用、借用中、报废中
    review_status = db.Column(db.String(255))  # 审核状态
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))  # 分类ID，外键关联到category表
    sort = db.Column(db.String(255))  # 排序
    principal = db.Column(db.String(255))  # 负责人
    
    # 关系
    category = db.relationship('Category', foreign_keys=[category_id])

class Maintenance(db.Model):
    """
    维护记录表
    """
    __tablename__ = 'maintenance'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))  # 维护名称
    number = db.Column(db.String(255))  # 维护编号
    last_date = db.Column(db.String(255))  # 上次维护日期
    next_date = db.Column(db.String(255))  # 下次维护日期
    content = db.Column(db.String(255))  # 维护内容
    admin_id = db.Column(db.Integer)  # 管理员ID

class User(db.Model, UserMixin):
    """
    用户表
    """
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255))
    phone = db.Column(db.String(255))
    email = db.Column(db.String(255))
    role = db.Column(db.String(255), default='USER')  # 用户角色，使用大写
    avatar = db.Column(db.String(255))  # 头像

class BorrowList(db.Model):
    """
    借用记录表
    """
    __tablename__ = 'borrowlist'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))  # 借用名称
    number = db.Column(db.String(255))  # 借用编号
    borrow_time = db.Column(db.String(255))  # 借用时间
    return_time = db.Column(db.String(255))  # 归还时间
    content = db.Column(db.String(255))  # 内容/说明
    status = db.Column(db.String(255))  # 状态
    reason = db.Column(db.String(255))  # 拒绝原因
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # 用户ID
    
    # 关系
    user = db.relationship('User', backref='borrow_records')

class ReturnList(db.Model):
    """
    归还记录表
    """
    __tablename__ = 'returnlist'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))  # 归还名称
    number = db.Column(db.String(255))  # 归还编号
    date = db.Column(db.String(255))  # 归还日期
    status = db.Column(db.String(255))  # 状态
    reason = db.Column(db.String(255))  # 原因
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # 用户ID
    
    # 关系
    user = db.relationship('User', backref='return_records')

class Notice(db.Model):
    """
    通知表
    """
    __tablename__ = 'notice'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255))  # 通知标题
    content = db.Column(db.String(255))  # 通知内容
    time = db.Column(db.String(255))  # 时间

class UserNotice(db.Model):
    """
    用户通知表
    """
    __tablename__ = 'usernotice'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(255))  # 通知内容
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # 用户ID
    record_id = db.Column(db.Integer)  # 相关记录ID
    equipment_id = db.Column(db.Integer, db.ForeignKey('equipment.id'))  # 设备ID
    
    # 关系
    user = db.relationship('User', backref='notifications')
    equipment = db.relationship('Equipment', backref='user_notices') 