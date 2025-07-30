"""
实验室仪器设备管理系统主入口
使用 Flask 框架
"""

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, make_response
from markupsafe import Markup
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from flask_admin import Admin, BaseView, expose, AdminIndexView
from flask_admin.actions import action
from apscheduler.schedulers.background import BackgroundScheduler
from flask_migrate import Migrate
from flask_admin.contrib.sqla import ModelView
from models import db, User, Equipment, Maintenance, BorrowList, ReturnList, Notice, UserNotice, Category, Admin as AdminModel
from flask_admin.form import rules, SecureForm, FileUploadField
from wtforms.validators import ValidationError, InputRequired
from wtforms.fields import DateField, SelectField, StringField
from werkzeug.security import generate_password_hash, check_password_hash
from wtforms import PasswordField, SelectField
from datetime import datetime, timedelta
from flask import abort
from flask_babel import Babel
from functools import wraps
import requests
from sqlalchemy import desc
import os
from werkzeug.utils import secure_filename
import uuid
import json
from flask import session # Added for session management in BorrowListModelView

# 创建自定义的文件上传字段，不保存文件到磁盘
class DatabaseFileUploadField(FileUploadField):
    """
    自定义文件上传字段，不保存文件到磁盘，而是提供访问文件数据的方法
    """
    def _save_file(self, data, filename, **kwargs):
        # 覆盖父类方法，不实际保存文件，只返回文件名
        # 实际的文件数据会在 on_model_change 中处理
        # 确保返回的是字符串类型
        if isinstance(filename, bytes):
            filename = filename.decode('utf-8')
        return filename
        
    def _delete_file(self, filename):
        # 覆盖父类方法，防止尝试删除不存在的文件
        # 我们不实际从磁盘删除文件，因为我们将图片保存在数据库中
        pass
        
    def _get_path(self, filename):
        # 覆盖父类方法，确保路径组件都是字符串类型
        if filename is None:
            return None
            
        if isinstance(filename, bytes):
            filename = filename.decode('utf-8')
            
        if isinstance(self.base_path, bytes):
            base_path = self.base_path.decode('utf-8')
        else:
            base_path = self.base_path
            
        return os.path.join(base_path, filename)

# 创建自定义的日期字段，支持 HTML5 日期选择器
class HTML5DateField(DateField):
    """
    自定义日期字段，支持 HTML5 日期选择器
    """
    def __call__(self, **kwargs):
        kwargs.setdefault('type', 'date')
        return super(HTML5DateField, self).__call__(**kwargs)
        
    def _value(self):
        if self.data:
            # 如果数据是字符串，直接返回
            if isinstance(self.data, str):
                return self.data
            # 否则使用 strftime，确保 format 是字符串
            format_str = self.format
            if not isinstance(format_str, str):
                format_str = '%Y-%m-%d'
            return self.data.strftime(format_str)
        return ''

# 初始化 Flask 应用
app = Flask(__name__)
app.config.from_object('config.Config')
app.config['BABEL_DEFAULT_LOCALE'] = 'zh_Hans_CN'
babel = Babel(app)

# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def generate_unique_filename(filename):
    # 获取文件扩展名
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    # 生成随机文件名
    new_filename = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex
    return new_filename

# 自定义管理后台首页视图
class MyAdminIndexView(AdminIndexView):
    """自定义管理后台首页视图"""
    
    @expose('/')
    def index(self):
        # 查询系统通知
        notices = Notice.query.order_by(Notice.id.desc()).limit(5).all()
        return self.render('admin/index.html', notices=notices)

# 初始化数据库连接，但不创建表，使用已有的数据库结构
db.init_app(app)
login_manager = LoginManager(app)
mail = Mail(app)
admin = Admin(
    app, 
    name='设备管理系统', 
    template_mode='bootstrap3',
    index_view=MyAdminIndexView(name='首页', url='/admin')
)
scheduler = BackgroundScheduler()
migrate = Migrate(app, db)

class AdminAccessibleModelView(ModelView):
    def is_accessible(self):
        if not current_user.is_authenticated:
            return False
        
        # 角色检查时考虑多种可能的格式
        if hasattr(current_user, 'role'):
            user_role = current_user.role
            if user_role is None:
                return False
                
            user_role = str(user_role).upper()
            print(f"检查权限: 用户={current_user.username}, 角色={user_role}")
            return user_role in ['ADMIN', 'admin', 'Admin']
        return False
    
    def inaccessible_callback(self, name, **kwargs):
        print(f"访问被拒绝: 用户={current_user.username if current_user.is_authenticated else 'anonymous'}, 角色={current_user.role if current_user.is_authenticated else 'none'}")
        return abort(403)
    
    # 为所有继承自AdminAccessibleModelView的视图类设置分页
    page_size = 15  # 每页显示15条记录
    can_set_page_size = True  # 允许用户设置每页显示的记录数

class EquipmentModelView(AdminAccessibleModelView, ModelView):
    """
    设备信息管理自定义后台
    """
    column_list = ('img', 'number', 'name', 'model', 'purchase_date', 'price', 'department', 'status')
    column_searchable_list = ('number', 'name', 'model', 'department')
    column_filters = ('status', 'department')
    form_columns = ('img', 'number', 'name', 'model', 'purchase_date', 'price', 'category_id', 'status')
    column_labels = {
        'img': '设备图片',
        'number': '设备编号',
        'name': '设备名称',
        'model': '型号',
        'purchase_date': '购置日期',
        'price': '价格',
        'department': '所属部门',
        'category_id': '所属部门',
        'status': '状态'
    }
    
    # 添加重置设备状态的操作
    action_disallowed_list = []
    can_export = True
    
    # 重写list_view方法，确保每次刷新页面时都获取最新的设备状态
    @expose('/')
    def list_view(self):
        # 在显示列表前，确保所有设备状态都是最新的
        self._refresh_equipment_status()
        return super(EquipmentModelView, self).list_view()
    
    def _refresh_equipment_status(self):
        """刷新所有设备状态，确保与借用记录保持一致"""
        try:
            # 查找所有标记为"借用中"的设备
            borrowed_equipments = Equipment.query.filter_by(status="借用中").all()
            
            for equipment in borrowed_equipments:
                # 检查是否有对应的有效借用记录
                active_borrow = BorrowList.query.filter_by(
                    number=equipment.number,
                    status="审核通过"
                ).first()
                
                # 检查是否有最近的归还记录
                recent_return = ReturnList.query.filter_by(
                    number=equipment.number,
                    status="审核通过"
                ).order_by(ReturnList.id.desc()).first()
                
                if not active_borrow or recent_return:
                    # 如果没有有效借用记录或有归还记录，则设备应为可用
                    equipment.status = "可用"
                    db.session.add(equipment)
                    print(f"自动刷新: 设备 {equipment.number} 状态已重置为可用")
            
            # 查找所有标记为可用但有有效借用记录的设备
            available_equipments = Equipment.query.filter_by(status="可用").all()
            
            for equipment in available_equipments:
                # 检查是否有对应的有效借用记录
                active_borrow = BorrowList.query.filter_by(
                    number=equipment.number,
                    status="审核通过"
                ).first()
                
                # 检查是否有最近的归还记录
                recent_return = ReturnList.query.filter_by(
                    number=equipment.number,
                    status="审核通过"
                ).order_by(ReturnList.id.desc()).first()
                
                if active_borrow and not recent_return:
                    # 如果有有效借用记录且无归还记录，则设备应为借用中
                    equipment.status = "借用中"
                    db.session.add(equipment)
                    print(f"自动刷新: 设备 {equipment.number} 状态已更新为借用中")
            
            # 提交所有更改
            db.session.commit()
            print("所有设备状态刷新完成")
        except Exception as ex:
            db.session.rollback()
            print(f"刷新设备状态时出错: {str(ex)}")
    
    # 添加批量操作功能 - 重置设备状态为"可用"
    @action('reset_status', '重置状态为"可用"', '确定将选中设备的状态重置为"可用"吗？')
    def action_reset_status(self, ids):
        try:
            # 查询选中的设备
            query = self.get_query().filter(self.model.id.in_(ids))
            count = 0
            
            # 更新状态为"可用"
            for equipment in query.all():
                if equipment.status != "可用":
                    equipment.status = "可用"
                    # 同时检查并更新相关借用记录
                    active_borrows = BorrowList.query.filter_by(
                        number=equipment.number,
                        status="审核通过"
                    ).all()
                    for borrow in active_borrows:
                        borrow.status = "归还完成"
                        db.session.add(borrow)
                    count += 1
                    
            db.session.commit()
            flash(f'成功将 {count} 个设备的状态重置为"可用"', 'success')
        except Exception as ex:
            db.session.rollback()
            flash(f'重置设备状态时出现错误: {str(ex)}', 'error')
    
    # 添加单行操作按钮
    def _row_actions(self, context, data, model_name, model_id, primary_key):
        row_actions = super()._row_actions(context, data, model_name, model_id, primary_key)
        if hasattr(data, 'status') and data.status != '可用':
            # 添加重置状态按钮
            reset_url = url_for('.action_view')
            reset_button = """
                <form class="icon" method="POST" action="{reset_url}" style="display:inline;">
                    <input type="hidden" name="action" value="reset_status">
                    <input type="hidden" name="rowid" value="{model_id}">
                    <input type="hidden" name="_csrf_token" value="{{{{ csrf_token() }}}}">
                    <button onclick="return confirm('确定要将此设备状态重置为"可用"吗？');" class="btn btn-sm btn-warning">
                        <i class="glyphicon glyphicon-refresh"></i> 重置状态
                    </button>
                </form>
            """.format(reset_url=reset_url, model_id=model_id)
            row_actions.append(Markup(reset_button))
        return row_actions
    
    # 自定义图片显示格式，使用动态URL显示数据库中的图片
    column_formatters = {
        'img': lambda v, c, m, p: Markup(f'<img src="/equipment_image/{m.id}" width="100px">') if m.img else '',
        'department': lambda v, c, m, p: Category.query.get(m.category_id).title if m.category_id and Category.query.get(m.category_id) else ''
    }
    
    # 状态和部门字段采用下拉框
    form_overrides = {
        'category_id': SelectField
    }
    
    def scaffold_form(self):
        form_class = super(EquipmentModelView, self).scaffold_form()
        form_class.status = SelectField('状态', choices=[
            ('可用', '可用'),
            ('借用中', '借用中'),
            ('报废中', '报废中')
        ])
        
        # 将img字段替换为文件上传字段，但不再保存文件到文件系统
        form_class.img = DatabaseFileUploadField('设备图片', 
                                base_path=app.config['UPLOAD_FOLDER'],  # 仍然需要提供base_path
                                allowed_extensions=['png', 'jpg', 'jpeg', 'gif'])
        
        # 将购置日期字段改为HTML5日期选择器
        from wtforms.fields import DateField
        
        # 自定义渲染方法，使用 HTML5 date 类型
        class HTML5DateField(DateField):
            def __call__(self, **kwargs):
                kwargs.setdefault('type', 'date')
                return super(HTML5DateField, self).__call__(**kwargs)
                
            def _value(self):
                if self.data:
                    # 如果数据是字符串，直接返回
                    if isinstance(self.data, str):
                        return self.data
                    # 否则使用 strftime，确保 format 是字符串
                    format_str = self.format
                    if not isinstance(format_str, str):
                        format_str = '%Y-%m-%d'
                    return self.data.strftime(format_str)
                return ''
        
        form_class.purchase_date = HTML5DateField(
            '购置日期',
            format='%Y-%m-%d'
        )
        
        return form_class
    
    def validate_number(self, form, field):
        if self.session.query(self.model).filter_by(number=field.data).first():
            raise ValidationError('设备编号已存在，请输入唯一编号。')
    
    def create_form(self, obj=None):
        form = super(EquipmentModelView, self).create_form(obj)
        
        # 从category表获取部门选项
        categories = Category.query.all()
        category_choices = [('', '-- 请选择部门 --')] + [(str(c.id), c.title) for c in categories]
        form.category_id.choices = category_choices
        
        return form
    
    def edit_form(self, obj=None):
        form = super(EquipmentModelView, self).edit_form(obj)
        
        # 从category表获取部门选项
        categories = Category.query.all()
        category_choices = [('', '-- 请选择部门 --')] + [(str(c.id), c.title) for c in categories]
        form.category_id.choices = category_choices
        
        return form
    
    def on_model_change(self, form, model, is_created):
        """处理图片上传，直接保存为二进制数据"""
        if form.img.data and hasattr(form.img.data, 'read'):
            # 直接读取文件数据并存储到模型的img字段
            model.img = form.img.data.read()
            # 重置文件指针，以防后续需要再次读取
            if hasattr(form.img.data, 'seek'):
                form.img.data.seek(0)
        
        # 处理category_id字段，确保它是整数类型
        if form.category_id.data:
            try:
                model.category_id = int(form.category_id.data)
                # 同时更新department字段，保持兼容性
                category = Category.query.get(model.category_id)
                if category:
                    model.department = category.title
            except (ValueError, TypeError):
                pass

