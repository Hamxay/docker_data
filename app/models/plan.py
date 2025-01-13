from app.extensions import db

class Plan(db.Model):
    __tablename__ = 'plans'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('Users.id'))
    plan_name = db.Column(db.String)
    items = db.Column(db.JSON)