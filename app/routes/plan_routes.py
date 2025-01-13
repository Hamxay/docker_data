from flask import Blueprint, request, jsonify, current_app
from app.utils.auth_middleware import token_required
from app.services.plan_service import PlanManager
from flask_caching import Cache

plan_bp = Blueprint('plan', __name__)

def make_cache_key():
    data = request.data
    return f"cache_key:{hash(frozenset(data))}"

def make_cache_user_key():
    form_data = request.form.to_dict(flat=True)
    user_token = None
    if "Authorization" in request.headers:
        user_token = request.headers["Authorization"].split(" ")[1]
    combined_data = frozenset(form_data.items()) | frozenset({'user_token': user_token}.items())
    return f"cache_key:{hash(combined_data)}"

with current_app.app_context():
    cache = Cache(current_app)

plan_manager = PlanManager()

@plan_bp.route('/create-plan', methods=['POST'])
@cache.cached(timeout=86400, key_prefix=make_cache_key)
def create_plan_route():
    return plan_manager.create_plan(request)

@plan_bp.route('/get-plans', methods=['GET'])
@token_required
def get_plans_route():
    return plan_manager.get_plans(request)

@plan_bp.route('/get-single-plan', methods=['POST'])
@cache.cached(timeout=86400, key_prefix=make_cache_user_key)
@token_required
def get_single_plan_route():
    return plan_manager.get_single_plan(request)

@plan_bp.route('/save-plan', methods=['POST'])
@token_required
def save_plan_route():
    return plan_manager.save_plan(request)

@plan_bp.route('/update-plan', methods=['POST'])
@token_required
def update_plan_route():
    return plan_manager.update_plan(request)

@plan_bp.route('/delete-plans', methods=['POST'])
@token_required
def delete_plans_route():
    return plan_manager.delete_plans(request)

@plan_bp.route('/get-codes')
def get_codes_route():
    return plan_manager.get_codes()

@plan_bp.route('/check-plan', methods=['POST'])
@token_required
def check_plan_route():
    return plan_manager.check_plan(request)

@plan_bp.route('/clear-cache')
def clear_cache():
    with current_app.app_context():
        cache.clear()
    return jsonify({'status': 'success', 'message': 'Cache cleared'})