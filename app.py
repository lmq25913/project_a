"""
实验室仪器设备管理系统主入口
使用 Flask 框架
"""

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from flask_admin import Admin, BaseView, expose
from apscheduler.schedulers.background import BackgroundScheduler
from flask_migrate import Migrate
from flask_admin.contrib.sqla import ModelView
from models import db, Equipment, Maintenance, Usage, User, Notification
from flask_admin.form import rules, SecureForm
from wtforms.validators import ValidationError
from werkzeug.security import generate_password_hash, check_password_hash
from wtforms import PasswordField, SelectField
from datetime import datetime, timedelta
from flask import abort
from flask_babel import Babel
from functools import wraps
import requests

# 初始化 Flask 应用
app = Flask(__name__)
app.config.from_object('config.Config')
app.config['BABEL_DEFAULT_LOCALE'] = 'zh_Hans_CN'
babel = Babel(app)

db.init_app(app)
login_manager = LoginManager(app)
mail = Mail(app)
admin = Admin(app, name='设备管理系统', template_mode='bootstrap3')
scheduler = BackgroundScheduler()
migrate = Migrate(app, db)

class AdminAccessibleModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.role == 'admin'
    def inaccessible_callback(self, name, **kwargs):
        return abort(403)

class EquipmentModelView(AdminAccessibleModelView, ModelView):
    """
    设备信息管理自定义后台
    """
    column_list = ('code', 'name', 'model', 'purchase_date', 'price', 'department', 'status')
    column_searchable_list = ('code', 'name', 'model', 'department')
    column_filters = ('status', 'department')
    form_columns = ('code', 'name', 'model', 'purchase_date', 'price', 'department', 'status')
    column_labels = {
        'code': '设备编号',
        'name': '设备名称',
        'model': '型号',
        'purchase_date': '购置日期',
        'price': '价格',
        'department': '所属部门',
        'status': '状态'
    }
    def validate_code(self, form, field):
        if self.session.query(self.model).filter_by(code=field.data).first():
            raise ValidationError('设备编号已存在，请输入唯一编号。')

class MaintenanceModelView(AdminAccessibleModelView, ModelView):
    """
    维护记录管理自定义后台
    """
    column_list = ('equipment_id', 'last_maintenance', 'next_maintenance', 'content', 'responsible')
    column_labels = {
        'equipment_id': '设备',
        'last_maintenance': '最近维护日期',
        'next_maintenance': '下次维护日期',
        'content': '维护内容',
        'responsible': '责任人'
    }
    form_columns = ('equipment_id', 'last_maintenance', 'next_maintenance', 'content', 'responsible')

class UsageModelView(AdminAccessibleModelView, ModelView):
    """
    设备去向记录自定义后台
    """
    column_list = ('equipment_id', 'borrower', 'borrow_time', 'expected_return_time', 'actual_return_time', 'remark')
    column_labels = {
        'equipment_id': '设备',
        'borrower': '借用人',
        'borrow_time': '借用时间',
        'expected_return_time': '预计归还时间',
        'actual_return_time': '实际归还时间',
        'remark': '备注'
    }
    form_columns = ('equipment_id', 'borrower', 'borrow_time', 'expected_return_time', 'actual_return_time', 'remark')
    def on_model_change(self, form, model, is_created):
        if model.actual_return_time and model.equipment_id:
            equipment = Equipment.query.get(model.equipment_id)
            if equipment:
                equipment.status = '可用'
                from app import db
                db.session.commit()

class UserModelView(AdminAccessibleModelView, ModelView):
    """
    用户管理自定义后台
    """
    column_list = ('username', 'role')
    column_labels = {'username': '用户名', 'role': '角色'}
    form_columns = ('username', 'password', 'role')
    def on_model_change(self, form, model, is_created):
        if form.password.data:
            model.password = generate_password_hash(form.password.data)
        elif is_created:
            raise ValidationError('必须设置密码')
    column_exclude_list = ('password',)
    form_excluded_columns = ('password',)

class NotificationModelView(ModelView):
    column_labels = {
        'type': '类型',
        'send_time': '发送时间',
        'receiver': '接收人'
    }

