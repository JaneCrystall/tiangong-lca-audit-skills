"""Data models for Tiangong platform API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


class DatasetType(str, Enum):
    """Dataset type enumeration."""
    PROCESS = "process"
    MODEL = "model"


class ReviewStatus(str, Enum):
    """Review status enumeration."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"


class FindingSeverity(str, Enum):
    """Finding severity levels."""
    BLOCKING = "blocking"
    ADVISORY = "advisory"
    MANUAL_REVIEW = "manual_review"
    INPUT_GAP = "input_gap"


@dataclass
class DatasetMetadata:
    """Basic dataset metadata from platform."""
    id: str
    name: str
    description: str
    dataset_type: DatasetType
    created_at: str
    updated_at: str
    version: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReviewTask:
    """Review task assigned to auditor."""
    id: str
    dataset_id: str
    dataset_name: str
    dataset_type: DatasetType
    status: ReviewStatus
    assigned_to: str
    assigned_at: str
    due_date: Optional[str] = None
    priority: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditFinding:
    """Audit finding to submit to platform."""
    id: str
    severity: FindingSeverity
    title: str
    description: str
    evidence: str
    suggested_fix: Optional[str] = None
    related_field: Optional[str] = None
    tags: list[str] = field(default_factory=list)


@dataclass
class AuditResult:
    """Complete audit result to submit."""
    review_task_id: str
    dataset_id: str
    conclusion: str  # "approved", "rejected", "manual_review"
    summary: str
    findings: list[AuditFinding] = field(default_factory=list)
    auditor_notes: Optional[str] = None
    submitted_at: Optional[str] = None


@dataclass
class PlatformAction:
    """Represents a platform operation to be executed."""
    action_type: str  # "assign", "approve", "reject", "submit_comment"
    target_id: str  # dataset_id or review_task_id
    parameters: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "target_id": self.target_id,
            "parameters": self.parameters,
            "description": self.description,
        }