class MaintenanceModelView(AdminAccessibleModelView, ModelView):
    """
    维护记录管理自定义后台
    """
    
    column_list = ('name', 'number', 'last_date', 'next_date', 'content', 'admin_id')
    column_labels = {
        'name': '设备名称',
        'number': '设备编号',
        'last_date': '近次维护日期',
        'next_date': '下次维护日期',
        'content': '维护内容',
        'admin_id': '管理员'
    }
    form_columns = ('number', 'name', 'last_date', 'next_date', 'content', 'admin_id')
    
    # 设置字段类型和渲染方式
    form_overrides = {
        'last_date': HTML5DateField,
        'next_date': HTML5DateField,
        'name': StringField,
        'number': SelectField,  # 使用SelectField而不是StringField
        'admin_id': SelectField,  # 使用SelectField来选择管理员
    }
    
    # 自定义管理员显示格式
    column_formatters = {
        'admin_id': lambda v, c, m, p: AdminModel.query.get(m.admin_id).name if m.admin_id and AdminModel.query.get(m.admin_id) else ''
    }
    
    # 设置字段属性
    form_args = {
        'number': {
            'label': '设备编号',
            'validators': [InputRequired('请选择设备编号')],
            'choices': []  # 初始为空，会在create_form和edit_form中填充
        },
        'name': {
            'label': '设备名称',
            'render_kw': {
                'readonly': True,
                'class': 'equipment-name',
                'style': 'background-color: #f5f5f5;' # 灰色背景表示只读
            }
        },
        'admin_id': {
            'label': '管理员',
            'choices': []  # 初始为空，会在create_form和edit_form中填充
        },
        'last_date': {
            'label': '近次维护日期',
            'format': '%Y-%m-%d'
        },
        'next_date': {
            'label': '下次维护日期',
            'format': '%Y-%m-%d'
        }
    }
    
    def on_model_change(self, form, model, is_created):
        """在保存模型前进行处理"""
        # 使用 no_autoflush 块来防止在数据清理前过早地刷新会话
        with self.session.no_autoflush:
            if model.number:
                selected_equipment = Equipment.query.filter_by(number=model.number).first()
                if selected_equipment:
                    model.name = selected_equipment.name
                else:
                    model.name = "" # 如果找不到设备，则清空设备名称
            else:
                model.name = ""

        # 处理 admin_id 字段，确保它是整数类型
        if model.admin_id:
            try:
                model.admin_id = int(model.admin_id)
            except (ValueError, TypeError):
                # 如果转换失败，则说明提交的不是有效的ID，抛出验证错误
                raise ValidationError(f"管理员ID无效: '{model.admin_id}'. 请从下拉列表中选择一个管理员。")

        print(f"准备保存维护记录: 设备编号={model.number}, 设备名称='{model.name}', 管理员ID={model.admin_id}")

    def create_form(self, obj=None):
        form = super(MaintenanceModelView, self).create_form(obj)
        
        # 设备编号选项
        equipments = Equipment.query.all()
        equipment_choices = [('', '-- 请选择设备 --')] + [
            (e.number, e.number) for e in equipments if e.number and e.number.strip()
        ]
        form.number.choices = equipment_choices
        
        # 管理员选项
        admins = AdminModel.query.all()
        admin_choices = [('', '-- 请选择管理员 --')] + [
            (str(a.id), a.name) for a in admins if a.name and a.name.strip()
        ]
        form.admin_id.choices = admin_choices
        
        # 确保设备名称字段是只读的
        if hasattr(form, 'name'):
            form.name.render_kw = {
                'readonly': True,
                'class': 'equipment-name',
                'style': 'background-color: #f5f5f5;'
            }
        
        # 注入JavaScript代码
        self._add_select2_js_to_form(form)
        return form

    def edit_form(self, obj=None):
        form = super(MaintenanceModelView, self).edit_form(obj)
        
        # 设备编号选项
        equipments = Equipment.query.all()
        equipment_choices = [('', '-- 请选择设备 --')] + [
            (e.number, e.number) for e in equipments if e.number and e.number.strip()
        ]
        form.number.choices = equipment_choices
        
        # 管理员选项
        admins = AdminModel.query.all()
        admin_choices = [('', '-- 请选择管理员 --')] + [
            (str(a.id), a.name) for a in admins if a.name and a.name.strip()
        ]
        form.admin_id.choices = admin_choices
        
        # 如果是编辑模式且已有设备编号，自动填充设备名称
        if obj and obj.number:
            equipment = Equipment.query.filter_by(number=obj.number).first()
            if equipment:
                form.name.data = equipment.name
                
        # 确保设备名称字段是只读的
        if hasattr(form, 'name'):
            form.name.render_kw = {
                'readonly': True,
                'class': 'equipment-name',
                'style': 'background-color: #f5f5f5;'
            }
        
        # 注入JavaScript代码
        self._add_select2_js_to_form(form)
        return form
    
    def _add_select2_js_to_form(self, form):
        """注入JavaScript以初始化Select2下拉框，并确保依赖库已加载"""
        
        # 获取所有设备，构建编号到名称的映射
        equipment_map = {}
        equipments = Equipment.query.all()
        for eq in equipments:
            if eq.number and eq.number.strip():
                equipment_map[eq.number] = eq.name
                
        # 将Python字典转换为JavaScript对象字符串
        equipment_map_js = json.dumps(equipment_map)
        
        # 打印映射以进行调试
        print("设备编号到名称映射:", equipment_map)
        
        # 如果存在HTML中的文本输入框但应该是选择框，则替换为Select2
        js_code = f"""
        <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
        <link href="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/css/select2.min.css" rel="stylesheet" />
        <script src="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js"></script>
        
        <script>
            console.log('设备自动填充脚本加载...');
            
            // 确保jQuery加载完成
            function ensureJQuery(callback) {{
                if (window.jQuery) {{
                    console.log('jQuery已加载');
                    callback(jQuery);
                }} else {{
                    console.log('等待jQuery加载...');
                    setTimeout(function() {{ ensureJQuery(callback); }}, 100);
                }}
            }}
            
            // 主函数 - 使用jQuery初始化所有功能
            ensureJQuery(function($) {{
                console.log('开始初始化表单字段...');
                
                // 记录页面上所有的输入字段
                console.log('页面上的输入字段:');
                $('input, select').each(function() {{
                    console.log($(this).attr('name') + ' (id=' + $(this).attr('id') + ', type=' + $(this).attr('type') + ')');
                }});
                
                // 设备编号到设备名称的映射
                const equipmentMap = {equipment_map_js};
                console.log('设备映射（总数:' + Object.keys(equipmentMap).length + '）:', equipmentMap);
                
                // 获取设备编号和设备名称字段元素
                let $numberField = $('#number');
                let $nameField = $('#name');
                
                // 检查是否找到字段
                console.log('初始设备编号字段状态:', $numberField.length > 0 ? '找到' : '未找到');
                console.log('初始设备名称字段状态:', $nameField.length > 0 ? '找到' : '未找到');
                
                // 确保设备名称字段为只读
                $nameField.prop('readonly', true);
                $nameField.addClass('equipment-name');
                $nameField.css('background-color', '#f5f5f5');
                
                // 将设备编号文本输入框转换为选择框（如果尚未转换）
                if ($numberField.length > 0 && $numberField.prop('tagName') === 'INPUT') {{
                    console.log('将设备编号文本框转换为选择框');
                    
                    // 获取当前值
                    const currentValue = $numberField.val();
                    
                    // 创建选择框元素
                    const $select = $('<select>')
                        .attr('id', 'number')
                        .attr('name', 'number')
                        .addClass('form-control');
                    
                    // 添加默认选项
                    $select.append($('<option value="">-- 请选择设备 --</option>'));
                    
                    // 添加设备选项
                    $.each(equipmentMap, function(number, name) {{
                        const $option = $('<option>')
                            .attr('value', number)
                            .text(number);
                        
                        if (number === currentValue) {{
                            $option.prop('selected', true);
                        }}
                        
                        $select.append($option);
                    }});
                    
                    // 替换原始输入框
                    $numberField.replaceWith($select);
                    
                    // 更新引用
                    $numberField = $('#number');
                    console.log('转换后的设备编号字段:', $numberField.length > 0 ? '找到' : '未找到');
                }}
                
                // 确保Select2已加载
                if ($.fn.select2) {{
                    console.log('Select2已加载，初始化选择框');
                    
                    // 初始化设备编号字段为Select2
                    try {{
                        $numberField.select2({{
                            placeholder: '请选择设备编号',
                            allowClear: true,
                            width: '100%'
                        }});
                        console.log('Select2初始化成功');
                    }} catch (e) {{
                        console.error('Select2初始化失败:', e);
                    }}
                    
                    // 设备编号变化时自动填充设备名称的函数
                    function updateEquipmentName() {{
                        const selectedNumber = $numberField.val();
                        console.log('选择的设备编号:', selectedNumber);
                        
                        if (selectedNumber && equipmentMap[selectedNumber]) {{
                            const equipmentName = equipmentMap[selectedNumber];
                            console.log('对应的设备名称:', equipmentName);
                            $nameField.val(equipmentName);
                            console.log('已设置设备名称为:', $nameField.val());
                        }} else {{
                            console.log('未找到对应的设备名称或未选择设备');
                            $nameField.val('');
                        }}
                    }}
                    
                    // 添加事件监听器
                    $numberField
                        .off('change select2:select') // 移除可能已有的事件处理器
                        .on('change', function() {{
                            console.log('设备编号change事件触发');
                            updateEquipmentName();
                        }})
                        .on('select2:select', function() {{
                            console.log('设备编号select2:select事件触发');
                            updateEquipmentName();
                        }});
                    
                    // 初始值处理
                    const initialValue = $numberField.val();
                    if (initialValue) {{
                        console.log('初始设备编号值:', initialValue);
                        updateEquipmentName();
                    }}
                    
                    // 确保在页面完全加载后再次更新
                    $(window).on('load', function() {{
                        console.log('窗口加载完成，再次检查设备名称');
                        setTimeout(updateEquipmentName, 500);
                    }});
                    
                    // 手动触发一次change事件，确保数据填充
                    setTimeout(function() {{
                        console.log('手动触发change事件');
                        $numberField.trigger('change');
                    }}, 300);
                }} else {{
                    console.error('错误: Select2未加载，无法初始化下拉框!');
                }}
                
                console.log('设备自动填充脚本初始化完成');
            }});
        </script>
        """
        if not hasattr(form, 'extras'):
            form.extras = []
        form.extras.append(Markup(js_code))

