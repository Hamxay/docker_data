from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from app.extensions import db
from app.models.user import User
from app.models.item import Item
from app.models.manufacturing_code import ManufacturingCode
from app.models.plan import Plan
from app.models.requirement import Requirement
from app.models.secondary_code import SecondaryCode


class CustomModelView(ModelView):
    """Базовый класс для всех представлений Flask-Admin."""
    def is_accessible(self):
        # Здесь вы можете добавить проверку авторизации
        return True

    def inaccessible_callback(self, name, **kwargs):
        # Здесь вы можете указать, куда перенаправить неавторизованных пользователей
        return "Access Denied"


class UserAdmin(CustomModelView):
    """Представление для модели User."""
    column_list = ('id', 'email', 'university_name', 'is_active', 'date_created', 'last_active')
    form_columns = ('email', 'password', 'university_name', 'is_active')


from flask_admin.contrib.sqla import ModelView

class ItemAdmin(CustomModelView):
    """Admin view for the Item model."""
    # Отображение всех колонок в админской панели
    column_list = (
        'id', 'display', 'code_name', 'units', 'predecessor', 
        'simultaneous', 'item_group_id', 'terms', 'standing', 
        'original_predecessor', 'original_simultaneous'
    )

    # Поля, доступные для редактирования
    form_columns = (
        'display', 'code_name', 'units', 'predecessor', 
        'simultaneous', 'item_group_id', 'terms', 'standing', 
        'original_predecessor', 'original_simultaneous'
    )

class ManufacturingCodeAdmin(CustomModelView):
    """Представление для модели ManufacturingCode."""
    column_list = ('id', 'item_group_id', 'code_name')
    form_columns = ('item_group_id', 'code_name')


class PlanAdmin(CustomModelView):
    """Представление для модели Plan."""
    column_list = ('id', 'user_id', 'plan_name')
    form_columns = ('user_id', 'plan_name', 'items')


class RequirementAdmin(CustomModelView):
    """Представление для модели Requirement."""
    column_list = ('id', 'code_name', 'course_id', 'course_name', 'credit_hours')
    form_columns = ('code_name', 'course_id', 'course_name', 'credit_hours')


class SecondaryCodeAdmin(CustomModelView):
    """Представление для модели SecondaryCode."""
    column_list = ('id', 'item_group_id', 'code_name')
    form_columns = ('item_group_id', 'code_name')


def setup_admin(app):
    """Функция для настройки админской панели."""
    admin = Admin(app, name='Admin Panel', template_mode='bootstrap4')

    # Добавляем модели в админку
    admin.add_view(UserAdmin(User, db.session))
    admin.add_view(ItemAdmin(Item, db.session))
    admin.add_view(ManufacturingCodeAdmin(ManufacturingCode, db.session))
    admin.add_view(PlanAdmin(Plan, db.session))
    admin.add_view(RequirementAdmin(Requirement, db.session))
    admin.add_view(SecondaryCodeAdmin(SecondaryCode, db.session))

    return admin