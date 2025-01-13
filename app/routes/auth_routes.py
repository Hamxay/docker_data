from flask import Blueprint, request, jsonify, current_app, session
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from app.models import User
from app import db
from app.utils.auth_middleware import token_required
import json

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/check_user_login", methods=["GET"])
@token_required
def check_user_login():
    token = request.headers.get("Authorization", "").split(" ")[1]
    if not token:
        return jsonify(message="Authentication Token is missing!", isAuthenticated=False), 401

    try:
        data = jwt.decode(json.loads(token), current_app.config["SECRET_KEY"], algorithms=["HS256"])
        current_user = User.query.filter_by(email=data["user_email"]).first()
        if current_user is None:
            return jsonify(message="Invalid Authentication token!", isAuthenticated=False), 401
        return jsonify(message="Authentic User", isAuthenticated=True)

    except Exception as e:
        return jsonify(message="Something went wrong", error=str(e), isAuthenticated=False), 500

@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.form
    email = data.get('email')
    password = data.get('password')

    user = User.query.filter_by(email=email).first()
    if user and check_password_hash(user.password, password):
        session["logged_in"] = True
        token = jwt.encode({"user_email": email}, current_app.config["SECRET_KEY"], algorithm="HS256")
        return jsonify(success=True, token=token)
    return jsonify(message='Invalid email or password', success=False)

@auth_bp.route("/signup", methods=["POST"])
def signup():
    data = request.form
    university = data['university']
    email = data['email']
    password = data['password']
    verificationEmail = data['password']

    if User.query.filter_by(email=email).first():
        return jsonify(status_code=201, result='error', message='email already exist')

    hashed_password = generate_password_hash(password)
    new_user = User(email=email, password=hashed_password, university_name=university, verificationEmail=verificationEmail)
    db.session.add(new_user)
    db.session.commit()

    return jsonify(status_code=201, result='success', message='User Registered Successfully')