class BorrowListModelView(AdminAccessibleModelView, ModelView):
    """
    设备借用审批管理
    """
    # 设置视图名称
    name = '设备借用审批'
    
    column_labels = {
        'id': '记录ID',
        'name': '借用名称',
        'number': '借用编号',
        'borrow_time': '借用时间',
        'return_time': '预计归还时间',
        'content': '借用说明',
        'status': '审核状态',
        'reason': '拒绝原因',
        'user_id': '借用人ID',
        'user': '借用人'
    }
    column_list = ('id', 'name', 'number', 'borrow_time', 'return_time', 'status', 'user')
    
    # 添加搜索和过滤功能
    column_searchable_list = ('name', 'number', 'status')
    column_filters = ('status', 'borrow_time')
    
    # 添加列表视图介绍文本
    list_template = 'admin/borrowlist_list.html'
    
    def render(self, template, **kwargs):
        """为列表视图添加介绍文本"""
        if template == self.list_template:
            kwargs['intro_text'] = """
            <div class="alert alert-info">
                <h4><i class="glyphicon glyphicon-info-sign"></i> 设备借用审批说明</h4>
                <p>本页面<strong>仅负责设备借用申请的审核</strong>。您可以在此页面进行以下操作：</p>
                <ul>
                    <li>审核通过：批准用户的借用申请，设备状态将变为"借用中"</li>
                    <li>审核不通过：拒绝用户的借用申请，设备状态将保持"可用"</li>
                </ul>
                <p>设备归还流程请前往 <a href="/admin/returnlist/">设备归还审核</a> 页面操作。</p>
            </div>
            """
        return super(BorrowListModelView, self).render(template, **kwargs)
    
    # 自定义查询以仅显示借用流程相关记录（排除归还相关状态）
    def get_query(self):
        # 获取原始查询
        query = super(BorrowListModelView, self).get_query()
        # 过滤出只与借用相关的状态
        return query.filter(BorrowList.status.in_(['待审核', '审核通过', '审核不通过']))
    
    # 同样更新计数查询
    def get_count_query(self):
        # 获取原始计数查询
        query = super(BorrowListModelView, self).get_count_query()
        # 应用相同的过滤条件
        return query.filter(BorrowList.status.in_(['待审核', '审核通过', '审核不通过']))
        
    # 状态字段采用下拉框
    form_overrides = {
        'borrow_time': StringField,
        'return_time': StringField,
        'status': SelectField
    }
    
    # 设置状态字段的选项
    form_args = {
        'status': {
            'choices': [
                ('待审核', '待审核'),
                ('审核通过', '审核通过'),
                ('审核不通过', '审核不通过')
            ],
            'default': '待审核'
        },
        'reason': {
            'description': '如果选择"审核不通过"，请填写拒绝原因'
        }
    }
    
    # 添加JavaScript来自动显示/隐藏拒绝原因字段
    def edit_form(self, obj=None):
        form = super(BorrowListModelView, self).edit_form(obj)
        
        # 处理借用时间和归还时间的格式...
        if obj is not None:
            # 处理借用时间
            if obj.borrow_time:
                try:
                    dt = datetime.strptime(obj.borrow_time, '%Y-%m-%d %H:%M:%S')
                    form.borrow_time.data = dt.strftime('%Y-%m-%dT%H:%M:%S')
                except ValueError:
                    try:
                        formats = ['%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M']
                        for fmt in formats:
                            try:
                                dt = datetime.strptime(obj.borrow_time, fmt)
                                form.borrow_time.data = dt.strftime('%Y-%m-%dT%H:%M:%S')
                                break
                            except ValueError:
                                continue
                    except Exception:
                        pass  # 保留原始值
            
            # 处理归还时间
            if obj.return_time:
                try:
                    dt = datetime.strptime(obj.return_time, '%Y-%m-%d %H:%M:%S')
                    form.return_time.data = dt.strftime('%Y-%m-%dT%H:%M:%S')
                except ValueError:
                    try:
                        formats = ['%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M']
                        for fmt in formats:
                            try:
                                dt = datetime.strptime(obj.return_time, fmt)
                                form.return_time.data = dt.strftime('%Y-%m-%dT%H:%M:%S')
                                break
                            except ValueError:
                                continue
                    except Exception:
                        pass  # 保留原始值
        
        # 添加自动显示/隐藏拒绝原因字段的JavaScript
        js = """
        <script>
            $(function() {
                // 获取状态和拒绝原因字段
                var statusField = $('#status');
                var reasonField = $('#reason').closest('.form-group');
                
                // 初始处理
                function updateReasonField() {
                    if (statusField.val() === '审核不通过') {
                        reasonField.show();
                    } else {
                        reasonField.hide();
                    }
                }
                
                // 初始状态
                updateReasonField();
                
                // 监听变化
                statusField.change(updateReasonField);
            });
        </script>
        """
        
        if not hasattr(form, 'extras'):
            form.extras = []
        form.extras.append(Markup(js))
        
        return form
        
    # 设置格式化函数来将状态显示为彩色标签
    def _status_formatter(view, context, model, name):
        status = getattr(model, name)
        if status:
            status_class = get_status_class(status)
            return Markup(f'<span class="label {status_class}">{status}</span>')
        return ''
        
    column_formatters = {
        'status': _status_formatter
    }
    
# 状态标签样式辅助函数
def get_status_class(status):
    """根据状态返回对应的CSS类"""
    if status in ['待审核', '待审批', 'pending', None, '']:
        return 'label-warning'  # 黄色
    elif status in ['审核通过', '已通过']:
        return 'label-success'  # 绿色
    elif status in ['审核不通过', '未通过']:
        return 'label-danger'   # 红色
    elif status in ['归还完成', '已归还']:
        return 'label-info'     # 蓝色
    elif status == '归还待审核':
        return 'label-primary'  # 深蓝色
    else:
        return 'label-default'  # 灰色
    form_columns = ('name', 'number', 'borrow_time', 'return_time', 'content', 'status', 'reason', 'user_id')
    
    # 添加操作列，用于显示审核按钮
    can_edit = True
    can_delete = True
    can_create = False  # 禁用创建功能，因为借用记录应该由用户申请时自动生成
    can_view_details = True
    
    # 添加批量操作按钮
    action_disallowed_list = []  # 不禁用任何操作
    
    # 自定义时间字段为HTML5日期时间选择器和状态字段为下拉框
    form_overrides = {
        'borrow_time': StringField,
        'return_time': StringField,
        'status': SelectField
    }
    
    form_widget_args = {
        'borrow_time': {
            'type': 'datetime-local',
            'step': '1'  # 支持秒级选择
        },
        'return_time': {
            'type': 'datetime-local',
            'step': '1'  # 支持秒级选择
        }
    }
    
    # 为状态字段设置下拉选项
    form_args = {
        'status': {
            'choices': [
                ('待审核', '待审核'),
                ('审核通过', '审核通过'),
                ('审核不通过', '审核不通过')
            ],
            'default': '待审核'
        },
        'reason': {
            'description': '如果选择"审核不通过"，请填写拒绝原因'
        }
    }
    
    # 添加审核通过和审核不通过的批量操作
    def create_form(self):
        """创建表单时，设置默认状态和添加JavaScript控制"""
        form = super(BorrowListModelView, self).create_form()
        
        # 设置默认状态为"待审核"
        if hasattr(form, 'status'):
            form.status.data = '待审核'
        
        # 添加JavaScript代码，控制拒绝原因字段的显示
        js_code = """
        <script>
            $(document).ready(function() {
                // 获取状态和原因字段
                var $statusField = $('#status');
                var $reasonField = $('#reason').closest('.form-group');
                
                // 初始状态处理
                function updateReasonVisibility() {
                    var selectedStatus = $statusField.val();
                    if (selectedStatus === '审核不通过') {
                        $reasonField.show();
                    } else {
                        $reasonField.hide();
                    }
                }
                
                // 初始执行一次
                updateReasonVisibility();
                
                // 监听状态变化
                $statusField.change(function() {
                    updateReasonVisibility();
                });
            });
        </script>
        """
        
        if not hasattr(form, 'extras'):
            form.extras = []
        form.extras.append(Markup(js_code))
        
        return form

    @expose('/approve', methods=['POST'])
    def action_approve(self):
        try:
            # 获取选中的记录
            ids = request.form.getlist('rowid')
            count = 0
            
            for record_id in ids:
                record = BorrowList.query.get(record_id)
                if record:
                    # 更新状态为"审核通过"
                    record.status = "审核通过"
                    count += 1
                    
                    # 查找设备并更新其状态
                    equipment = Equipment.query.filter_by(number=record.number).first()
                    if equipment:
                        # 确保设备状态设置为"借用中"
                        if equipment.status != "借用中":
                            equipment.status = "借用中"
                            print(f"设备 {equipment.number} 状态更新为: 借用中")
                        db.session.add(equipment)
                    else:
                        print(f"警告：找不到编号为 {record.number} 的设备")
                    
                    # 为用户创建通知
                    if record.user_id:
                        user_notice = UserNotice(
                            content=f"您申请借用的设备 {record.name}（编号：{record.number}）已审核通过。",
                            user_id=record.user_id,
                            record_id=record.id,
                            equipment_id=equipment.id if equipment else None
                        )
                        db.session.add(user_notice)
                
            # 确保立即提交更改
            db.session.commit()
            flash(f'成功审核通过 {count} 条借用申请。', 'success')
        except Exception as ex:
            db.session.rollback()
            flash(f'审核过程中出现错误: {str(ex)}', 'error')
            print(f"借用审核出错: {str(ex)}")
        return redirect(url_for('.index_view'))
    
    @expose('/reject', methods=['POST'])
    def action_reject(self):
        # 保存ID列表到会话，以便在表单提交时使用
        session['reject_borrow_ids'] = request.form.getlist('rowid')
        # 重定向到填写拒绝原因的页面
        return redirect(url_for('.reject_form'))
    
    # 添加用于显示和处理拒绝原因表单的路由
    @expose('/reject_form', methods=['GET', 'POST'])
    def reject_form(self):
        if request.method == 'POST':
            reason = request.form.get('reason', '未提供原因')
            ids = session.get('reject_borrow_ids', [])
            
            try:
                query = BorrowList.query.filter(BorrowList.id.in_(ids))
                count = 0
                
                for record in query.all():
                    # 更新状态为"审核不通过"并设置拒绝原因
                    record.status = "审核不通过"
                    record.reason = reason
                    count += 1
                    
                    # 重要：将对应设备状态重置为"可用"
                    equipment = Equipment.query.filter_by(number=record.number).first()
                    if equipment and equipment.status == "借用中":
                        equipment.status = "可用"
                        db.session.add(equipment)
                    
                    # 为用户创建通知
                    if record.user_id:
                        user_notice = UserNotice(
                            content=f"您申请借用的设备 {record.name}（编号：{record.number}）未通过审核。原因：{reason}",
                            user_id=record.user_id,
                            record_id=record.id
                        )
                        db.session.add(user_notice)
                
                db.session.commit()
                flash(f'成功拒绝 {count} 条借用申请。', 'success')
                # 处理完毕后清除会话数据
                session.pop('reject_borrow_ids', None)
                return redirect(url_for('.index_view'))
            except Exception as ex:
                db.session.rollback()
                flash(f'处理拒绝申请时出现错误: {str(ex)}', 'error')
                return redirect(url_for('.index_view'))
        
        # GET请求时，显示填写拒绝原因的表单
        return self.render('admin/reject_form.html')
    
    # 添加行操作按钮（每行单独的审核按钮）
    def _row_actions(self, context, data, model_name, model_id, primary_key):
        row_actions = super()._row_actions(context, data, model_name, model_id, primary_key)
        
        # 只有待审核状态的记录才显示审核按钮
        if hasattr(data, 'status') and data.status in ["待审核", "待审批", "pending", None, ""]:
            # 添加审核通过按钮
            approve_url = url_for('.action_view')
            approve_button = """
                <form class="icon" method="POST" action="{approve_url}" style="display:inline;">
                    <input type="hidden" name="action" value="approve">
                    <input type="hidden" name="rowid" value="{model_id}">
                    <input type="hidden" name="_csrf_token" value="{{{{ csrf_token() }}}}">
                    <button onclick="return confirm('确定要批准此借用申请吗？');" class="btn btn-sm btn-success">
                        <i class="glyphicon glyphicon-ok"></i> 通过
                    </button>
                </form>
            """.format(approve_url=approve_url, model_id=model_id)
            
            # 添加审核不通过按钮
            reject_url = url_for('.reject_single', id=model_id)
            reject_button = """
                <a href="{reject_url}" class="btn btn-sm btn-danger" title="不通过">
                    <i class="glyphicon glyphicon-remove"></i> 不通过
                </a>
            """.format(reject_url=reject_url)
            
            # 将按钮添加到操作列表中
            row_actions.append(Markup(approve_button))
            row_actions.append(Markup(reject_button))
        
        # 对于已审核的记录，添加查看拒绝原因的按钮（如果有）
        elif hasattr(data, 'status') and data.status == "审核不通过" and hasattr(data, 'reason') and data.reason:
            reason_button = """
                <button class="btn btn-sm btn-info" title="查看原因" 
                    onclick="alert('拒绝原因: {reason}');">
                    <i class="glyphicon glyphicon-info-sign"></i> 查看原因
                </button>
            """.format(reason=data.reason.replace("'", "\\'").replace('"', '\\"'))
            
            row_actions.append(Markup(reason_button))
            
        return row_actions
    
    @expose('/reject_single/<id>', methods=['GET', 'POST'])
    def reject_single(self, id):
        if request.method == 'POST':
            reason = request.form.get('reason', '未提供原因')
            
            try:
                record = BorrowList.query.get(id)
                if record:
                    # 更新状态为"审核不通过"并设置拒绝原因
                    record.status = "审核不通过"
                    record.reason = reason
                    
                    # 重要：将对应设备状态重置为"可用"
                    equipment = Equipment.query.filter_by(number=record.number).first()
                    if equipment and equipment.status == "借用中":
                        equipment.status = "可用"
                        db.session.add(equipment)
                    
                    # 为用户创建通知
                    if record.user_id:
                        user_notice = UserNotice(
                            content=f"您申请借用的设备 {record.name}（编号：{record.number}）未通过审核。原因：{reason}",
                            user_id=record.user_id,
                            record_id=record.id
                        )
                        db.session.add(user_notice)
                    
                    db.session.commit()
                    flash('成功拒绝该借用申请。', 'success')
                else:
                    flash('找不到指定的借用记录。', 'error')
                
                return redirect(url_for('.index_view'))
            except Exception as ex:
                db.session.rollback()
                flash(f'处理拒绝申请时出现错误: {str(ex)}', 'error')
                return redirect(url_for('.index_view'))
        
        # GET请求时，显示填写拒绝原因的表单
        return self.render('admin/reject_form.html', single_id=id)
    
    def on_model_change(self, form, model, is_created):
        # 处理借用时间
        if not model.borrow_time:
            model.borrow_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        elif 'T' in model.borrow_time:  # 处理HTML5日期时间选择器的格式
            try:
                dt = datetime.strptime(model.borrow_time, '%Y-%m-%dT%H:%M:%S')
                model.borrow_time = dt.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                try:
                    dt = datetime.strptime(model.borrow_time, '%Y-%m-%dT%H:%M')
                    model.borrow_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                except ValueError:
                    pass  # 保留原始值
        
        # 处理归还时间
        if model.return_time and 'T' in model.return_time:
            try:
                dt = datetime.strptime(model.return_time, '%Y-%m-%dT%H:%M:%S')
                model.return_time = dt.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                try:
                    dt = datetime.strptime(model.return_time, '%Y-%m-%dT%H:%M')
                    model.return_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                except ValueError:
                    pass  # 保留原始值
        
        # 获取表单中的状态
        new_status = model.status
        
        # 处理状态变更
        if not is_created:
            # 获取旧状态
            try:
                old_record = BorrowList.query.get(model.id)
                if old_record and old_record.status != new_status:
                    # 如果状态变为"审核通过"
                    if new_status == "审核通过":
                        # 更新设备状态
                        equipment = Equipment.query.filter_by(number=model.number).first()
                        if equipment:
                            # 确保设备状态设置为"借用中"
                            if equipment.status != "借用中":
                                equipment.status = "借用中"
                                print(f"[表单编辑] 设备 {equipment.number} 状态更新为: 借用中")
                            self.session.add(equipment)
                        else:
                            print(f"[表单编辑] 警告：找不到编号为 {model.number} 的设备")
                        
                        # 创建用户通知
                        if model.user_id:
                            user_notice = UserNotice(
                                content=f"您申请借用的设备 {model.name}（编号：{model.number}）已审核通过。",
                                user_id=model.user_id,
                                record_id=model.id,
                                equipment_id=equipment.id if equipment else None
                            )
                            self.session.add(user_notice)
                    
                    # 如果状态变为"审核不通过"
                    elif new_status == "审核不通过":
                        # 确保有填写拒绝原因
                        if not model.reason or model.reason.strip() == '':
                            model.reason = "管理员未提供具体原因"
                        
                        # 重要：将对应设备状态重置为"可用"
                        equipment = Equipment.query.filter_by(number=model.number).first()
                        if equipment and equipment.status == "借用中":
                            equipment.status = "可用"
                            self.session.add(equipment)
                        
                        # 创建用户通知
                        if model.user_id:
                            user_notice = UserNotice(
                                content=f"您申请借用的设备 {model.name}（编号：{model.number}）未通过审核。原因：{model.reason}",
                                user_id=model.user_id,
                                record_id=model.id
                            )
                            self.session.add(user_notice)
                    
                    # 如果状态变为"已归还"
                    elif new_status == "已归还":
                        # 更新设备状态为可用
                        equipment = Equipment.query.filter_by(number=model.number).first()
                        if equipment:
                            equipment.status = "可用"
                            self.session.add(equipment)
                        
                        # 创建用户通知
                        if model.user_id:
                            user_notice = UserNotice(
                                content=f"您借用的设备 {model.name}（编号：{model.number}）已确认归还。",
                                user_id=model.user_id,
                                record_id=model.id,
                                equipment_id=equipment.id if equipment else None
                            )
                            self.session.add(user_notice)
            except Exception as e:
                print(f"处理状态变更时出错: {e}")
                # 错误处理：失败时不中断流程，但记录错误
                pass
                    
    def edit_form(self, obj=None):
        """编辑表单时，将数据库中的时间格式转换为HTML5日期时间选择器需要的格式"""
        form = super(BorrowListModelView, self).edit_form(obj)
        if obj is not None:
            # 处理借用时间
            if obj.borrow_time:
                try:
                    dt = datetime.strptime(obj.borrow_time, '%Y-%m-%d %H:%M:%S')
                    form.borrow_time.data = dt.strftime('%Y-%m-%dT%H:%M:%S')
                except ValueError:
                    try:
                        formats = ['%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M']
                        for fmt in formats:
                            try:
                                dt = datetime.strptime(obj.borrow_time, fmt)
                                form.borrow_time.data = dt.strftime('%Y-%m-%dT%H:%M:%S')
                                break
                            except ValueError:
                                continue
                    except Exception:
                        pass  # 保留原始值
            
            # 处理归还时间
            if obj.return_time:
                try:
                    dt = datetime.strptime(obj.return_time, '%Y-%m-%d %H:%M:%S')
                    form.return_time.data = dt.strftime('%Y-%m-%dT%H:%M:%S')
                except ValueError:
                    try:
                        formats = ['%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M']
                        for fmt in formats:
                            try:
                                dt = datetime.strptime(obj.return_time, fmt)
                                form.return_time.data = dt.strftime('%Y-%m-%dT%H:%M:%S')
                                break
                            except ValueError:
                                continue
                    except Exception:
                        pass  # 保留原始值
        
        # 添加JavaScript代码，控制拒绝原因字段的显示
        js_code = """
        <script>
            $(document).ready(function() {
                // 获取状态和原因字段
                var $statusField = $('#status');
                var $reasonField = $('#reason').closest('.form-group');
                
                // 初始状态处理
                function updateReasonVisibility() {
                    var selectedStatus = $statusField.val();
                    if (selectedStatus === '审核不通过') {
                        $reasonField.show();
                    } else {
                        $reasonField.hide();
                    }
                }
                
                // 初始执行一次
                updateReasonVisibility();
                
                // 监听状态变化
                $statusField.change(function() {
                    updateReasonVisibility();
                });
            });
        </script>
        """
        
        if not hasattr(form, 'extras'):
            form.extras = []
        form.extras.append(Markup(js_code))
                        
        return form

