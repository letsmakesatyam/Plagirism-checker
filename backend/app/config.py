"""
Central application configuration.
Reads from environment variables / .env file.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    APP_NAME: str = "College Plagiarism Checker"
    ENV: str = "development"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "postgresql+psycopg2://plagiarism_user:plagiarism_pass@localhost:5432/plagiarism_db"

    # JWT
    JWT_SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # File uploads
    UPLOAD_DIR: str = "uploads/submissions"
    MAX_UPLOAD_SIZE_MB: int = 25
    ALLOWED_EXTENSIONS: tuple = (".pdf", ".docx")

    # Vector search
    FAISS_INDEX_PATH: str = "faiss_data/paragraph_index.faiss"

    # Plagiarism scoring
    # Cosine similarity above which two paragraphs are considered a plagiarism
    # match rather than just "on a related topic". 0.85 is deliberately strict:
    # all-MiniLM-L6-v2 puts loosely-related sentences around 0.4-0.6, genuinely
    # paraphrased text around 0.7-0.85, and near-verbatim copies above 0.9.
    INTERNAL_SIMILARITY_THRESHOLD: float = 0.85

    # Internet plagiarism uses a slightly lower threshold than internal: web
    # sources (Wikipedia, textbooks, articles) are usually paraphrased rather
    # than copied verbatim by the time they reach a student submission, so a
    # 0.85 cutoff would miss real matches. 0.78 still comfortably excludes
    # same-topic-different-wording paragraphs (see README section 11 for the
    # empirical basis of these numbers).
    INTERNET_SIMILARITY_THRESHOLD: float = 0.78
    INTERNET_FAISS_INDEX_PATH: str = "faiss_data/internet_source_index.faiss"

    # AI-generated-text detection (Phase 4c). Model is a RoBERTa classifier
    # originally released to detect GPT-2 output — see README section 12 for
    # its documented limitations against modern LLMs. Two thresholds (not one)
    # create a deliberate "uncertain" middle band instead of forcing every
    # paragraph into a confident human/AI verdict it may not deserve:
    #   probability >= AI_LIKELY_THRESHOLD  -> likely_ai
    #   probability <= AI_HUMAN_THRESHOLD   -> likely_human
    #   otherwise                           -> uncertain
    AI_DETECTION_MODEL_NAME: str = "openai-community/roberta-base-openai-detector"
    AI_LIKELY_THRESHOLD: float = 0.65
    AI_HUMAN_THRESHOLD: float = 0.35

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
