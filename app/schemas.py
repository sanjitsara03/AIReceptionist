from datetime import datetime
from typing import Any
from pydantic import BaseModel, model_validator
from app.models import JobStatus, MessageDirection


class BusinessResponse(BaseModel):
    id: int
    name: str
    twilio_number: str
    services: str | None
    hours: str | None
    address: str | None
    voice_greeting: str | None = None
    system_prompt: str | None = None

    model_config = {"from_attributes": True}


class BusinessUpdate(BaseModel):
    """All fields optional — only provided keys are updated."""
    name: str | None = None
    services: str | None = None
    hours: str | None = None
    address: str | None = None
    voice_greeting: str | None = None
    system_prompt: str | None = None


class TechnicianResponse(BaseModel):
    id: int
    name: str
    phone: str
    active: bool

    model_config = {"from_attributes": True}


class TechnicianCreate(BaseModel):
    name: str
    phone: str
    active: bool = True


class TechnicianUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    active: bool | None = None


class CustomerResponse(BaseModel):
    id: int
    name: str
    phone: str
    created_at: datetime
    job_count: int = 0

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def compute_job_count(cls, data: Any) -> Any:
        if hasattr(data, "jobs"):
            try:
                data.__dict__["job_count"] = len(data.jobs)
            except Exception:
                pass
        return data


class JobResponse(BaseModel):
    id: int
    job_type: str
    status: JobStatus
    source: str
    estimate: int | None
    notes: str | None
    reminder_sent: bool
    start_time: datetime | None = None
    end_time: datetime | None = None
    customer: CustomerResponse
    technician: TechnicianResponse | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def pull_slot_times(cls, data: Any) -> Any:
        if hasattr(data, "time_slot") and data.time_slot is not None:
            data.__dict__.setdefault("start_time", data.time_slot.start_time)
            data.__dict__.setdefault("end_time", data.time_slot.end_time)
        return data


class JobCreate(BaseModel):
    customer_id: int
    time_slot_id: int
    job_type: str
    estimate: int | None = None
    notes: str | None = None


class JobReschedule(BaseModel):
    new_slot_id: int


class TimeSlotResponse(BaseModel):
    id: int
    technician_id: int
    technician_name: str
    start_time: datetime
    end_time: datetime


class TimeSlotFullResponse(BaseModel):
    """Like TimeSlotResponse but also includes booking status."""
    id: int
    technician_id: int
    technician_name: str
    start_time: datetime
    end_time: datetime
    is_available: bool


class TimeSlotCreate(BaseModel):
    technician_id: int
    start_time: datetime
    end_time: datetime


class TimeSlotBulkCreate(BaseModel):
    """
    Create recurring slots for one technician.
    Example: M-F 9am-5pm with 2hr slots between 2026-06-01 and 2026-06-30.
    """
    technician_id: int
    start_date: datetime  # midnight on the first day to include
    end_date: datetime    # midnight on the day AFTER the last day to include
    weekdays: list[int]   # 0=Mon, 6=Sun
    day_start_hour: int   # local hour the workday starts, 0-23
    day_end_hour: int     # local hour the workday ends, 0-23
    slot_minutes: int     # length of each slot in minutes


class MessageResponse(BaseModel):
    id: int
    direction: MessageDirection
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    id: int
    channel: str
    customer: CustomerResponse
    messages: list[MessageResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InviteResponse(BaseModel):
    token: str
    business_name: str
    expires_at: datetime
    claimed: bool

    model_config = {"from_attributes": True}


class FeedItem(BaseModel):
    id: int
    kind: str
    customer_name: str
    verb: str
    channel: str
    when_iso: datetime
    tech_name: str | None = None
    estimate: int | None = None


class DashboardSummary(BaseModel):
    total_jobs_today: int
    in_progress: int
    confirmed: int
    pending: int
    completed: int
    no_shows: int
    cancelled: int
    ai_booked_today: int
    ai_booked_revenue: int
    human_booked_today: int
    conversations_today: int
    total_customers: int
