from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import WorkCalendarSetting

DEFAULT_CLOSED_WEEKDAYS = (6,)
MAX_CALENDAR_LOOKAHEAD_DAYS = 366


@dataclass(frozen=True)
class WorkCalendarRules:
    closed_weekdays: frozenset[int]
    holiday_dates: frozenset[date]
    working_dates: frozenset[date]


def load_work_calendar(session: Session) -> WorkCalendarRules:
    setting = session.get(WorkCalendarSetting, "singleton")
    if setting is None:
        return WorkCalendarRules(
            closed_weekdays=frozenset(DEFAULT_CLOSED_WEEKDAYS),
            holiday_dates=frozenset(),
            working_dates=frozenset(),
        )
    return WorkCalendarRules(
        closed_weekdays=frozenset(setting.closed_weekdays_json),
        holiday_dates=frozenset(date.fromisoformat(value) for value in setting.holiday_dates_json),
        working_dates=frozenset(date.fromisoformat(value) for value in setting.working_dates_json),
    )


def is_working_day(day: date, rules: WorkCalendarRules) -> bool:
    if day in rules.working_dates:
        return True
    return day not in rules.holiday_dates and day.weekday() not in rules.closed_weekdays


def next_working_day(day: date, rules: WorkCalendarRules) -> date:
    candidate = day
    for _ in range(MAX_CALENDAR_LOOKAHEAD_DAYS + 1):
        if is_working_day(candidate, rules):
            return candidate
        candidate += timedelta(days=1)
    raise ValueError("工作日曆在未來一年內沒有可用工作日。")
