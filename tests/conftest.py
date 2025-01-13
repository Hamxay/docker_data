# tests/conftest.py

import warnings

# === 1. Подавление конкретных DeprecationWarning перед любыми импортами ===

# Подавляем DeprecationWarning из pkg_resources

warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    message=r".*Using the initialization functions in flask_caching.backend is deprecated.*"
)

warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    module=r".*pkg_resources.*"
)

# Подавляем DeprecationWarning из flask_admin и его модуля contrib
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    module=r".*flask_admin.*"
)

# Подавляем DeprecationWarning из flask_caching
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    module=r".*flask_caching.*"
)

import pytest
import shutil
import os
from app.config import TestConfig

@pytest.fixture(scope='session')
def app():
    """Создание и настройка приложения для тестов."""
    from app import create_app, db  # Импорт после установки TestConfig

    # Определяем пути к оригинальной и тестовой базам данных
    original_db_path = os.path.join(TestConfig.BASEDIR, 'database', 'database.db')
    test_db_path = os.path.join(TestConfig.BASEDIR, 'database', 'test_database.db')
    
    # Проверяем, существует ли оригинальная база данных
    if not os.path.exists(original_db_path):
        raise FileNotFoundError(f"Оригинальная база данных не найдена по пути {original_db_path}")

    # Удаляем тестовую базу данных, если она уже существует
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    
    # Копируем оригинальную базу данных в тестовую
    shutil.copyfile(original_db_path, test_db_path)
    
    # Обновляем TestConfig для использования тестовой базы данных
    TestConfig.SQLALCHEMY_DATABASE_URI = f'sqlite:///{test_db_path}'
    
    # Создаем Flask приложение с уже установленной TestConfig
    app = create_app()
    
    with app.app_context():
        # Не нужно повторно инициализировать db, так как это делается в create_app()
        yield app  # Предоставляем приложение для тестов
    
    # === 3. Очистка: удаляем тестовую базу данных после тестов ===
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

@pytest.fixture(scope='session')
def test_client(app):
    """Создание тестового клиента для приложения."""
    return app.test_client()

@pytest.fixture(scope='session')
def init_database(app):
    """Инициализация базы данных для тестов."""
    from app import db
    with app.app_context():
        # Опционально: убедитесь, что схема базы данных корректна
        # db.create_all()  # Только если необходимо
        yield db  # Предоставляем базу данных для тестов

        # Не удаляем таблицы, чтобы сохранить состояние тестовой базы данных
        # db.session.remove()
        # db.drop_all()
