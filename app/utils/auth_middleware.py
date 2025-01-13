import json
from functools import wraps
from flask import request, current_app
import jwt
from app.models import User

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if "Authorization" in request.headers:
            token = request.headers["Authorization"].split(" ")[1]
        if not token:
            return {
                       "message": "Authentication Token is missing!",
                       "data": None,
                       "error": "Unauthorized"
                   }, 401
        try:
            # Decode token
            data = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
            
            # Check if user exists
            current_user = User.query.filter_by(email=data["user_email"]).first()
            if current_user is None:
                return {
                           "message": "Invalid Authentication token!",
                           "data": None,
                           "error": "Unauthorized"
                       }, 401

        except jwt.ExpiredSignatureError:
            return {
                       "message": "Token has expired!",
                       "data": None,
                       "error": "Unauthorized"
                   }, 401

        except jwt.InvalidTokenError:
            return {
                       "message": "Invalid token!",
                       "data": None,
                       "error": "Unauthorized"
                   }, 401

        except Exception as e:
            return {
                       "message": "Something went wrong",
                       "data": None,
                       "error": str(e)
                   }, 500
        return f()

    return decorated