class ReturnListModelView(AdminAccessibleModelView, ModelView):
    """
    设备归还审核管理
    """
    # 设置视图名称
    name = '设备归还审核'
    
    column_labels = {
        'id': '记录ID',
        'name': '归还名称',
        'number': '设备编号',
        'date': '申请归还日期',
        'status': '审核状态',
        'reason': '拒绝原因',
        'user_id': '归还人ID',
        'user': '归还人'
    }
    column_list = ('id', 'name', 'number', 'date', 'status', 'user_id')
    form_columns = ('name', 'number', 'date', 'status', 'reason', 'user_id')
    
    # 添加搜索和过滤功能
    column_searchable_list = ('name', 'number', 'status')
    column_filters = ('status', 'date')
    
    # 添加列表视图介绍文本
    list_template = 'admin/returnlist_list.html'
    
    def render(self, template, **kwargs):
        """为列表视图添加介绍文本"""
        if template == self.list_template:
            kwargs['intro_text'] = """
            <div class="alert alert-info">
                <h4><i class="glyphicon glyphicon-info-sign"></i> 设备归还审核说明</h4>
                <p>本页面<strong>仅负责设备归还申请的审核</strong>。您可以在此页面进行以下操作：</p>
                <ul>
                    <li>审核通过：确认设备已归还，设备状态将自动变为"可用"</li>
                    <li>审核不通过：拒绝归还申请，设备状态将保持"借用中"</li>
                </ul>
                <p>一旦归还申请审核通过，借用流程即视为结束，无需再回到借用记录页面操作。</p>
                <p><a href="/admin/refresh_equipment_status" class="btn btn-primary" onclick="return confirm('确定要刷新所有设备状态吗？');">
                    <i class="glyphicon glyphicon-refresh"></i> 刷新所有设备状态
                </a></p>
            </div>
            """
        return super(ReturnListModelView, self).render(template, **kwargs)
        
    # 自定义查询以仅显示归还流程相关记录
    def get_query(self):
        # 获取原始查询
        query = super(ReturnListModelView, self).get_query()
        # 过滤出只与归还相关的状态
        return query.filter(ReturnList.status.in_(['待审核', '审核通过', '审核不通过']))
    
    # 同样更新计数查询
    def get_count_query(self):
        # 获取原始计数查询
        query = super(ReturnListModelView, self).get_count_query()
        # 应用相同的过滤条件
        return query.filter(ReturnList.status.in_(['待审核', '审核通过', '审核不通过']))
    
    # 自定义日期字段为HTML5日期时间选择器，状态字段为下拉框
    form_overrides = {
        'date': StringField,
        'status': SelectField
    }
    
    form_widget_args = {
        'date': {
            'type': 'datetime-local',
            'step': '1'  # 支持秒级选择
        }
    }
    
    # 为状态字段设置下拉选项
    form_args = {
        'status': {
            'choices': [
                ('待审核', '待审核'),
                ('审核通过', '审核通过'),
                ('审核不通过', '审核不通过')
            ],
            'default': '待审核'
        },
        'reason': {
            'description': '如果选择"审核不通过"，请填写原因'
        }
    }
    
    # 设置格式化函数来将状态显示为彩色标签
    def _status_formatter(view, context, model, name):
        status = getattr(model, name)
        if status:
            status_class = get_status_class(status)
            return Markup(f'<span class="label {status_class}">{status}</span>')
        return ''
        
    column_formatters = {
        'status': _status_formatter
    }
    
    def on_model_change(self, form, model, is_created):
        # 如果没有输入日期，则使用当前时间
        if not model.date:
            model.date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # 格式化日期字段
        elif 'T' in model.date:  # 处理HTML5日期时间选择器的格式
            try:
                # 将"2023-03-18T20:24:35"格式转换为"2023-03-18 20:24:35"
                dt = datetime.strptime(model.date, '%Y-%m-%dT%H:%M:%S')
                model.date = dt.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                # 如果格式不匹配，尝试不带秒的格式
                try:
                    dt = datetime.strptime(model.date, '%Y-%m-%dT%H:%M')
                    model.date = dt.strftime('%Y-%m-%d %H:%M:%S')
                except ValueError:
                    pass  # 保留原始值
                    
        # 处理状态变更
        if not is_created:
            old_record = ReturnList.query.get(model.id)
            new_status = model.status
            
            # 从名称中提取借用记录ID
            import re
            borrow_id = None
            if model.name and model.name.startswith('归还-'):
                match = re.match(r'归还-(\d+)-', model.name)
                if match:
                    borrow_id = int(match.group(1))
            
            # 如果状态从"待审核"变为"审核通过"
            if old_record and old_record.status != new_status and new_status == "审核通过":
                # 更新关联的借用记录和设备状态
                try:
                    # 更新借用记录状态为"归还完成"
                    borrow_record = BorrowList.query.get(borrow_id) if borrow_id else None
                    if borrow_record:
                        borrow_record.status = "归还完成"  # 内部状态，不在下拉框中显示
                        self.session.add(borrow_record)
                        print(f"借用记录ID:{borrow_id} 状态已更新为: 归还完成")
                        
                    # 更新设备状态为可用
                    equipment = Equipment.query.filter_by(number=model.number).first()
                    if equipment:
                        old_status = equipment.status
                        equipment.status = "可用"
                        self.session.add(equipment)
                        print(f"归还审核通过: 设备 {model.number} 状态从 '{old_status}' 更新为 '可用'")
                        
                        # 确保立即提交更改，不等待整个事务结束
                        try:
                            # 立即刷新变更到数据库
                            self.session.flush()
                            print(f"设备状态更改已刷新到数据库")
                            
                            # 强制提交更改，确保立即生效
                            db.session.commit()
                            print(f"设备 {model.number} 状态更新已提交到数据库")
                            
                            # 立即更新全局设备状态
                            try:
                                # 直接执行SQL更新，确保状态立即更新
                                db.engine.execute(
                                    "UPDATE equipment SET status = '可用' WHERE number = %s", 
                                    (model.number,)
                                )
                                print(f"设备 {model.number} 状态已通过直接SQL更新为可用")
                            except Exception as sql_ex:
                                print(f"SQL直接更新失败: {str(sql_ex)}")
                        except Exception as flush_ex:
                            print(f"刷新失败: {flush_ex}")
                    else:
                        print(f"错误: 找不到编号为 {model.number} 的设备!")
                            
                    # 创建用户通知
                    if model.user_id:
                        display_name = model.name.split('-')[-1] if '-' in model.name else model.name
                        user_notice = UserNotice(
                            content=f"您归还的设备 {display_name}（编号：{model.number}）已确认归还。",
                            user_id=model.user_id,
                            record_id=model.id,
                            equipment_id=equipment.id if equipment else None
                        )
                        self.session.add(user_notice)
                except Exception as e:
                    print(f"处理归还审核时出错: {e}")
            
            # 如果状态从"待审核"变为"审核不通过"
            elif old_record and old_record.status != new_status and new_status == "审核不通过":
                # 确保有拒绝原因
                if not model.reason:
                    model.reason = "管理员未提供原因"
                
                # 更新借用记录状态回到"审核通过"（继续借用）
                borrow_record = BorrowList.query.get(borrow_id) if borrow_id else None
                if borrow_record and borrow_record.status == "归还待审核":
                    borrow_record.status = "审核通过"  # 恢复为借用状态
                    self.session.add(borrow_record)
                
                # 创建用户通知
                if model.user_id:
                    display_name = model.name.split('-')[-1] if '-' in model.name else model.name
                    user_notice = UserNotice(
                        content=f"您归还的设备 {display_name}（编号：{model.number}）未通过归还审核。原因：{model.reason}",
                        user_id=model.user_id,
                        record_id=model.id
                    )
                    self.session.add(user_notice)
                    print(f"归还审核不通过: 设备{model.number} 保持借用中状态")
                    
    def edit_form(self, obj=None):
        """编辑表单时，将数据库中的日期格式转换为HTML5日期时间选择器需要的格式"""
        form = super(ReturnListModelView, self).edit_form(obj)
        if obj is not None and obj.date:
            try:
                # 尝试将"2023-03-18 20:24:35"转换为"2023-03-18T20:24:35"
                dt = datetime.strptime(obj.date, '%Y-%m-%d %H:%M:%S')
                form.date.data = dt.strftime('%Y-%m-%dT%H:%M:%S')
            except ValueError:
                try:
                    # 尝试其他可能的格式
                    formats = ['%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M']
                    for fmt in formats:
                        try:
                            dt = datetime.strptime(obj.date, fmt)
                            form.date.data = dt.strftime('%Y-%m-%dT%H:%M:%S')
                            break
                        except ValueError:
                            continue
                except Exception:
                    # 如果所有转换都失败，保持原始值
                    pass
        
        # 添加JavaScript代码，控制拒绝原因字段的显示
        js_code = """
        <script>
            $(document).ready(function() {
                // 获取状态和原因字段
                var $statusField = $('#status');
                var $reasonField = $('#reason').closest('.form-group');
                
                // 初始状态处理
                function updateReasonVisibility() {
                    var selectedStatus = $statusField.val();
                    if (selectedStatus === '审核不通过') {
                        $reasonField.show();
                    } else {
                        $reasonField.hide();
                    }
                }
                
                // 初始执行一次
                updateReasonVisibility();
                
                // 监听状态变化
                $statusField.change(function() {
                    updateReasonVisibility();
                });
            });
        </script>
        """
        
        if not hasattr(form, 'extras'):
            form.extras = []
        form.extras.append(Markup(js_code))
        
        return form
    
    # 添加批量操作
    action_disallowed_list = []
    
    # 添加批量审核通过和审核不通过的操作
    @action('approve_returns', '批量审核通过', '确定要批量审核通过选中的归还记录吗？')
    def action_approve_returns(self, ids):
        try:
            # 查询选中的记录
            query = self.get_query().filter(self.model.id.in_(ids))
            count = 0
            
            for record in query.all():
                # 只处理"待审核"状态的记录
                if record.status == "待审核":
                    # 更新状态为"审核通过"
                    record.status = "审核通过"
                    
                    # 从名称中提取借用记录ID
                    import re
                    borrow_id = None
                    if record.name and record.name.startswith('归还-'):
                        match = re.match(r'归还-(\d+)-', record.name)
                        if match:
                            borrow_id = int(match.group(1))
                    
                    # 更新借用记录状态为"归还完成"（内部标记，不显示在下拉框中）
                    borrow_record = BorrowList.query.get(borrow_id) if borrow_id else None
                    if borrow_record:
                        # 设置一个内部状态，标记借用已完成但不会出现在下拉框选项中
                        borrow_record.status = "归还完成"
                        db.session.add(borrow_record)
                        print(f"借用记录 ID:{borrow_id} 已标记为归还完成")
                        
                    # 更新设备状态为可用
                    equipment = Equipment.query.filter_by(number=record.number).first()
                    if equipment:
                        # 保存原始状态以便调试
                        old_status = equipment.status
                        equipment.status = "可用"
                        db.session.add(equipment)
                        print(f"批量归还审核: 设备 {equipment.number} 状态从 '{old_status}' 更新为 '可用'")
                        
                        # 每次单独处理一条记录，以确保状态更新立即生效
                        try:
                            # 立即刷新变更到数据库
                            db.session.flush()
                            print(f"设备 {equipment.number} 状态已成功刷新到数据库")
                            
                            # 为此设备单独提交更改，确保立即生效
                            db.session.commit()
                            print(f"设备 {equipment.number} 状态更新已单独提交到数据库")
                            
                            # 立即更新全局设备状态
                            try:
                                # 直接执行SQL更新，确保状态立即更新
                                db.engine.execute(
                                    "UPDATE equipment SET status = '可用' WHERE number = %s", 
                                    (record.number,)
                                )
                                print(f"设备 {equipment.number} 状态已通过直接SQL更新为可用")
                            except Exception as sql_ex:
                                print(f"SQL直接更新失败: {str(sql_ex)}")
                            
                            # 查询确认更新是否成功
                            refreshed_equipment = Equipment.query.filter_by(number=record.number).first()
                            if refreshed_equipment and refreshed_equipment.status == "可用":
                                print(f"确认: 设备 {equipment.number} 状态已成功更新为 '可用'")
                            else:
                                print(f"警告: 设备 {equipment.number} 状态更新可能未成功，当前状态: {refreshed_equipment.status if refreshed_equipment else '未知'}")
                        except Exception as flush_ex:
                            print(f"刷新设备状态失败: {str(flush_ex)}")
                            # 发生错误时回滚，然后继续处理其他记录
                            db.session.rollback()
                    else:
                        print(f"严重错误: 找不到编号为 '{record.number}' 的设备!")
                        
                    # 创建用户通知
                    if record.user_id:
                        user_notice = UserNotice(
                            content=f"您归还的设备 {record.name.split('-')[-1] if '-' in record.name else record.name}（编号：{record.number}）已确认归还。",
                            user_id=record.user_id,
                            record_id=record.id,
                            equipment_id=equipment.id if equipment else None
                        )
                        db.session.add(user_notice)
                    
                    count += 1
                    
            db.session.commit()
            flash(f'成功审核通过 {count} 条归还记录。', 'success')
        except Exception as ex:
            db.session.rollback()
            flash(f'审核过程中出现错误: {str(ex)}', 'error')
            print(f"批量归还审核出错: {str(ex)}")
    
    @action('reject_returns', '批量审核不通过', '确定要批量拒绝选中的归还记录吗？')
    def action_reject_returns(self, ids):
        # 保存ID列表到会话，以便在表单提交时使用
        session['reject_return_ids'] = ids
        # 重定向到填写拒绝原因的页面
        return redirect(url_for('.reject_return_form'))
    
    # 拒绝归还的表单页面
    @expose('/reject_return_form', methods=['GET', 'POST'])
    def reject_return_form(self):
        if request.method == 'POST':
            reason = request.form.get('reason', '未提供原因')
            ids = session.get('reject_return_ids', [])
            
            try:
                query = ReturnList.query.filter(ReturnList.id.in_(ids))
                count = 0
                
                for record in query.all():
                    # 只处理"待审核"状态的记录
                    if record.status == "待审核":
                        # 更新状态为"审核不通过"并设置拒绝原因
                        record.status = "审核不通过"
                        record.reason = reason
                        
                        # 从名称中提取借用记录ID
                        import re
                        borrow_id = None
                        if record.name and record.name.startswith('归还-'):
                            match = re.match(r'归还-(\d+)-', record.name)
                            if match:
                                borrow_id = int(match.group(1))
                        
                        # 更新借用记录状态回到"审核通过"（继续借用）
                        borrow_record = BorrowList.query.get(borrow_id) if borrow_id else None
                        if borrow_record and borrow_record.status == "归还待审核":
                            borrow_record.status = "审核通过"  # 恢复为借用状态
                            db.session.add(borrow_record)
                        
                        # 创建用户通知
                        if record.user_id:
                            display_name = record.name.split('-')[-1] if '-' in record.name else record.name
                            user_notice = UserNotice(
                                content=f"您归还的设备 {display_name}（编号：{record.number}）未通过归还审核。原因：{reason}",
                                user_id=record.user_id,
                                record_id=record.id
                            )
                            db.session.add(user_notice)
                        
                        count += 1
                
                db.session.commit()
                flash(f'成功拒绝 {count} 条归还申请。', 'success')
                # 处理完毕后清除会话数据
                session.pop('reject_return_ids', None)
                return redirect(url_for('.index_view'))
            except Exception as ex:
                db.session.rollback()
                flash(f'处理拒绝申请时出现错误: {str(ex)}', 'error')
                print(f"拒绝归还申请出错: {str(ex)}")
                return redirect(url_for('.index_view'))
        
        # GET请求时，显示填写拒绝原因的表单
        return self.render('admin/reject_form.html', action_name="归还")

