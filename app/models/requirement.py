from app.extensions import db

class Requirement(db.Model):
    __tablename__ = 'requirements'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    code_name = db.Column(db.String, index=True)
    course_id = db.Column(db.String, index=True)
    course_name = db.Column(db.String)
    credit_hours = db.Column(db.Float)

    def to_dict(self):
        return {
            'id': self.id,
            'code_name': self.code_name,
            'course_id': self.course_id,
            'course_name': self.course_name,
            'credit_hours': self.credit_hours,
        }

    @classmethod
    def get_requirements_by_code_names(cls, code_names=None):
        if not code_names:
            requirements = cls.query.all()
        else:
            requirements = cls.query.filter(cls.code_name.in_(code_names)).all()
        return [requirement.to_dict() for requirement in requirements]
    
    @classmethod
    def get_requirements_by_course_ids(cls, course_ids=None):
        if not course_ids:
            requirements = cls.query.all()
        else:
            requirements = cls.query.filter(cls.course_id.in_(course_ids)).all()
        return [requirement.to_dict() for requirement in requirements]
    
    @classmethod
    # @cache.memoize(timeout=60)
    def get_required_fields(cls):
        query = cls.query.all()
        return [{'code_name': req.code_name, 'course_id': req.course_id} for req in query]