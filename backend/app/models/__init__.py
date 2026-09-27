"""
Import every model here so Alembic's autogenerate (which reads
Base.metadata) can discover all tables from a single import.
As new models are added in later phases (Assignment, Submission,
Report, etc.) they must be imported here too.
"""
from app.models.user import User, UserRole  # noqa: F401
from app.models.assignment import Assignment  # noqa: F401
from app.models.submission import Submission, SubmissionStatus, FileType  # noqa: F401
from app.models.paragraph_embedding import ParagraphEmbedding  # noqa: F401
from app.models.report import Report, ReportStatus, InternalMatch, InternetMatch, AIResult, AILabel  # noqa: F401
from app.models.internet_source import InternetSource, InternetSourceCategory, InternetSourceParagraph  # noqa: F401
