# app/models/manufacturing_code.py
from app.extensions import db

class ManufacturingCode(db.Model):
    __tablename__ = 'manufacturing_codes'
    id = db.Column(db.BigInteger, primary_key=True)
    item_group_id = db.Column(db.String, unique=True)
    code_name = db.Column(db.String)

    def __str__(self):
        return f'{self.item_group_id} ({self.code_name})'
    
    # Опционально, можно также переопределить __repr__ для дополнительной информации
    def __repr__(self):
        return f'<ManufacturingCode {self.item_group_id} ({self.code_name})>'
