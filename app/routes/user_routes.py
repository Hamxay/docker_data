from flask import Blueprint, request, jsonify, session, current_app
from app.services.user_service import login, signup, reset_email, reset_password, check_user_login, logout
from app.utils.auth_middleware import token_required

user_bp = Blueprint('user', __name__)

@user_bp.route("/login", methods=["POST"])
def login_route():
    return login(request)

@user_bp.route('/signup', methods=['POST'])
def signup_route():
    return signup(request)

@user_bp.route("/confirm_email", methods=["POST"])
def reset_email_route():
    return reset_email(request)

@user_bp.route("/reset_password", methods=["POST"])
def reset_password_route():
    return reset_password(request)

@user_bp.route("/check_user_login", methods=["GET"])
@token_required
def check_user_login_route():
    return check_user_login(request)

@user_bp.route('/logout')
@token_required
def logout_route():
    return logout()
