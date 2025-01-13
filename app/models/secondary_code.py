from app.extensions import db

class SecondaryCode(db.Model):
    __tablename__ = 'secondary_codes'
    id = db.Column(db.BigInteger, primary_key=True)
    item_group_id = db.Column(db.String)
    code_name = db.Column(db.String)