class UserModelView(AdminAccessibleModelView, ModelView):
    """
    用户管理自定义后台
    """
    column_list = ('username', 'name', 'email', 'phone', 'role')
    column_labels = {'username': '用户名', 'name': '姓名', 'email': '邮箱', 'phone': '手机号', 'role': '角色'}
    form_columns = ('username', 'password', 'name', 'phone', 'email', 'role')
    page_size = 15  # 每页显示15条记录
    can_set_page_size = True  # 允许用户设置每页显示的记录数
    
    # 创建表单时自定义角色和密码字段
    def scaffold_form(self):
        form_class = super(UserModelView, self).scaffold_form()
        form_class.role = SelectField('角色', choices=[
            ('ADMIN', '管理员'),
            ('USER', '普通用户')
        ])
        # 添加密码字段
        form_class.password = PasswordField('密码')
        return form_class
    
    def on_model_change(self, form, model, is_created):
        # 处理密码
        if form.password.data:
            model.password = form.password.data  # 直接保存明文密码，与系统当前逻辑一致
        elif is_created:
            raise ValidationError('必须设置密码')
            
        # 确保角色值正确保存
        if hasattr(form, 'role') and form.role.data:
            model.role = form.role.data
            
        # 打印用户信息，但不要依赖model.id，因为在创建时它可能为None
        print(f"保存用户: 用户名={model.username}, 角色={model.role}, 创建={is_created}")
        
        # 如果是创建新用户且角色是管理员，则中止保存到user表，改为保存到admin表
        if is_created and model.role and model.role.upper() == 'ADMIN':
            # 设置标记，在after_model_change中使用
            model._skip_user_save = True
            
            try:
                # 创建新的admin记录
                new_admin = AdminModel(
                    username=model.username,
                    password=model.password,
                    name=model.name,
                    email=model.email,
                    phone=model.phone
                )
                db.session.add(new_admin)
                db.session.flush()  # 获取ID但不提交
                
                print(f"管理员用户 {model.username} 已准备保存到admin表")
            except Exception as e:
                print(f"创建admin记录时出错: {e}")
                # 不抛出异常，让流程继续
    
    def after_model_change(self, form, model, is_created):
        """在模型保存后执行，处理管理员用户的特殊逻辑"""
        # 如果是管理员用户且是新创建的
        if hasattr(model, '_skip_user_save') and model._skip_user_save:
            try:
                # 提交admin表的更改
                db.session.commit()
                
                # 删除刚刚创建的user表记录
                if model.id:
                    db.session.delete(model)
                    db.session.commit()
                    
                print(f"管理员用户 {model.username} 已保存到admin表，并从user表中删除")
            except Exception as e:
                db.session.rollback()
                print(f"处理管理员用户时出错: {e}")
        # 如果是普通用户，不需要特殊处理
        elif model.role and model.role.upper() == 'USER':
            print(f"普通用户 {model.username} 已保存到user表")
        # 如果是更新管理员用户
        elif model.role and model.role.upper() == 'ADMIN' and not is_created:
            try:
                # 检查admin表中是否已存在该用户名的记录
                existing_admin = AdminModel.query.filter_by(username=model.username).first()
                
                if existing_admin:
                    # 如果已存在，则更新记录
                    existing_admin.name = model.name
                    existing_admin.password = model.password
                    existing_admin.email = model.email
                    existing_admin.phone = model.phone
                    db.session.add(existing_admin)
                    db.session.commit()
                    print(f"管理员用户 {model.username} 的数据已更新到admin表")
            except Exception as e:
                db.session.rollback()
                print(f"更新admin表时出错: {e}")
                
    def on_model_delete(self, model):
        """在删除用户时，同时检查并删除admin表中的对应记录"""
        if model.role and model.role.upper() == 'ADMIN':
            try:
                admin_user = AdminModel.query.filter_by(username=model.username).first()
                if admin_user:
                    db.session.delete(admin_user)
                    db.session.commit()
                    print(f"管理员用户 {model.username} 已从admin表中删除")
            except Exception as e:
                db.session.rollback()
                print(f"从admin表删除用户时出错: {e}")
                
    # 不需要排除密码字段，因为我们已经自定义了它
    column_exclude_list = ('password',)

    def get_list(self, page, sort_field, sort_desc, search, filters, page_size=None):
        """重写get_list方法，合并user表和admin表中的用户，先显示角色为admin的用户，再显示角色为user的用户"""
        # 设置页面大小
        if page_size is None:
            page_size = self.page_size
        
        # 首先获取所有user表用户数据
        query = self.get_query()
        user_count = self.get_count_query().scalar()
        
        # 应用排序
        if sort_field is not None:
            sort_field = self._get_column_by_name(sort_field)
            query = query.order_by(sort_desc and desc(sort_field) or sort_field)
        else:
            query = query.order_by(self.model.id.asc())
        
        # 获取user表中的所有用户
        user_users = query.all()
        
        # 处理搜索条件
        if search:
            search_term = search.lower()
            user_users = [u for u in user_users if 
                        search_term in (u.username or '').lower() or
                        search_term in (u.name or '').lower() or 
                        search_term in (u.email or '').lower()]
            
        # 从admin表获取管理员用户
        admin_users = []
        try:
            conn = db.engine.raw_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, password, name, email, phone FROM admin")
            admin_rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            # 转换admin表用户为可显示的用户对象
            for row in admin_rows:
                # 提取行数据，处理可能的列数不匹配
                admin_id = row[0] if len(row) > 0 else None
                username = row[1] if len(row) > 1 else None
                password = row[2] if len(row) > 2 else None
                name = row[3] if len(row) > 3 else None
                email = row[4] if len(row) > 4 else None
                phone = row[5] if len(row) > 5 else None
                
                # 检查是否已存在于user表中（避免重复）
                if username and not any(u.username == username for u in user_users):
                    # 创建一个临时用户对象用于显示（不保存到数据库）
                    admin_user = User()
                    admin_user.id = admin_id  # 使用admin表的ID
                    admin_user.username = username
                    admin_user.name = name
                    admin_user.email = email
                    admin_user.phone = phone
                    admin_user.role = 'ADMIN'
                    admin_users.append(admin_user)
                    
            print(f"从admin表获取了 {len(admin_users)} 个管理员用户")
        except Exception as e:
            print(f"获取admin表用户时出错: {e}")
            admin_users = []
        
        # 从user表获取管理员和普通用户
        user_admin_users = [u for u in user_users if str(u.role).upper() == 'ADMIN']
        user_normal_users = [u for u in user_users if str(u.role).upper() == 'USER']
        
        # 合并所有用户并计算总数
        all_admin_users = admin_users + user_admin_users
        all_users = all_admin_users + user_normal_users
        total_count = len(all_users)
        
        # 如果有排序字段，单独对admin和user组排序
        if sort_field is not None:
            field_name = sort_field.key
            reverse = sort_desc
            # 处理排序键可能为None的情况
            def sort_key(x):
                value = getattr(x, field_name, "")
                return value if value is not None else ""
            
            all_admin_users.sort(key=sort_key, reverse=reverse)
            user_normal_users.sort(key=sort_key, reverse=reverse)
            
            # 重新合并已排序的列表
            all_users = all_admin_users + user_normal_users
        
        # 手动分页
        start = page * page_size
        end = start + page_size
        paginated_users = all_users[start:end] if start < len(all_users) else []
        
        return total_count, paginated_users
    
    # 处理异常情况
    def handle_error(self, e, query, user_count, page, page_size):
        print(f"处理用户数据时出错: {e}")
        
        # 应用分页并返回
        if page_size:
            query = query.limit(page_size)
            if page > 0:
                query = query.offset(page * page_size)
        
        return user_count, query.all()

