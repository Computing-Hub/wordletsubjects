"""Database tables.

Privacy: no student names are stored anywhere. Students are known only by a
random code that the teacher hands out; the teacher keeps the code-to-name list.
"""
import secrets
from datetime import datetime, timezone

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)  # stored as naive UTC


class Teacher(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(80), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    # Comma-separated subject ids this teacher may add terms to, or "*" for all.
    subjects = db.Column(db.String(500), default="", nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    must_change_password = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=now, nullable=False)

    classes = db.relationship("SchoolClass", back_populates="teacher", lazy="dynamic")

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    @property
    def is_active(self):  # Flask-Login: deactivated teachers can't log in
        return self.active

    def subject_ids(self):
        return {s.strip() for s in self.subjects.split(",") if s.strip()}

    def can_edit(self, subject_id):
        ids = self.subject_ids()
        return "*" in ids or subject_id in ids


class Draft(db.Model):
    """One row of a word bank, waiting to be sent for review.

    Rows that belong together (a new term plus its extra follow-up questions)
    share an entry_id so they are shown, edited and deleted as one.
    """
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teacher.id"), nullable=False, index=True)
    subject_id = db.Column(db.String(60), nullable=False)
    entry_id = db.Column(db.String(32), nullable=False, index=True)
    position = db.Column(db.Integer, default=0, nullable=False)
    term = db.Column(db.String(120), nullable=False)
    clue = db.Column(db.Text, default="")      # blank = extra follow-up for an existing term
    topic = db.Column(db.String(120), default="")
    tier = db.Column(db.String(1), default="")
    question = db.Column(db.Text, nullable=False)
    correct_answer = db.Column(db.Text, nullable=False)
    wrong_1 = db.Column(db.Text, nullable=False)
    wrong_2 = db.Column(db.Text, nullable=False)
    wrong_3 = db.Column(db.Text, nullable=False)
    explanation = db.Column(db.Text, nullable=False)
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    submission_id = db.Column(db.Integer, db.ForeignKey("submission.id"), nullable=True)

    teacher = db.relationship("Teacher")


class Submission(db.Model):
    """A batch of drafts sent to GitHub as one pull request."""
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teacher.id"), nullable=False, index=True)
    subject_id = db.Column(db.String(60), nullable=False)
    rows = db.Column(db.Integer, nullable=False)
    terms = db.Column(db.Text, default="")    # comma list, for display
    path = db.Column(db.String(255), default="")
    pr_number = db.Column(db.Integer, nullable=True)
    pr_url = db.Column(db.String(255), default="")
    status = db.Column(db.String(20), default="open")  # open, merged, closed, local
    checked_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=now, nullable=False)

    teacher = db.relationship("Teacher")
    drafts = db.relationship("Draft", backref="submission")


class SchoolClass(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    prefix = db.Column(db.String(6), nullable=False)
    subject_id = db.Column(db.String(60), default="")  # default filter on the dashboard
    teacher_id = db.Column(db.Integer, db.ForeignKey("teacher.id"), nullable=False, index=True)
    archived = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=now, nullable=False)

    teacher = db.relationship("Teacher", back_populates="classes")
    codes = db.relationship("StudentCode", back_populates="school_class",
                            order_by="StudentCode.id", cascade="all, delete-orphan")


# Letters and digits that can't be mistaken for each other (no 0/O, 1/I/L, 5/S, 8/B, 2/Z).
CODE_ALPHABET = "ACDEFHJKMNPRTUVWXY34679"


class StudentCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(12), unique=True, nullable=False, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=False, index=True)
    active = db.Column(db.Boolean, default=True, nullable=False)

    school_class = db.relationship("SchoolClass", back_populates="codes")

    @staticmethod
    def generate(prefix):
        while True:
            code = f"{prefix}-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(3))
            if not StudentCode.query.filter_by(code=code).first():
                return code


class Attempt(db.Model):
    """One finished set of (up to) 10 terms, sent by the game."""
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.String(40), unique=True, nullable=False)  # makes resending harmless
    code_id = db.Column(db.Integer, db.ForeignKey("student_code.id"), nullable=False, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=False, index=True)
    subject_id = db.Column(db.String(60), nullable=False)
    topic_choice = db.Column(db.String(120), default="")
    played_at = db.Column(db.DateTime, nullable=False)
    received_at = db.Column(db.DateTime, default=now, nullable=False)

    code = db.relationship("StudentCode")
    items = db.relationship("AttemptItem", backref="attempt", cascade="all, delete-orphan")


class AttemptItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("attempt.id"), nullable=False, index=True)
    term = db.Column(db.String(120), nullable=False)
    topic = db.Column(db.String(120), default="")
    solved = db.Column(db.Boolean, nullable=False)
    follow = db.Column(db.Boolean, nullable=False)
