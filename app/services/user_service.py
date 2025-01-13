# app/services/user_service.py
from flask import jsonify, current_app, session
from werkzeug.security import generate_password_hash, check_password_hash
from app.models import User
from app.extensions import db  # Импортируем db из extensions
from flask_mail import Message
import jwt
import os
import json

def login(request):
    data = request.form
    if not data:
        return jsonify(message="Please provide user details", data=None, error="Bad request", success=False), 400

    email = data.get('email')
    password = data.get('password')

    user = User.query.filter_by(email=email).first()
    if user and user.check_password(password):     
        session["admin_logged_in"] = True
        user.last_active = db.func.current_timestamp()
        db.session.commit()
    else:
        return jsonify(message='Invalid email or password', data=None, error=False, success=False)

    if not user.is_active:
        if data.get('token') != "undefined":
            try:
                token_data = jwt.decode(data['token'], current_app.config["SECRET_KEY"], algorithms=["HS256"])
                if token_data["user_email"] == email:
                    user.is_active = True
                    db.session.commit()

                    token = jwt.encode({"user_email": email}, current_app.config["SECRET_KEY"], algorithm="HS256")
                    return jsonify(error=None, success=True, message="Successfully fetched auth token", data={"is_active": 1, "token": token})

            except Exception as e:
                return jsonify(message="Invalid Authentication url!", data=None, error=str(e)), 200

    try:
        token = jwt.encode({"user_email": email}, current_app.config["SECRET_KEY"], algorithm="HS256")
        return jsonify(error=None, success=True, message="Successfully fetched auth token", data={"is_active": user.is_active, "token": token})
    except Exception as e:
        return jsonify(error="Something went wrong", success=False, message=str(e), data=None), 500

def signup(request):
    data = request.form
    university = data.get('university')
    email = data.get('email')
    verificationEmail = data.get('verificationEmail')
    password = data.get('password')

    user = User.query.filter_by(email=email).first()
    if user:
        return jsonify(status_code=201, result='error', message='email already exist')

    hashed_password = generate_password_hash(password)
    new_user = User(verificationEmail=verificationEmail, email=email, password=hashed_password, university_name=university, is_active=1)
    db.session.add(new_user)
    db.session.commit()
    return jsonify(status_code=201, result='success', message='User Registered Successfully')

def reset_email(data):
    email = data.get('email')
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify(message='User not found', data=None, error=False, success=False)

    try:
        token = jwt.encode({"user_email": email}, current_app.config["SECRET_KEY"], algorithm="HS256")
        sender = os.environ.get('MAIL_USERNAME')
        email_body = f"{os.environ.get('URL')}reset-password/?token={token}"
        email_subject = "AutoGrad Password Reset"
        email_msg = Message(email_subject, sender=sender, recipients=[email])
        email_msg.body = email_body
        mail.send(email_msg)
        return jsonify(status_code=201, error=None, message="Reset email sent to your email.", success=True)
    except Exception as e:
        return jsonify(error="Something went wrong", success=False, message=str(e), data=None), 500

def reset_password(request):
    data = request.form
    email = data.get('email')
    password = data.get('password')
    token = data.get('token')

    try:
        token_data = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
        user = User.query.filter_by(email=token_data["user_email"]).first()
        if not user:
            return jsonify(message="Invalid Authentication token!", data=None, error="Unauthorized"), 401

        user.password = generate_password_hash(password)
        db.session.commit()
        return jsonify(status_code=201, error=None, message="Password reset successfully.", success=True)
    except Exception as e:
        return jsonify(message="Something went wrong", data=None, error=str(e)), 500

def check_user_login(request):
    token = None
    if "Authorization" in request.headers:
        token = request.headers["Authorization"].split(" ")[1]
    if not token:
        return {
            "message": "Authentication Token is missing!",
            "data": None,
            "error": "Unauthorized",
            "isAuthenticated": False
        }, 401
    try:
        data = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
        current_user = User.query.filter_by(email=data["user_email"]).first()
        if current_user is None:
            return {
                "message": "Invalid Authentication token!",
                "data": None,
                "error": "Unauthorized",
                "isAuthenticated": False
            }
        else:
            return {
                "message": "Authentic User",
                "data": None,
                "error": None,
                "isAuthenticated": True
            }
    except Exception as e:
        return {
            "message": "Something went wrong",
            "data": None,
            "error": str(e),
            "isAuthenticated": False
        }, 500

def logout():
    session.clear()
    return jsonify(error=None, success=True, message="Successfully logged out", data=None)