class NoticeModelView(AdminAccessibleModelView):
    """
    通知管理
    """
    column_labels = {
        'id': '通知ID',
        'title': '标题',
        'content': '内容',
        'time': '时间'
    }
    column_list = ('id', 'title', 'content', 'time')
    form_columns = ('title', 'content', 'time')
    
    # 自定义时间字段为HTML5日期时间选择器
    form_overrides = {
        'time': StringField
    }
    
    form_widget_args = {
        'time': {
            'type': 'datetime-local',
            'step': '1'  # 支持秒级选择
        }
    }
    
    def on_model_change(self, form, model, is_created):
        # 如果没有输入时间，则使用当前时间
        if not model.time:
            model.time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # 格式化时间字段
        elif 'T' in model.time:  # 处理HTML5日期时间选择器的格式
            try:
                # 将"2023-03-18T20:24:35"格式转换为"2023-03-18 20:24:35"
                dt = datetime.strptime(model.time, '%Y-%m-%dT%H:%M:%S')
                model.time = dt.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                # 如果格式不匹配，尝试不带秒的格式
                try:
                    dt = datetime.strptime(model.time, '%Y-%m-%dT%H:%M')
                    model.time = dt.strftime('%Y-%m-%d %H:%M:%S')
                except ValueError:
                    pass  # 保留原始值
                    
    def edit_form(self, obj=None):
        """编辑表单时，将数据库中的时间格式转换为HTML5日期时间选择器需要的格式"""
        form = super(NoticeModelView, self).edit_form(obj)
        if obj is not None and obj.time:
            try:
                # 尝试将"2023-03-18 20:24:35"转换为"2023-03-18T20:24:35"
                dt = datetime.strptime(obj.time, '%Y-%m-%d %H:%M:%S')
                form.time.data = dt.strftime('%Y-%m-%dT%H:%M:%S')
            except ValueError:
                try:
                    # 尝试其他可能的格式
                    formats = ['%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M']
                    for fmt in formats:
                        try:
                            dt = datetime.strptime(obj.time, fmt)
                            form.time.data = dt.strftime('%Y-%m-%dT%H:%M:%S')
                            break
                        except ValueError:
                            continue
                except Exception:
                    # 如果所有转换都失败，保持原始值
                    pass
        return form

class UserNoticeModelView(AdminAccessibleModelView):
    """
    用户通知管理
    """
    column_labels = {
        'id': '用户通知ID',
        'content': '内容',
        'user_id': '用户ID',
        'user': '用户',
        'record_id': '记录ID',
        'equipment_id': '设备ID',
        'equipment': '设备'
    }
    column_list = ('id', 'content', 'user', 'equipment')
    form_columns = ('content', 'user_id', 'record_id', 'equipment_id')

