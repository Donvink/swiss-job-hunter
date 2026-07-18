"""
Database models — SQLAlchemy 2.x declarative style.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Enum, Float, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class JobStatus(str, PyEnum):
    NEW          = "new"
    ANALYZED     = "analyzed"
    SHORTLISTED  = "shortlisted"
    VIEWED       = "viewed"       # opened the listing, not yet applied
    CONSIDERING  = "considering"  # read JD, interested but not ready to apply
    APPLIED      = "applied"
    REJECTED     = "rejected"
    INTERVIEWING = "interviewing"
    OFFER        = "offer"
    ARCHIVED     = "archived"


class ApplicationStatus(str, PyEnum):
    PENDING        = "pending"
    SENT           = "sent"
    FAILED         = "failed"
    ACKNOWLEDGED   = "acknowledged"


class ApplicationEvent(str, PyEnum):
    """Timeline events for progress tracking."""
    VIEWED         = "viewed"          # first opened
    APPLIED        = "applied"         # application sent
    CONFIRMATION   = "confirmation"    # got auto-reply
    RECRUITER_CALL = "recruiter_call"  # recruiter reached out
    INTERVIEW_1    = "interview_1"     # first interview
    INTERVIEW_2    = "interview_2"     # second interview
    TECHNICAL      = "technical"       # technical test
    OFFER_RECEIVED = "offer_received"  # offer letter
    OFFER_ACCEPTED = "offer_accepted"  # signed
    OFFER_DECLINED = "offer_declined"  # declined
    REJECTED       = "rejected"        # rejection received
    NOTE           = "note"            # free-form note


class Job(Base):
    """Deduplicated, canonical job record."""
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dedup_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # Core fields
    title: Mapped[str] = mapped_column(String(300))
    company: Mapped[str] = mapped_column(String(300))
    location: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(1000))
    source: Mapped[str] = mapped_column(String(100))

    # Enriched fields
    salary_raw: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    salary_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    employment_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    remote_ok: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    language_required: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    skills_extracted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Direction tag (e.g. "agent", "perception") — links job to a specific CV
    direction: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    # Pipeline state
    status: Mapped[str] = mapped_column(Enum(JobStatus), default=JobStatus.NEW, index=True)
    match_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    match_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_stars: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-5, manual interest rating

    # Tracking timestamps
    viewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    source_job_id: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    # Timestamps
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # Relations
    raw_jobs: Mapped[list[RawJob]] = relationship("RawJob", back_populates="canonical")
    application: Mapped[Optional[Application]] = relationship(
        "Application", back_populates="job", uselist=False
    )
    events: Mapped[list[JobEvent]] = relationship(
        "JobEvent", back_populates="job", order_by="JobEvent.occurred_at"
    )
    interviews: Mapped[list[Interview]] = relationship(
        "Interview", back_populates="job", order_by="Interview.scheduled_at"
    )

    __table_args__ = (
        Index("ix_jobs_status_score", "status", "match_score"),
    )

    @staticmethod
    def make_dedup_hash(title: str, company: str, location: str) -> str:
        key = f"{title.lower().strip()}|{company.lower().strip()}|{location.lower().strip()}"
        return hashlib.sha256(key.encode()).hexdigest()

    def __repr__(self) -> str:
        return f"<Job id={self.id} '{self.title}' @ {self.company}>"


class RawJob(Base):
    __tablename__ = "raw_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    canonical_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("jobs.id"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(100))
    source_job_id: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    url: Mapped[str] = mapped_column(String(1000))
    raw_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    canonical: Mapped[Optional[Job]] = relationship("Job", back_populates="raw_jobs")

    __table_args__ = (
        UniqueConstraint("source", "source_job_id", name="uq_raw_source_id"),
    )


class Application(Base):
    """Application record — cover letter, method, contact info."""
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id"), unique=True)

    cover_letter: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cover_letter_language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    apply_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # email|form|manual
    recipient_email: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    contact_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(Enum(ApplicationStatus), default=ApplicationStatus.PENDING)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    resume_version_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("resume_versions.id"), nullable=True
    )

    job: Mapped[Job] = relationship("Job", back_populates="application")
    resume_version: Mapped[Optional[ResumeVersion]] = relationship(
        "ResumeVersion", back_populates="applications"
    )


class CompanyInfo(Base):
    """Cached LLM-generated company overview, keyed by company name."""
    __tablename__ = "company_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class JobEvent(Base):
    """
    Timeline event for a job — tracks every meaningful interaction.
    One job can have many events (viewed, applied, interview scheduled, etc.)
    """
    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id"), index=True)
    event_type: Mapped[str] = mapped_column(Enum(ApplicationEvent))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # free-form detail
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    job: Mapped[Job] = relationship("Job", back_populates="events")

    def __repr__(self) -> str:
        return f"<JobEvent job={self.job_id} type={self.event_type} at={self.occurred_at}>"


class FileFormat(str, PyEnum):
    PDF  = "pdf"
    DOCX = "docx"
    TXT  = "txt"


class InterviewType(str, PyEnum):
    PHONE_SCREEN = "phone_screen"
    TECHNICAL    = "technical"
    BEHAVIORAL   = "behavioral"
    ONSITE       = "onsite"
    FINAL        = "final"
    OTHER        = "other"


class InterviewFormat(str, PyEnum):
    VIDEO  = "video"
    PHONE  = "phone"
    ONSITE = "onsite"


class InterviewOutcome(str, PyEnum):
    PENDING   = "pending"
    PASSED    = "passed"
    FAILED    = "failed"
    CANCELLED = "cancelled"


class ResumeVersion(Base):
    """A single uploaded/imported resume file, scoped to a direction (or direction-less)."""
    __tablename__ = "resume_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    direction: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # None = data/cv.txt
    label: Mapped[str] = mapped_column(String(200))
    original_filename: Mapped[str] = mapped_column(String(500))
    file_path: Mapped[str] = mapped_column(String(1000))
    file_format: Mapped[str] = mapped_column(Enum(FileFormat))
    extracted_text: Mapped[str] = mapped_column(Text)
    changelog: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    applications: Mapped[list[Application]] = relationship(
        "Application", back_populates="resume_version"
    )

    __table_args__ = (
        Index("ix_resume_versions_direction_active", "direction", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<ResumeVersion id={self.id} direction={self.direction} label='{self.label}'>"


class Interview(Base):
    """A single interview round for a job. Replaces the fixed-enum ApplicationEvent rounds."""
    __tablename__ = "interviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id"), index=True)
    round_number: Mapped[int] = mapped_column(Integer)
    interview_type: Mapped[str] = mapped_column(Enum(InterviewType))
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    interviewer_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    format: Mapped[Optional[str]] = mapped_column(Enum(InterviewFormat), nullable=True)
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    prep_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    outcome: Mapped[str] = mapped_column(Enum(InterviewOutcome), default=InterviewOutcome.PENDING)

    # Retrospective fields
    self_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-5
    went_well: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    to_improve: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    job: Mapped[Job] = relationship("Job", back_populates="interviews")
    questions: Mapped[list[InterviewQuestion]] = relationship(
        "InterviewQuestion", back_populates="interview", order_by="InterviewQuestion.order_index"
    )

    def __repr__(self) -> str:
        return f"<Interview id={self.id} job={self.job_id} round={self.round_number}>"


class InterviewQuestion(Base):
    """A single question asked (or expected) in an interview round, with optional AI-optimized answer."""
    __tablename__ = "interview_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    interview_id: Mapped[int] = mapped_column(Integer, ForeignKey("interviews.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    my_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    llm_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    optimized_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    interview: Mapped[Interview] = relationship("Interview", back_populates="questions")

    def __repr__(self) -> str:
        return f"<InterviewQuestion id={self.id} interview={self.interview_id}>"


class StarStory(Base):
    """Standalone STAR-format personal story, independent of resumes/interviews."""
    __tablename__ = "star_stories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(300))
    tags: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # comma-separated
    situation: Mapped[str] = mapped_column(Text)
    task: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    result: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<StarStory id={self.id} title='{self.title}'>"
