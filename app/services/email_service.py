from flask import current_app, jsonify
from flask_mail import Message
import jwt, os
from app import mail

def send_email(data):
    token = data.get('token')
    if not token:
        return jsonify(message="Token is missing", success=False)

    current_user = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
    sender = os.getenv('MAIL_USERNAME')
    email_body = data['body']
    email_subject = data['subject']

    try:
        email = Message(email_subject, sender=sender, recipients=[current_user["user_email"]])
        email.body = email_body
        mail.send(email)
        return jsonify(message="Email sent successfully.", success=True)
    except Exception as e:
        return jsonify(message="Error in sending email.", error=str(e), success=False)
