"""
数据库初始化脚本：创建表、管理员、普通用户和样例设备，支持批量导入
运行方法：python init_users.py
"""
import csv
from models import db, User, Equipment, Maintenance, Usage, Notification
from werkzeug.security import generate_password_hash
from app import app
from datetime import date, datetime

def parse_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

with app.app_context():
    # 创建所有表
    db.create_all()
    # 初始化管理员
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password=generate_password_hash('123456'), role='admin')
        db.session.add(admin)
    # 初始化普通用户
    if not User.query.filter_by(username='user').first():
        user = User(username='user', password=generate_password_hash('123456'), role='user')
        db.session.add(user)
    # 初始化样例设备
    if not Equipment.query.filter_by(code='EQ001').first():
        eq1 = Equipment(code='EQ001', name='高精度电子天平', model='TP-100', purchase_date=date(2022,1,10), price=3500, department='化学', status='可用')
        db.session.add(eq1)
    if not Equipment.query.filter_by(code='EQ002').first():
        eq2 = Equipment(code='EQ002', name='紫外分光光度计', model='UV-9000', purchase_date=date(2021,5,20), price=12000, department='生物', status='可用')
        db.session.add(eq2)
    # 批量导入CSV设备
    try:
        with open('sample_equipments.csv', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not Equipment.query.filter_by(code=row['code']).first():
                    eq = Equipment(
                        code=row['code'],
                        name=row['name'],
                        model=row['model'],
                        purchase_date=parse_date(row['purchase_date']),
                        price=float(row['price']),
                        department=row['department'],
                        status=row['status']
                    )
                    db.session.add(eq)
        print('已批量导入 sample_equipments.csv 中的设备数据')
    except FileNotFoundError:
        print('未检测到 sample_equipments.csv，跳过批量导入')
    # 批量导入用户
    try:
        with open('sample_users.csv', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not User.query.filter_by(username=row['username']).first():
                    user = User(
                        username=row['username'],
                        password=generate_password_hash(row['password']),
                        role=row['role']
                    )
                    db.session.add(user)
        print('已批量导入 sample_users.csv 中的用户数据')
    except FileNotFoundError:
        print('未检测到 sample_users.csv，跳过用户批量导入')
    # 批量导入维护记录
    try:
        with open('sample_maintenances.csv', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                eq = Equipment.query.filter_by(code=row['equipment_code']).first()
                if eq:
                    last_maintenance = parse_date(row['last_maintenance'])
                    next_maintenance = parse_date(row['next_maintenance'])
                    m = Maintenance(
                        equipment_id=eq.id,
                        last_maintenance=last_maintenance,
                        next_maintenance=next_maintenance,
                        content=row['content'],
                        responsible=row['responsible']
                    )
                    db.session.add(m)
        print('已批量导入 sample_maintenances.csv 中的维护记录')
    except FileNotFoundError:
        print('未检测到 sample_maintenances.csv，跳过维护记录批量导入')
    # 批量导入借用记录
    try:
        with open('sample_usages.csv', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                eq = Equipment.query.filter_by(code=row['equipment_code']).first()
                user = User.query.filter_by(username=row['borrower']).first()
                if eq and user:
                    borrow_time = datetime.strptime(row['borrow_time'], "%Y-%m-%d %H:%M")
                    expected_return_time = datetime.strptime(row['expected_return_time'], "%Y-%m-%d %H:%M")
                    actual_return_time = datetime.strptime(row['actual_return_time'], "%Y-%m-%d %H:%M") if row['actual_return_time'] else None
                    usage = Usage(
                        equipment_id=eq.id,
                        borrower=row['borrower'],
                        borrow_time=borrow_time,
                        expected_return_time=expected_return_time,
                        actual_return_time=actual_return_time,
                        remark=row['remark']
                    )
                    db.session.add(usage)
        print('已批量导入 sample_usages.csv 中的借用记录')
    except FileNotFoundError:
        print('未检测到 sample_usages.csv，跳过借用记录批量导入')
    # 批量导入通知
    try:
        with open('sample_notifications.csv', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                eq = Equipment.query.filter_by(code=row['equipment_code']).first()
                if eq:
                    send_time = datetime.strptime(row['send_time'], "%Y-%m-%d %H:%M")
                    is_read = row['is_read'].strip().lower() == 'true'
                    notification = Notification(
                        equipment_id=eq.id,
                        type=row['type'],
                        send_time=send_time,
                        receiver=row['receiver'],
                        is_read=is_read
                    )
                    db.session.add(notification)
        print('已批量导入 sample_notifications.csv 中的通知')
    except FileNotFoundError:
        print('未检测到 sample_notifications.csv，跳过通知批量导入')
    db.session.commit()
    print('初始化完成：管理员(admin/123456)、普通用户(user/123456)、样例设备(EQ001/EQ002/CSV批量)') 