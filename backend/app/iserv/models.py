from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Child:
    child_id: str
    name: str


@dataclass(frozen=True)
class Lesson:
    date: str
    day_of_week: int
    period: int
    subject: str
    teacher: str
    room: str
    class_name: str
    lesson_id: Optional[int] = None
    internal_id: Optional[str] = None
    subject_name: str = ""
    subject_color: str = ""
    teacher_name: str = ""
    start_time: str = ""
    end_time: str = ""


@dataclass
class TimetableWeek:
    start_date: str
    end_date: str
    last_updated: Optional[str]
    combined: list
    plain: list
    changes: list = field(default_factory=list)
