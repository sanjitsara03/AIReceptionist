from datetime import datetime
from pydantic import BaseModel
from app.models import JobStatus


class TechnicianResponse(BaseModel):
    id: int
    name: str
    phone: str
    active: bool

    model_config = {"from_attributes": True}


class CustomerResponse(BaseModel):
    id: int
    name: str
    phone: str
    created_at: datetime

    model_config = {"from_attributes": True}


class JobResponse(BaseModel):
    id: int
    job_type: str
    status: JobStatus
    notes: str | None
    reminder_sent: bool
    start_time: datetime | None
    customer: CustomerResponse
    technician: TechnicianResponse | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    id: int
    customer: CustomerResponse
    created_at: datetime

    model_config = {"from_attributes": True}


class DashboardSummary(BaseModel):
    total_jobs_today: int
    confirmed: int
    completed: int
    no_shows: int
    cancelled: int
    total_customers: int
