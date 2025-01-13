# app/__init__.py
import os
from flask import Flask, jsonify
from flask_cors import CORS
from flask_admin import Admin
from dotenv import load_dotenv
from app.config import Config
from flask_compress import Compress
from app.extensions import db, mail, migrate
from app.admin_views import setup_admin

load_dotenv()

def create_app():
    app = Flask(__name__)
    Compress(app)
    app.config.from_object(Config)
    app.config['CACHE_TYPE'] = 'simple'  # Simple in-memory cache
    app.config['CACHE_DEFAULT_TIMEOUT'] = 300  # Default cache timeout in seconds
    app.config['COMPRESS_MIMETYPES'] = ['text/html', 'text/css', 'application/json']
    app.config['COMPRESS_LEVEL'] = 6  # Уровень сжатия (по умолчанию 6)
    app.config['COMPRESS_MIN_SIZE'] = 500  # Минимальный размер ответа для сжатия

    if os.getenv('FLASK_ENV') == 'production':
        db_path = '/app/database.db'
    else:
        db_path = os.path.join(os.path.dirname(__file__), 'database/database.db')
    
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    db.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)

    CORS(app, resources={r"/*": {"origins": "*"}})

    # Import models after initializing db
    from app.models import User, Item, ManufacturingCode, SecondaryCode, Plan, Requirement

    # Add admin views
    setup_admin(app)

    with app.app_context():
        from app.routes.auth_routes import auth_bp
        from app.routes.user_routes import user_bp
        from app.routes.plan_routes import plan_bp
        from app.routes.email_routes import email_bp

        app.register_blueprint(auth_bp)
        app.register_blueprint(user_bp, name="user_unique1")
        app.register_blueprint(plan_bp, name='plan_unique')
        app.register_blueprint(email_bp)

        # db.create_all()  # Ensure this does not cause issues with existing databases

    @app.route('/', methods=['GET'])
    def health_check():
        return "All Work", 200

    return app