def admin_required(f):
    """
    仅允许管理员访问的视图装饰器。
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('无权限访问该页面', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def user_required(f):
    """
    仅允许普通用户访问的视图装饰器。
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'user':
            flash('无权限访问该页面', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

class ReportView(BaseView):
    @expose('/')
    @admin_required
    @login_required
    def index(self):
        # 获取统计数据
        equipment_status = self.get_json('/admin/report/equipment_status')
        maintenance_due = self.get_json('/admin/report/maintenance_due')
        borrow_overdue = self.get_json('/admin/report/borrow_overdue')
        usage_rate = self.get_json('/admin/report/usage_rate')
        return self.render('admin/report.html',
                          equipment_status=equipment_status,
                          maintenance_due=maintenance_due,
                          borrow_overdue=borrow_overdue,
                          usage_rate=usage_rate)

    def get_json(self, endpoint):
        from flask import request as flask_request
        url = flask_request.host_url.rstrip('/') + endpoint
        cookies = flask_request.cookies
        headers = {'Cookie': '; '.join([f'{k}={v}' for k, v in cookies.items()])}
        try:
            resp = requests.get(url, headers=headers, timeout=5)
            return resp.json() if resp.status_code == 200 else {}
        except Exception:
            return {}

# 注册管理后台模型
admin.add_view(EquipmentModelView(Equipment, db.session, name='设备信息'))
admin.add_view(MaintenanceModelView(Maintenance, db.session, name='维护记录'))
admin.add_view(UsageModelView(Usage, db.session, name='去向记录'))
admin.add_view(UserModelView(User, db.session, name='用户'))
admin.add_view(NotificationModelView(Notification, db.session, name='通知'))
admin.add_view(ReportView(name='统计报表', endpoint='report'))

# 示例路由
@app.route('/')
def index():
    return redirect(url_for('login'))

# 用户加载回调
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# 登录路由
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('登录成功', 'success')
            # 登录后根据角色跳转
            if user.role == 'admin':
                return redirect(url_for('admin.index'))
            else:
                return redirect(url_for('user_index'))
        else:
            flash('用户名或密码错误', 'danger')
    return render_template('login.html')

# 登出路由
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已退出登录', 'info')
    return redirect(url_for('login'))

@app.route('/user')
@user_required
@login_required
def user_index():
    if current_user.role != 'user':
        return redirect(url_for('admin.index'))
    from models import Equipment
    status = request.args.get('status', '')
    q = request.args.get('q', '').strip()
    query = Equipment.query
    if status:
        query = query.filter_by(status=status)
    if q:
        query = query.filter((Equipment.name.contains(q)) | (Equipment.code.contains(q)))
    equipments = query.all()
    return render_template('user_index.html', equipments=equipments, status=status, q=q)

@app.route('/user/borrow/<int:equipment_id>', methods=['GET', 'POST'])
@user_required
@login_required
def user_borrow(equipment_id):
    if current_user.role != 'user':
        return redirect(url_for('admin.index'))
    from models import Equipment, Usage, db
    equipment = Equipment.query.get_or_404(equipment_id)
    if equipment.status != '可用':
        flash('该设备当前不可借用！', 'danger')
        return redirect(url_for('user_index'))
    from datetime import datetime
    now = datetime.now().strftime('%Y-%m-%dT%H:%M')
    if request.method == 'POST':
        borrow_time = request.form['borrow_time']
        expected_return_time = request.form['expected_return_time']
        remark = request.form.get('remark', '')
        usage = Usage(
            equipment_id=equipment.id,
            borrower=current_user.username,
            borrow_time=datetime.fromisoformat(borrow_time),
            expected_return_time=datetime.fromisoformat(expected_return_time),
            remark=remark
        )
        equipment.status = '借出'
        db.session.add(usage)
        db.session.commit()
        flash('借用申请已提交！', 'success')
        return redirect(url_for('user_index'))
    return render_template('user_borrow.html', equipment=equipment, now=now)

@app.route('/user/records')
@user_required
@login_required
def user_borrow_records():
    if current_user.role != 'user':
        return redirect(url_for('admin.index'))
    from models import Usage, Equipment
    page = int(request.args.get('page', 1))
    per_page = 10
    query = Usage.query.filter_by(borrower=current_user.username)
    total = query.count()
    records = query.order_by(Usage.borrow_time.desc()).offset((page-1)*per_page).limit(per_page).all()
    for r in records:
        r.equipment = Equipment.query.get(r.equipment_id)
    total_pages = (total + per_page - 1) // per_page
    return render_template('user_borrow_records.html', records=records, page=page, total_pages=total_pages)

@app.route('/user/return/<int:usage_id>', methods=['POST'])
@user_required
@login_required
def user_return(usage_id):
    if current_user.role != 'user':
        return redirect(url_for('admin.index'))
    from models import Usage, Equipment, db
    from datetime import datetime
    usage = Usage.query.get_or_404(usage_id)
    if usage.borrower != current_user.username or usage.actual_return_time:
        flash('无权归还或已归还！', 'danger')
        return redirect(url_for('user_borrow_records'))
    usage.actual_return_time = datetime.now()
    equipment = Equipment.query.get(usage.equipment_id)
    if equipment:
        equipment.status = '可用'
    db.session.commit()
    # 消息提醒（可扩展为邮件通知）
    flash(f'设备 {equipment.name} 已归还，感谢您的配合！', 'success')
    return redirect(url_for('user_borrow_records'))

@app.route('/user/notifications')
@user_required
@login_required
def user_notifications():
    """
    消息中心页面，支持分页、已读高亮、删除
    """
    from models import Notification, Equipment, db
    from flask import render_template, request, redirect, url_for, flash
    page = int(request.args.get('page', 1))
    per_page = 10
    query = Notification.query.filter_by(receiver=current_user.username, is_deleted=False).order_by(Notification.send_time.desc())
    total = query.count()
    notifications = query.offset((page-1)*per_page).limit(per_page).all()
    # 标记本页消息为已读
    for n in notifications:
        if not n.is_read:
            n.is_read = True
    db.session.commit()
    notif_list = []
    for n in notifications:
        notif_list.append({
            'id': n.id,
            '类型': n.type,
            '设备名称': n.equipment.name if n.equipment else '',
            '发送时间': n.send_time.strftime('%Y-%m-%d %H:%M'),
            '内容': f"{n.type} - {n.equipment.name if n.equipment else ''}",
            '已读': n.is_read
        })
    return render_template('user_notifications.html', notifications=notif_list, page=page, total_pages=(total+per_page-1)//per_page)

@app.route('/user/notifications/delete/<int:notification_id>', methods=['POST'])
@user_required
@login_required
def delete_notification(notification_id):
    from models import Notification, db
    from flask import abort, redirect, url_for, flash, request
    n = Notification.query.get_or_404(notification_id)
    if n.receiver != current_user.username:
        abort(403)
    n.is_deleted = True
    db.session.commit()
    flash('消息已删除', 'success')
    # 保持在当前页
    page = request.args.get('page', 1)
    return redirect(url_for('user_notifications', page=page))

def send_email(subject, recipients, body, html=None):
    """
    发送邮件辅助函数
    :param subject: 邮件主题
    :param recipients: 收件人列表
    :param body: 邮件正文（纯文本）
    :param html: 邮件正文（HTML，可选）
    """
    msg = Message(subject=subject, recipients=recipients, body=body, html=html)
    mail.send(msg)

def send_maintenance_reminders():
    """
    维护到期前7天提醒责任人
    """
    today = datetime.today().date()
    upcoming = today + timedelta(days=7)
    maintenances = Maintenance.query.filter(Maintenance.next_maintenance == upcoming).all()
    for m in maintenances:
        if m.responsible:
            subject = f"设备维护提醒：{m.equipment.name}"
            body = f"设备 {m.equipment.name}（编号：{m.equipment.code}）将在 {m.next_maintenance} 需要维护，请及时处理。"
            # 这里假设责任人邮箱为"责任人名@domain.com"，实际应从用户表查找
            send_email(subject, [f"{m.responsible}@domain.com"], body)

def send_overdue_borrow_reminders():
    """
    设备借用超期1天提醒借用人
    """
    today = datetime.today()
    overdues = Usage.query.filter(
        Usage.expected_return_time < today,
        Usage.actual_return_time == None
    ).all()
    for u in overdues:
        # 只提醒超期1天的
        if (today - u.expected_return_time).days == 1 and u.borrower:
            subject = f"设备归还超时提醒：{u.equipment.name}"
            body = f"您借用的设备 {u.equipment.name}（编号：{u.equipment.code}）已超期，请尽快归还。"
            # 假设借用人邮箱为"用户名@domain.com"，实际应从用户表查找
            send_email(subject, [f"{u.borrower}@domain.com"], body)

# 定时任务：每天凌晨1点执行提醒
scheduler.add_job(send_maintenance_reminders, 'cron', hour=1, id='maintenance_reminder')
scheduler.add_job(send_overdue_borrow_reminders, 'cron', hour=1, id='overdue_borrow_reminder')

scheduler.start()

@app.route('/admin/report/equipment_status')
@admin_required
@login_required
def report_equipment_status():
    """
    设备状态统计：返回各状态设备数量
    """
    from models import Equipment
    from flask import jsonify
    status_counts = (
        Equipment.query.with_entities(Equipment.status, db.func.count(Equipment.id))
        .group_by(Equipment.status).all()
    )
    result = {status: count for status, count in status_counts}
    return jsonify(result)

@app.route('/admin/report/maintenance_due')
@admin_required
@login_required
def report_maintenance_due():
    """
    维护到期统计：返回未来7天内需要维护的设备
    """
    from models import Maintenance, Equipment
    from flask import jsonify
    from datetime import datetime, timedelta
    today = datetime.today().date()
    upcoming = today + timedelta(days=7)
    due_maintenances = Maintenance.query.filter(
        Maintenance.next_maintenance >= today,
        Maintenance.next_maintenance <= upcoming
    ).all()
    result = [
        {
            '设备名称': m.equipment.name if m.equipment else '',
            '设备编号': m.equipment.code if m.equipment else '',
            '下次维护日期': m.next_maintenance.strftime('%Y-%m-%d'),
            '责任人': m.responsible
        }
        for m in due_maintenances
    ]
    return jsonify(result)

@app.route('/admin/report/borrow_overdue')
@admin_required
@login_required
def report_borrow_overdue():
    """
    借用超期统计：返回所有超期未归还的设备
    """
    from models import Usage, Equipment
    from flask import jsonify
    from datetime import datetime
    today = datetime.now()
    overdues = Usage.query.filter(
        Usage.expected_return_time < today,
        Usage.actual_return_time == None
    ).all()
    result = [
        {
            '设备名称': u.equipment.name if u.equipment else '',
            '设备编号': u.equipment.code if u.equipment else '',
            '借用人': u.borrower,
            '预计归还时间': u.expected_return_time.strftime('%Y-%m-%d %H:%M'),
        }
        for u in overdues
    ]
    return jsonify(result)

@app.route('/admin/report/usage_rate')
@admin_required
@login_required
def report_usage_rate():
    """
    设备使用率统计：返回每台设备的使用率（总借用时长/设备存在时长）
    """
    from models import Equipment, Usage
    from flask import jsonify
    from datetime import datetime, timedelta
    
    result = []
    equipments = Equipment.query.all()
    
    for eq in equipments:
        # 获取设备的所有使用记录
        usages = Usage.query.filter_by(equipment_id=eq.id).all()
        
        # 计算总借用时间（秒）
        total_borrow_seconds = 0
        for u in usages:
            try:
                # 如果已归还，计算实际借用时间
                if u.actual_return_time and u.borrow_time:
                    total_borrow_seconds += (u.actual_return_time - u.borrow_time).total_seconds()
                # 如果未归还但有借用时间，计算到现在的时间
                elif u.borrow_time:
                    total_borrow_seconds += (datetime.now() - u.borrow_time).total_seconds()
            except Exception as e:
                # 如果计算出错，记录日志但继续处理
                print(f"计算设备 {eq.name} 的使用时间时出错: {str(e)}")
                continue
        
        # 计算设备存在时间（秒）
        try:
            # 如果有购买日期，使用购买日期计算
            if eq.purchase_date:
                exist_seconds = (datetime.now() - eq.purchase_date).total_seconds()
            else:
                # 如果没有购买日期，默认使用一个较长时间（如30天）
                exist_seconds = timedelta(days=30).total_seconds()
        except Exception as e:
            # 如果计算出错，使用默认值
            print(f"计算设备 {eq.name} 的存在时间时出错: {str(e)}")
            exist_seconds = timedelta(days=30).total_seconds()
        
        # 计算使用率，确保不会除以零
        if exist_seconds > 0:
            usage_rate = total_borrow_seconds / exist_seconds
        else:
            usage_rate = 0
            
        # 添加到结果中，确保格式正确
        result.append({
            '设备名称': eq.name,
            '设备编号': eq.code,
            '使用率': f'{usage_rate:.2%}'  # 格式化为百分比，如 12.34%
        })
    
    # 如果没有数据，添加一个提示
    if not result:
        result.append({
            '设备名称': '暂无数据',
            '设备编号': '-',
            '使用率': '0.00%'
        })
        
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True) 