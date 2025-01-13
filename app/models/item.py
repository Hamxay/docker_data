from app.extensions import db
import json

class Item(db.Model):
    __tablename__ = 'items'
    id = db.Column(db.BigInteger, primary_key=True)
    display = db.Column(db.String)
    code_name = db.Column(db.String)
    units = db.Column(db.Float)
    predecessor = db.Column(db.String)
    simultaneous = db.Column(db.String)
    item_group_id = db.Column(db.String)  # Убрана связь ForeignKey
    terms = db.Column(db.String)
    standing = db.Column(db.String)
    original_predecessor = db.Column(db.String)
    original_simultaneous = db.Column(db.String)

    # Убрана relationship
    @property
    def predecessor_human(self):
        """Преобразует JSON строку в человеко-читаемый формат."""
        if self.predecessor:
            try:
                data = json.loads(self.predecessor)
                parts = []
                for item in data:
                    if ',' in item:
                        sub_items = item.split(', ')
                        parts.append('(' + ' or '.join(sub_items) + ')')
                    else:
                        parts.append(item)
                return ' and '.join(parts).strip('()')
            except json.JSONDecodeError:
                return self.predecessor
        return ''

    @predecessor_human.setter
    def predecessor_human(self, value):
        """Преобразует человеко-читаемый формат обратно в JSON строку."""
        if value:
            and_parts = value.split(' and ')
            data = []
            for part in and_parts:
                part = part.strip('()')
                or_parts = part.split(' or ')
                data.append(', '.join(or_parts))
            self.predecessor = json.dumps(data)
        else:
            self.predecessor = None

    @property
    def simultaneous_human(self):
        """Преобразует JSON строку в человеко-читаемый формат."""
        if self.simultaneous:
            try:
                data = json.loads(self.simultaneous)
                parts = []
                for item in data:
                    if ',' in item:
                        sub_items = item.split(', ')
                        parts.append('(' + ' or '.join(sub_items) + ')')
                    else:
                        parts.append(item)
                return ' and '.join(parts).strip('()')
            except json.JSONDecodeError:
                return self.simultaneous
        return ''

    @simultaneous_human.setter
    def simultaneous_human(self, value):
        """Преобразует человеко-читаемый формат обратно в JSON строку."""
        if value:
            and_parts = value.split(' and ')
            data = []
            for part in and_parts:
                part = part.strip('()')
                or_parts = part.split(' or ')
                data.append(', '.join(or_parts))
            self.simultaneous = json.dumps(data)
        else:
            self.simultaneous = None