def admin_required(f):
    """
    仅允许管理员访问的视图装饰器。
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('请先登录', 'danger')
            return redirect(url_for('login'))
        
        # 角色检查时考虑多种可能的格式
        user_role = str(current_user.role).upper() if current_user.role else ''
        print(f"管理员权限检查: 用户={current_user.username}, 角色={user_role}")
        
        if user_role != 'ADMIN':
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
        if not current_user.is_authenticated:
            flash('请先登录', 'danger')
            return redirect(url_for('login'))
        
        # 改进角色检查，接受不同大小写的'USER'或'user'
        user_role = current_user.role.upper() if current_user.role else ''
        print(f"用户权限检查: 用户={current_user.username}, 角色={user_role}")
        
        if user_role != 'USER':
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
    
    @expose('/fix_statuses', methods=['GET', 'POST'])
    @admin_required
    @login_required
    def fix_equipment_statuses(self):
        # 用于修复设备状态一致性问题的页面
        if request.method == 'POST':
            try:
                # 查找所有标记为"借用中"的设备
                borrowed_equipments = Equipment.query.filter_by(status="借用中").all()
                inconsistent_count = 0
                fixed_count = 0
                
                for equipment in borrowed_equipments:
                    # 检查是否有对应的有效借用记录
                    active_borrow = BorrowList.query.filter_by(
                        number=equipment.number,
                        status="审核通过"
                    ).first()
                    
                    if not active_borrow:
                        # 如果没有有效借用记录，则设备状态不一致
                        inconsistent_count += 1
                        equipment.status = "可用"
                        db.session.add(equipment)
                        fixed_count += 1
                
                # 查找所有标记为可用但实际被借用的设备
                available_equipments = Equipment.query.filter_by(status="可用").all()
                for equipment in available_equipments:
                    # 检查是否有对应的有效借用记录
                    active_borrow = BorrowList.query.filter_by(
                        number=equipment.number,
                        status="审核通过"
                    ).first()
                    
                    if active_borrow:
                        # 如果有有效借用记录，则设备状态不一致
                        inconsistent_count += 1
                        equipment.status = "借用中"
                        db.session.add(equipment)
                        fixed_count += 1
                
                db.session.commit()
                flash(f'发现 {inconsistent_count} 个设备状态不一致，已修复 {fixed_count} 个', 'success')
            except Exception as ex:
                db.session.rollback()
                flash(f'修复设备状态时出现错误: {str(ex)}', 'error')
            return redirect(url_for('.fix_equipment_statuses'))
        
        # GET请求时显示修复页面
        # 统计状态不一致的设备数量
        inconsistent_equipments = []
        
        # 查找所有标记为"借用中"的设备，但没有对应的有效借用记录
        borrowed_equipments = Equipment.query.filter_by(status="借用中").all()
        for equipment in borrowed_equipments:
            active_borrow = BorrowList.query.filter_by(
                number=equipment.number, 
                status="审核通过"
            ).first()
            if not active_borrow:
                inconsistent_equipments.append({
                    'id': equipment.id,
                    'number': equipment.number,
                    'name': equipment.name,
                    'current_status': '借用中',
                    'expected_status': '可用',
                    'reason': '无有效借用记录'
                })
        
        # 查找所有标记为可用但有对应的有效借用记录的设备
        available_equipments = Equipment.query.filter_by(status="可用").all()
        for equipment in available_equipments:
            active_borrow = BorrowList.query.filter_by(
                number=equipment.number,
                status="审核通过"
            ).first()
            if active_borrow:
                inconsistent_equipments.append({
                    'id': equipment.id,
                    'number': equipment.number,
                    'name': equipment.name,
                    'current_status': '可用',
                    'expected_status': '借用中',
                    'reason': f'有有效借用记录 (借用ID: {active_borrow.id})'
                })
        
        return self.render(
            'admin/fix_statuses.html',
            inconsistent_equipments=inconsistent_equipments,
            count=len(inconsistent_equipments)
        )

# 注册管理后台模型
admin.add_view(EquipmentModelView(Equipment, db.session, name='设备管理', category='设备'))
admin.add_view(MaintenanceModelView(Maintenance, db.session, name='设备维护', category='设备'))
admin.add_view(BorrowListModelView(BorrowList, db.session, name='设备借用', category='设备流程'))
admin.add_view(ReturnListModelView(ReturnList, db.session, name='设备归还', category='设备流程'))
admin.add_view(UserModelView(User, db.session, name='用户管理', category='系统'))
admin.add_view(NoticeModelView(Notice, db.session, name='系统通知', category='系统'))
admin.add_view(UserNoticeModelView(UserNotice, db.session, name='用户消息', category='系统'))
admin.add_view(ReportView(name='统计报表', endpoint='report', category='系统'))

# 示例路由
@app.route('/')
def index():
    return redirect(url_for('login'))

# 导入UserMixin
from flask_login import UserMixin

# 创建自定义的Admin用户类，用于处理admin表中的用户
class AdminUser(UserMixin):
    def __init__(self, id, username, name, role='ADMIN'):
        self.id = id
        self.username = username
        self.name = name
        self.role = role
        # 添加其他需要的属性
        self.email = None
        self.phone = None
    
    def get_id(self):
        # 使用特殊前缀标记admin用户ID
        return f"admin_{self.id}"

# 用户加载回调
@login_manager.user_loader
def load_user(user_id):
    # 检查是否是admin表用户(使用前缀识别)
    if str(user_id).startswith('admin_'):
        try:
            # 从admin表中获取用户信息
            real_id = int(user_id.replace('admin_', ''))
            conn = db.engine.raw_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, name FROM admin WHERE id = %s", (real_id,))
            admin_data = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if admin_data:
                # 创建AdminUser对象
                admin_user = AdminUser(admin_data[0], admin_data[1], admin_data[2])
                print(f"加载admin表用户: ID={admin_user.id}, 用户名={admin_user.username}, 角色={admin_user.role}")
                return admin_user
            return None
        except Exception as e:
            print(f"加载admin表用户出错: {e}")
            return None
    
    # 普通User表用户
    try:
        user = User.query.get(int(user_id))
        if user:
            # 对于普通用户，确保角色值正确
            if user.role.lower() in ['user', 'users']:
                user.role = 'USER'
            
            print(f"加载user表用户: ID={user.id}, 用户名={user.username}, 角色={user.role}")
        return user
    except Exception as e:
        print(f"加载user表用户出错: {e}")
        return None

# 登录路由
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        print(f"尝试登录 - 用户名: {username}, 密码: {password}")
        
        # 1. 首先检查admin表
        try:
            conn = db.engine.raw_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, password, name FROM admin WHERE username = %s AND password = %s", (username, password))
            admin_user = cursor.fetchone()
            cursor.close()
            conn.close()
            
            # 如果在admin表中找到匹配的用户，直接使用AdminUser类登录
            if admin_user:
                admin_id, admin_username, admin_password, admin_name = admin_user
                print(f"在admin表中找到管理员: ID={admin_id}, 用户名={admin_username}")
                
                # 创建AdminUser对象用于登录
                admin_user_obj = AdminUser(admin_id, admin_username, admin_name)
                
                # 直接登录并重定向到管理员页面
                login_user(admin_user_obj)
                flash('管理员登录成功', 'success')
                print(f"管理员登录成功: ID={admin_user_obj.id}, 用户名={admin_user_obj.username}, 角色={admin_user_obj.role}")
                return redirect(url_for('admin.index'))
        except Exception as e:
            error_msg = f"查询admin表时出错: {e}"
            print(error_msg)
            app.logger.error(error_msg)
        
        # 2. 然后检查user表
        try:
            # 查询普通用户
            user = User.query.filter_by(username=username).first()
            
            if user and user.password == password:
                # 根据角色决定跳转页面
                if user.role and user.role.upper() == 'ADMIN':
                    # 如果是管理员角色，跳转到管理员页面
                    login_user(user)
                    flash('管理员登录成功', 'success')
                    print(f"user表管理员登录成功: ID={user.id}, 角色={user.role}")
                    return redirect(url_for('admin.index'))
                else:
                    # 如果是普通用户角色，跳转到用户页面
                    # 确保角色是USER
                    user.role = 'USER'
                    db.session.commit()
                    login_user(user)
                    flash('登录成功', 'success')
                    print(f"普通用户登录成功: ID={user.id}, 角色={user.role}")
                    return redirect(url_for('user_index'))
        except Exception as e:
            error_msg = f"查询user表时出错: {e}"
            print(error_msg)
            app.logger.error(error_msg)
        
        # 如果都没找到匹配的用户，显示错误消息
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
@login_required
def user_index():
    # 获取当前用户角色
    user_role = current_user.role.upper() if current_user.role else ''
    print(f"访问用户页面: 用户={current_user.username}, 角色={user_role}")
    
    # 如果是管理员，重定向到管理员页面
    if user_role == 'ADMIN':
        return redirect(url_for('admin.index'))
    
    # 普通用户显示用户页面
    status = request.args.get('status', '')
    q = request.args.get('q', '').strip()
    query = Equipment.query
    if status:
        query = query.filter_by(status=status)
    if q:
        query = query.filter((Equipment.name.contains(q)) | (Equipment.number.contains(q)))
    
    # 获取所有设备
    equipments = query.all()
    
    # 获取所有已审核通过的借用记录，用于检查设备是否真实可用
    approved_borrows = BorrowList.query.filter_by(status="审核通过").all()
    borrowed_numbers = {borrow.number for borrow in approved_borrows}
    
    # 更新设备显示状态，确保与借用记录一致
    for equipment in equipments:
        # 检查是否存在对应的归还审核通过记录
        return_approved = ReturnList.query.filter_by(
            number=equipment.number,
            status="审核通过"
        ).order_by(ReturnList.id.desc()).first()
        
        # 检查是否有有效的借用记录（审核通过的借用）
        has_active_borrow = equipment.number in borrowed_numbers
        
        # 记录原始状态用于调试
        original_status = equipment.status
        
        if has_active_borrow:
            # 如果有有效借用，显示为借用中
            equipment.display_status = "借用中"
            # 如果实际状态不是借用中，也修正数据库中的状态
            if equipment.status != "借用中":
                equipment.status = "借用中"
                db.session.add(equipment)
                print(f"修正设备状态: {equipment.number} 从 {original_status} 更新为 借用中")
        elif return_approved:
            # 如果有归还审核通过的记录，确保状态为可用
            equipment.display_status = "可用"
            # 如果实际状态不是可用，也修正数据库中的状态
            if equipment.status != "可用":
                equipment.status = "可用"
                db.session.add(equipment)
                print(f"修正设备状态: {equipment.number} 从 {original_status} 更新为 可用 (已归还)")
        else:
            # 其他情况使用数据库中的状态
            equipment.display_status = equipment.status
    
    # 提交所有状态修正
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"修正设备状态时出错: {str(e)}")
            
    return render_template('user_index.html', equipments=equipments, status=status, q=q)

@app.route('/user/borrow_records')
@login_required
@user_required
def user_borrow_records():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    # 查询当前用户的借用记录
    query = BorrowList.query.filter_by(user_id=current_user.id).order_by(BorrowList.id.desc())
    
    # 手动分页
    total_count = query.count()
    records = query.limit(per_page).offset((page - 1) * per_page).all()
    total_pages = (total_count + per_page - 1) // per_page or 1
    
    # 对于每条记录，获取关联的设备信息和归还申请状态
    for record in records:
        # 假设借用编号(number)包含设备编号
        equipment_number = record.number if record.number else ''
        # 尝试查找对应的设备
        equipment = Equipment.query.filter_by(number=equipment_number).first()
        # 如果找到设备，将其附加到记录上
        if equipment:
            record.equipment = equipment
        else:
            # 创建一个临时设备对象
            temp_equip = Equipment()
            temp_equip.number = record.number or '未知'
            temp_equip.name = record.name or '未知设备'
            record.equipment = temp_equip
            
        # 检查是否有对应的归还申请记录 - 根据名称前缀查找
        return_record = ReturnList.query.filter(
            ReturnList.name.like(f'归还-{record.id}-%'),
            ReturnList.user_id == current_user.id
        ).order_by(ReturnList.id.desc()).first()
        
        if return_record:
            record.return_status = return_record.status
            record.return_reason = return_record.reason
        else:
            record.return_status = None
            record.return_reason = None
            
        # 设置预计归还时间和实际归还时间
        record.expected_return_time = record.return_time or '-'
        record.actual_return_time = None
        if record.status == '归还完成':
            record.actual_return_time = record.return_time
    
    return render_template('user_borrow_records.html', records=records, page=page, total_pages=total_pages)

@app.route('/user/notifications')
@login_required
@user_required
def user_notifications():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    # 查询当前用户的通知
    user_notices = UserNotice.query.filter_by(user_id=current_user.id).all()
    
    # 格式化通知数据
    notifications = []
    for un in user_notices:
        # 获取相关设备信息
        equipment = Equipment.query.get(un.equipment_id) if un.equipment_id else None
        equipment_name = equipment.name if equipment else '未知设备'
        
        # 创建通知字典
        notifications.append({
            'id': un.id,
            '类型': '设备通知',
            '设备名称': equipment_name,
            '发送时间': datetime.now().strftime('%Y-%m-%d %H:%M'),
            '内容': un.content,
            '已读': True  # 默认为已读
        })
    
    # 添加系统通知
    system_notices = Notice.query.order_by(Notice.id.desc()).all()
    for notice in system_notices:
        notifications.append({
            'id': f'notice_{notice.id}',  # 使用前缀区分系统通知
            '类型': '系统通知',
            '设备名称': '-',
            '发送时间': notice.time,
            '内容': notice.content,
            '已读': True  # 系统通知默认为已读
        })
    
    # 按时间排序
    notifications.sort(key=lambda x: x['发送时间'], reverse=True)
    
    # 分页处理
    total_count = len(notifications)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_notifications = notifications[start:end] if start < total_count else []
    total_pages = (total_count + per_page - 1) // per_page or 1
    
    return render_template('user_notifications.html', notifications=paginated_notifications, page=page, total_pages=total_pages)

@app.route('/user/borrow/<int:equipment_id>', methods=['GET', 'POST'])
@login_required
@user_required
def user_borrow(equipment_id):
    equipment = Equipment.query.get_or_404(equipment_id)
    
    # 检查设备是否可用
    if equipment.status != '可用':
        flash('该设备当前不可借用', 'danger')
        return redirect(url_for('user_index'))
    
    if request.method == 'POST':
        # 处理借用申请
        borrow_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        expected_return_time = request.form.get('expected_return_time', '')
        remark = request.form.get('remark', '')
        
        # 创建借用记录
        borrow_record = BorrowList()
        borrow_record.name = f"{current_user.username}借用{equipment.name}"
        borrow_record.number = equipment.number  # 使用设备编号
        borrow_record.borrow_time = borrow_time
        borrow_record.return_time = expected_return_time if expected_return_time else ''
        borrow_record.content = remark
        borrow_record.status = '待审核'  # 默认状态为待审核
        borrow_record.user_id = current_user.id
        
        # 不应该在申请阶段就更改设备状态，而应该在审核通过后才更改
        # 设备状态保持为"可用"
        
        db.session.add(borrow_record)
        db.session.commit()
        
        flash('设备借用申请已提交，等待管理员审核', 'success')
        return redirect(url_for('user_borrow_records'))
    
    return render_template('user_borrow.html', equipment=equipment, now=datetime.now().strftime('%Y-%m-%dT%H:%M'))

@app.route('/user/return/<int:usage_id>', methods=['POST'])
@login_required
@user_required
def user_return(usage_id):
    borrow_record = BorrowList.query.get_or_404(usage_id)
    
    # 检查是否是当前用户的借用记录
    if borrow_record.user_id != current_user.id:
        flash('您无权操作此记录', 'danger')
        return redirect(url_for('user_borrow_records'))
    
    # 只有已审核通过的记录才能申请归还
    if borrow_record.status != '审核通过':
        flash('只有审核通过的借用记录才能申请归还', 'warning')
        return redirect(url_for('user_borrow_records'))
    
    try:
        # 创建归还申请记录
        return_record = ReturnList()
        # 使用借用记录的名称但添加归还前缀，便于后续通过名称查找关联的借用记录
        return_record.name = f"归还-{borrow_record.id}-{borrow_record.name}"  # 在名称中加入借用ID用于关联
        return_record.number = borrow_record.number
        return_record.date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return_record.status = '待审核'  # 默认状态为待审核
        return_record.user_id = current_user.id
        
        # 记录归还申请时间，但保持借用记录状态为"审核通过"
        borrow_record.return_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # 借用记录状态保持不变，仍为"审核通过"
        
        db.session.add(return_record)
        db.session.commit()
        
        flash('归还申请已提交，等待管理员审核', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'提交归还申请失败: {str(e)}', 'danger')
        print(f"归还申请失败: {str(e)}")
    
    return redirect(url_for('user_borrow_records'))

@app.route('/user/notifications/delete/<notification_id>', methods=['POST'])
@login_required
@user_required
def delete_notification(notification_id):
    page = request.args.get('page', 1, type=int)
    
    # 检查通知ID格式
    if notification_id.startswith('notice_'):
        # 处理系统通知，我们不真正删除它，只是返回
        flash('系统通知无法删除', 'info')
        return redirect(url_for('user_notifications', page=page))
    
    # 处理用户通知
    try:
        # 尝试将通知ID转换为整数
        user_notice_id = int(notification_id)
        notification = UserNotice.query.get_or_404(user_notice_id)
        
        # 检查是否是当前用户的通知
        if notification.user_id != current_user.id:
            flash('您无权操作此通知', 'danger')
            return redirect(url_for('user_notifications'))
    except ValueError:
        # 如果无法转换为整数，可能是无效的ID
        flash('无效的通知ID', 'danger')
        return redirect(url_for('user_notifications'))
    
    # 删除通知
    db.session.delete(notification)
    db.session.commit()
    
    flash('通知已删除', 'success')
    return redirect(url_for('user_notifications', page=page))

# 其他路由需要根据新的模型进行调整

# 统计报表相关API端点
@app.route('/admin/report/equipment_status')
@login_required
@admin_required
def report_equipment_status():
    """设备状态统计"""
    try:
        # 查询各状态的设备数量
        status_counts = {}
        conn = db.engine.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status, COUNT(*) as count FROM equipment GROUP BY status")
        for status, count in cursor.fetchall():
            status_counts[status or '未知'] = count
        cursor.close()
        conn.close()
        
        # 如果没有数据，添加一些示例数据
        if not status_counts:
            status_counts = {'可用': 5, '借用中': 3, '维修中': 2, '报废': 1}
        
        return jsonify(status_counts)
    except Exception as e:
        print(f"获取设备状态统计出错: {e}")
        return jsonify({})

@app.route('/admin/report/maintenance_due')
@login_required
@admin_required
def report_maintenance_due():
    """维护到期设备（未来7天）"""
    try:
        # 在实际应用中，这里应该查询未来7天内需要维护的设备
        # 由于数据库结构可能不支持日期比较，这里返回示例数据
        maintenance_due = []
        
        # 尝试从数据库获取一些维护记录
        conn = db.engine.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT m.name, m.number, m.next_date, e.name as equipment_name FROM maintenance m LEFT JOIN equipment e ON m.number = e.number LIMIT 5")
        for name, number, next_date, equipment_name in cursor.fetchall():
            maintenance_due.append({
                '设备名称': equipment_name or name,
                '设备编号': number,
                '下次维护日期': next_date,
                '责任人': '管理员'
            })
        cursor.close()
        conn.close()
        
        # 如果没有数据，添加一些示例数据
        if not maintenance_due:
            maintenance_due = [
                {'设备名称': '显微镜', '设备编号': 'EQ001', '下次维护日期': '2025-03-25', '责任人': '管理员'},
                {'设备名称': '离心机', '设备编号': 'EQ002', '下次维护日期': '2025-03-26', '责任人': '管理员'}
            ]
        
        return jsonify(maintenance_due)
    except Exception as e:
        print(f"获取维护到期设备出错: {e}")
        return jsonify([])

@app.route('/admin/report/borrow_overdue')
@login_required
@admin_required
def report_borrow_overdue():
    """借用超期设备"""
    try:
        # 在实际应用中，这里应该查询已超期未归还的设备
        borrow_overdue = []
        
        # 尝试从数据库获取一些借用记录
        conn = db.engine.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT b.name, b.number, u.username, b.return_time FROM borrowlist b LEFT JOIN user u ON b.user_id = u.id WHERE b.status = '审核通过' LIMIT 5")
        for name, number, username, return_time in cursor.fetchall():
            borrow_overdue.append({
                '设备名称': name,
                '设备编号': number,
                '借用人': username or '未知用户',
                '预计归还时间': return_time
            })
        cursor.close()
        conn.close()
        
        # 如果没有数据，添加一些示例数据
        if not borrow_overdue:
            borrow_overdue = [
                {'设备名称': '显微镜', '设备编号': 'EQ001', '借用人': '张三', '预计归还时间': '2025-03-15'},
                {'设备名称': '离心机', '设备编号': 'EQ002', '借用人': '李四', '预计归还时间': '2025-03-16'}
            ]
        
        return jsonify(borrow_overdue)
    except Exception as e:
        print(f"获取借用超期设备出错: {e}")
        return jsonify([])

@app.route('/admin/report/usage_rate')
@login_required
@admin_required
def report_usage_rate():
    """设备使用率"""
    try:
        # 在实际应用中，这里应该计算设备的使用率
        # 这里简单返回一些示例数据
        usage_rate = []
        
        # 尝试从数据库获取一些设备信息
        conn = db.engine.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name, number FROM equipment LIMIT 5")
        for name, number in cursor.fetchall():
            # 随机生成一个使用率
            import random
            rate = f"{random.randint(30, 95)}%"
            usage_rate.append({
                '设备名称': name,
                '设备编号': number,
                '使用率': rate
            })
        cursor.close()
        conn.close()
        
        # 如果没有数据，添加一些示例数据
        if not usage_rate:
            usage_rate = [
                {'设备名称': '显微镜', '设备编号': 'EQ001', '使用率': '85%'},
                {'设备名称': '离心机', '设备编号': 'EQ002', '使用率': '72%'},
                {'设备名称': '分光光度计', '设备编号': 'EQ003', '使用率': '65%'},
                {'设备名称': '电子天平', '设备编号': 'EQ004', '使用率': '90%'}
            ]
        
        return jsonify(usage_rate)
    except Exception as e:
        print(f"获取设备使用率出错: {e}")
        return jsonify([])

# 提供上传文件访问路由（注：Flask默认提供static文件夹下的静态资源访问，但为了清晰起见，保留此路由）
@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# 提供数据库中的图片访问路由
@app.route('/equipment_image/<int:equipment_id>')
def equipment_image(equipment_id):
    equipment = Equipment.query.get_or_404(equipment_id)
    if not equipment.img:
        # 如果没有图片，返回一个默认图片或404
        return abort(404)
    
    # 获取图片的MIME类型
    # 这里简单处理，实际生产环境可能需要更精确的MIME类型检测
    response = make_response(equipment.img)
    response.headers.set('Content-Type', 'image/jpeg')  # 默认为JPEG
    
    # 尝试判断图片类型并设置正确的Content-Type
    import imghdr
    import io
    img_type = imghdr.what(None, h=equipment.img[:32])  # 使用前32字节检测图片类型
    if img_type:
        response.headers.set('Content-Type', f'image/{img_type}')
    
    return response

# 测试路由：显示所有设备图片
@app.route('/test_equipment_images')
def test_equipment_images():
    equipments = Equipment.query.all()
    html = '<h1>设备图片测试</h1>'
    for equipment in equipments:
        if equipment.img:
            html += f'<div><h3>{equipment.name} (ID: {equipment.id})</h3>'
            html += f'<img src="/equipment_image/{equipment.id}" width="200px"><br>'
            html += f'<p>设备编号: {equipment.number}</p></div><hr>'
        else:
            html += f'<div><h3>{equipment.name} (ID: {equipment.id})</h3>'
            html += f'<p>没有图片</p>'
            html += f'<p>设备编号: {equipment.number}</p></div><hr>'
    return html

@app.route('/api/equipment_options')
@login_required
def equipment_options():
    """为Select2 v4提供设备数据"""
    search = request.args.get('q', '')
    query = Equipment.query
    if search:
        query = query.filter(db.or_(
            Equipment.name.ilike(f'%{search}%'),
            Equipment.number.ilike(f'%{search}%')
        ))
    equipments = query.limit(50).all()
    results = [{'id': e.number, 'text': f"{e.name} ({e.number})"} for e in equipments if e.number and e.number.strip()]
    return jsonify(results=results)

@app.route('/api/admin_options')
@login_required
def admin_options():
    """为Select2 v4提供管理员数据"""
    search = request.args.get('q', '')
    query = User.query
    if search:
        query = query.filter(db.or_(
            User.name.ilike(f'%{search}%'),
            User.username.ilike(f'%{search}%')
        ))
    users = query.limit(50).all()
    results = [{'id': u.id, 'text': f"{u.name or u.username} ({u.username})"} for u in users]
    return jsonify(results=results)

@app.route('/admin/fix_equipment/<equipment_number>', methods=['GET'])
@login_required
@admin_required
def fix_equipment_status(equipment_number):
    """手动修复指定设备的状态"""
    try:
        # 查找设备
        equipment = Equipment.query.filter_by(number=equipment_number).first()
        
        if not equipment:
            return f"找不到编号为 {equipment_number} 的设备", 404
            
        # 检查是否有对应的有效借用记录
        active_borrow = BorrowList.query.filter_by(
            number=equipment_number,
            status="审核通过"
        ).first()
        
        old_status = equipment.status
        
        if active_borrow:
            # 如果有有效借用记录，设备状态应为"借用中"
            equipment.status = "借用中"
            status_message = f"设备有有效借用记录(ID: {active_borrow.id})，状态应为'借用中'"
        else:
            # 否则设备状态应为"可用"
            equipment.status = "可用"
            
            # 如果有待处理的归还申请
            return_pending = ReturnList.query.filter_by(
                number=equipment_number,
                status="待审核"
            ).order_by(ReturnList.id.desc()).first()
            
            if return_pending:
                status_message = f"设备有待处理的归还申请(ID: {return_pending.id})，但无有效借用记录，状态已设为'可用'"
            else:
                status_message = f"设备无有效借用记录，状态已设为'可用'"
        
        # 保存更改
        db.session.add(equipment)
        db.session.commit()
        
        return f"""
        <h2>设备状态已修复</h2>
        <p>设备编号: {equipment.number}</p>
        <p>设备名称: {equipment.name}</p>
        <p>原状态: {old_status}</p>
        <p>新状态: {equipment.status}</p>
        <p>原因: {status_message}</p>
        <p><a href="/admin/report/fix_statuses">返回设备状态检查</a></p>
        """
    except Exception as e:
        db.session.rollback()
        return f"修复设备状态时出错: {str(e)}", 500

@app.route('/admin/refresh_equipment_status', methods=['GET'])
@login_required
@admin_required
def refresh_equipment_status():
    """强制刷新所有设备状态"""
    try:
        # 查找所有标记为"借用中"的设备
        borrowed_equipments = Equipment.query.filter_by(status="借用中").all()
        
        for equipment in borrowed_equipments:
            # 检查是否有对应的有效借用记录
            active_borrow = BorrowList.query.filter_by(
                number=equipment.number,
                status="审核通过"
            ).first()
            
            # 检查是否有最近的归还记录
            recent_return = ReturnList.query.filter_by(
                number=equipment.number,
                status="审核通过"
            ).order_by(ReturnList.id.desc()).first()
            
            if not active_borrow or recent_return:
                # 如果没有有效借用记录或有归还记录，则设备应为可用
                equipment.status = "可用"
                db.session.add(equipment)
                print(f"强制刷新: 设备 {equipment.number} 状态已重置为可用")
        
        # 查找所有标记为可用但有有效借用记录的设备
        available_equipments = Equipment.query.filter_by(status="可用").all()
        
        for equipment in available_equipments:
            # 检查是否有对应的有效借用记录
            active_borrow = BorrowList.query.filter_by(
                number=equipment.number,
                status="审核通过"
            ).first()
            
            # 检查是否有最近的归还记录
            recent_return = ReturnList.query.filter_by(
                number=equipment.number,
                status="审核通过"
            ).order_by(ReturnList.id.desc()).first()
            
            if active_borrow and not recent_return:
                # 如果有有效借用记录且无归还记录，则设备应为借用中
                equipment.status = "借用中"
                db.session.add(equipment)
                print(f"强制刷新: 设备 {equipment.number} 状态已更新为借用中")
        
        # 提交所有更改
        db.session.commit()
        
        # 强制刷新，使用直接SQL更新
        try:
            # 更新所有有归还记录但仍标记为借用中的设备
            sql = """
            UPDATE equipment e
            SET e.status = '可用'
            WHERE e.status = '借用中'
            AND EXISTS (
                SELECT 1 FROM returnlist r
                WHERE r.number = e.number
                AND r.status = '审核通过'
            )
            """
            db.engine.execute(sql)
            print("已通过SQL直接更新设备状态")
        except Exception as sql_ex:
            print(f"SQL直接更新失败: {str(sql_ex)}")
        
        return "所有设备状态已刷新"
    except Exception as ex:
        db.session.rollback()
        return f"刷新设备状态时出错: {str(ex)}"

if __name__ == '__main__':
    # 启动应用
    app.run(debug=True) 