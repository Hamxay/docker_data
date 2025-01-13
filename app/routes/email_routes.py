from flask import Blueprint, request, jsonify, current_app
from app.utils.auth_middleware import token_required
from app.services.email_service import send_email

email_bp = Blueprint('email', __name__)

@email_bp.route('/send_email', methods=['POST'])
@token_required
def send_email_route():
    data = request.form
    return send_email(data)