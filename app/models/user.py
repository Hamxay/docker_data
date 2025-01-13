from app.extensions import db

class User(db.Model):
    __tablename__ = 'Users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(64))
    university_name = db.Column(db.String(32))
    is_active = db.Column(db.Integer)
    date_created = db.Column(db.DateTime)
    last_active = db.Column(db.DateTime)
    verificationEmail = db.Column(db.String(255))