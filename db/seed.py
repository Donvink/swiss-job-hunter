"""
One-time DB seeding from legacy flat CV files.
"""
from __future__ import annotations

import glob
from pathlib import Path

from config.settings import settings
from db.models import FileFormat, ResumeVersion
from db.session import get_session


def seed_resume_versions_from_flat_files() -> None:
    """
    Idempotent: for data/cv.txt and every data/cv_*.txt, insert a v1 ResumeVersion
    if that direction has zero existing rows. Safe to call on every startup.
    """
    candidates: list[tuple[str | None, Path]] = []

    cv_path = settings.cv_text_path
    if cv_path.exists():
        candidates.append((None, cv_path))

    pattern = str(cv_path.parent / "cv_*.txt")
    for p in sorted(glob.glob(pattern)):
        path = Path(p)
        candidates.append((path.stem[3:], path))  # strip leading "cv_"

    with get_session() as session:
        for direction, path in candidates:
            exists = (
                session.query(ResumeVersion)
                .filter(ResumeVersion.direction == direction)
                .first()
            )
            if exists:
                continue
            session.add(ResumeVersion(
                direction=direction,
                label="v1",
                original_filename=path.name,
                file_path=str(path),
                file_format=FileFormat.TXT,
                extracted_text=path.read_text(encoding="utf-8"),
                is_active=True,
            ))
