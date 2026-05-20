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

    # Direction tag (e.g. "ml", "perception") — links job to a specific CV
    direction: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    # Pipeline state
    status: Mapped[str] = mapped_column(Enum(JobStatus), default=JobStatus.NEW, index=True)
    match_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    match_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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

    job: Mapped[Job] = relationship("Job", back_populates="application")


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
