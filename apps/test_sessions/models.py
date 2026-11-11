"""apps/test_sessions/models.py – Test session lifecycle and procedure configuration model."""
import random
from django.db import models
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from apps.core.models import BaseModel
from apps.core.constants import SessionStatus


def generate_session_number():
    """Generate a human-readable unique test session reference. Format: TS-YYYYMMDD-XXXX."""
    today = timezone.now().strftime("%Y%m%d")
    suffix = str(random.randint(1000, 9999))
    return f"TS-{today}-{suffix}"


class OIMLEdition(models.TextChoices):
    R76_2006 = "R76-2006", "OIML R 76-1:2006 / EN 45501:2015"
    R76_1992 = "R76-1992", "OIML R 76-1:1992"
    NATIONAL = "NATIONAL", "National Metrology Standard / Other"


class TestSession(BaseModel):
    """
    Represents one complete NAWI test record for a weighing instrument under OIML R 76.
    Configurable for applicable test procedures, environmental conditions, and status flow.

    Workflow:
        DRAFT → IN_PROGRESS → PENDING_REVIEW → APPROVED / REJECTED
    """

    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.PROTECT,
        related_name="test_sessions",
        verbose_name="Laboratory / Organisation",
    )
    instrument = models.ForeignKey(
        "instruments.Instrument",
        on_delete=models.PROTECT,
        related_name="test_sessions",
        verbose_name="Linked Instrument",
        help_text="Instrument under verification test.",
    )

    # ── 1. Test Identification & Tracking ─────────────────────────────────────
    session_number = models.CharField(
        max_length=30,
        unique=True,
        default=generate_session_number,
        verbose_name="Unique Test ID",
        help_text="Auto-generated unique test reference number (e.g. TS-YYYYMMDD-XXXX).",
    )
    lab_reference_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Laboratory Reference Number",
        help_text="Internal laboratory tracking or certificate reference number.",
    )
    test_date = models.DateField(
        default=timezone.now,
        verbose_name="Test Date",
        help_text="Date on which the test was performed.",
    )
    test_location = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Test Location",
        help_text="Physical laboratory room, testing bay, or client site.",
    )

    # ── 2. Personnel ──────────────────────────────────────────────────────────
    technician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sessions_as_technician",
        verbose_name="Operator / Technician",
        help_text="Metrologist or technician performing the test procedures.",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions_as_reviewer",
        verbose_name="Reviewer / Approver",
        help_text="Authorized metrologist verifying observations and approving report.",
    )

    # ── 3. Applicable Standards & Edition ─────────────────────────────────────
    oiml_edition = models.CharField(
        max_length=20,
        choices=OIMLEdition.choices,
        default=OIMLEdition.R76_2006,
        verbose_name="Applicable OIML R 76 Edition",
        help_text="Standard edition governing acceptance criteria and MPE limits.",
    )

    # ── 4. Applicable Test Procedures Configuration ───────────────────────────
    # Configurable procedures: applicability determined by instrument and standard requirements
    proc_initial_examination = models.BooleanField(
        default=True,
        verbose_name="Initial Examination",
        help_text="Visual inspection, markings, levelling, sealing, and functional check.",
    )
    proc_zero_setting = models.BooleanField(
        default=True,
        verbose_name="Zero-Setting & Tracking Tests",
        help_text="R 76 §A.4.1 – §A.4.3: Zero-setting accuracy and tracking device checks.",
    )
    proc_weighing = models.BooleanField(
        default=True,
        verbose_name="Weighing Performance Test",
        help_text="R 76 §A.4.4: Increasing and decreasing nominal load points up to Max.",
    )
    proc_repeatability = models.BooleanField(
        default=True,
        verbose_name="Repeatability Test",
        help_text="R 76 §A.4.10: Repeatability series at minimum two load points.",
    )
    proc_eccentricity = models.BooleanField(
        default=True,
        verbose_name="Eccentricity Test",
        help_text="R 76 §A.4.7: Off-center load placement test (e.g. Max/3 or Max/4).",
    )
    proc_discrimination = models.BooleanField(
        default=True,
        verbose_name="Discrimination Test",
        help_text="R 76 §A.4.8: Sensitivity to small additional loads (~1.4d).",
    )
    proc_tare = models.BooleanField(
        default=False,
        verbose_name="Tare Weighing Test",
        help_text="R 76 §A.4.6: Tare range, subtractive, and additive tare weighing check.",
    )
    proc_influence_quantities = models.BooleanField(
        default=False,
        verbose_name="Influence Quantities / Temp Test",
        help_text="R 76 §A.5.3: Performance under temperature and environmental variations.",
    )

    # ── 5. Observations for Initial Exam & Zero Check ─────────────────────────
    initial_examination_passed = models.BooleanField(
        default=True,
        verbose_name="Initial Examination Result",
        help_text="Pass/Fail status of visual markings and functional inspection.",
    )
    initial_examination_notes = models.TextField(
        blank=True,
        verbose_name="Initial Examination Observations",
        help_text="Condition of plate markings, serial number readability, level bubble status.",
    )
    zero_test_passed = models.BooleanField(
        default=True,
        verbose_name="Zero-Setting / Tracking Result",
        help_text="Zero setting error within ±0.25e per OIML R 76 §A.4.1.",
    )
    zero_test_notes = models.TextField(
        blank=True,
        verbose_name="Zero-Setting / Tracking Observations",
        help_text="Zeroing time, indicator response, and tracking range observations.",
    )

    # ── 6. Status & Lockout ───────────────────────────────────────────────────
    status = models.CharField(
        max_length=20,
        choices=SessionStatus.choices,
        default=SessionStatus.DRAFT,
        db_index=True,
        verbose_name="Test Status",
    )
    is_locked = models.BooleanField(
        default=False,
        verbose_name="Session Locked",
        help_text="Locked once approved to prevent modification.",
    )
    overall_result = models.CharField(
        max_length=10,
        choices=[("PASS", "Pass"), ("FAIL", "Fail"), ("PENDING", "Pending")],
        default="PENDING",
        verbose_name="Overall Metrological Result",
    )
    rejection_reason = models.TextField(
        blank=True,
        verbose_name="Rejection Comments",
        help_text="Reason provided by reviewer if returned for correction.",
    )

    # ── Workflow Audit & Timestamp History ────────────────────────────────────
    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Submission Date",
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_test_sessions",
        verbose_name="Submitted By",
    )
    review_started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Review Started Date",
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Approval Date",
    )
    rejected_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Rejection Date",
    )
    report_generated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Report Generation Date",
    )
    report_generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_generated_test_sessions",
        verbose_name="Report Generated By",
    )
    revision_number = models.PositiveIntegerField(
        default=1,
        verbose_name="Revision Number",
        help_text="Incremented upon every controlled revision after approval.",
    )
    revision_reason = models.TextField(
        blank=True,
        verbose_name="Revision Justification",
        help_text="Mandatory change-control reason explaining the approved record revision.",
    )

    # ── 7. Environmental Conditions ───────────────────────────────────────────
    temperature_start = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Temperature at Start (°C)",
        help_text="Ambient temperature at test commencement.",
    )
    temperature_end = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Temperature at End (°C)",
        help_text="Ambient temperature at test conclusion.",
    )
    humidity_start = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Relative Humidity at Start (%RH)",
        help_text="Ambient relative humidity at start.",
    )
    humidity_end = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Relative Humidity at End (%RH)",
        help_text="Ambient relative humidity at end.",
    )

    # ── 8. Standards, Remarks, and Notes ──────────────────────────────────────
    reference_standards = models.TextField(
        blank=True,
        verbose_name="Reference Standards Used",
        help_text="Standard mass set ID, calibration certificate numbers, and traceability codes.",
    )
    remarks = models.TextField(
        blank=True,
        verbose_name="Remarks / Observations",
        help_text="General technician remarks, instrument behavior, or visual findings.",
    )
    notes = models.TextField(
        blank=True,
        verbose_name="Administrative Notes",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Test Record"
        verbose_name_plural = "Test Records"

    def __str__(self):
        return f"{self.session_number} — {self.instrument} ({self.test_date})"

    def save(self, *args, **kwargs):
        """Synchronize remarks and notes if one is provided."""
        if self.remarks and not self.notes:
            self.notes = self.remarks
        elif self.notes and not self.remarks:
            self.remarks = self.notes
        super().save(*args, **kwargs)

    @property
    def can_be_submitted(self):
        """Session can be submitted for review if in DRAFT, IN_PROGRESS, or REJECTED and unlocked."""
        return not self.is_locked and self.status in [
            SessionStatus.DRAFT,
            SessionStatus.IN_PROGRESS,
            SessionStatus.REJECTED,
        ]

    @property
    def can_be_reviewed(self):
        """Session can be moved to UNDER_REVIEW by reviewer if currently submitted."""
        return not self.is_locked and self.status in [
            SessionStatus.SUBMITTED,
            SessionStatus.PENDING_REVIEW,
        ]

    @property
    def can_be_approved(self):
        """Session can be approved if currently in review."""
        return not self.is_locked and self.status in [
            SessionStatus.SUBMITTED,
            SessionStatus.PENDING_REVIEW,
            SessionStatus.UNDER_REVIEW,
        ]

    @property
    def is_pending_review(self):
        """Returns True if the session is waiting for reviewer action."""
        return self.status in [
            SessionStatus.SUBMITTED,
            SessionStatus.PENDING_REVIEW,
            SessionStatus.UNDER_REVIEW,
        ]

    @property
    def can_be_revised(self):
        """Controlled revision can be initiated on approved / report generated sessions."""
        return self.status in [
            SessionStatus.APPROVED,
            SessionStatus.REPORT_GENERATED,
        ]

    @property
    def environmental_temperature(self):
        return self.temperature_start or self.temperature_end

    @property
    def temperature_range(self):
        """Formatted temperature range string."""
        if self.temperature_start is not None and self.temperature_end is not None:
            return f"{self.temperature_start}°C – {self.temperature_end}°C"
        elif self.temperature_start is not None:
            return f"{self.temperature_start}°C"
        return "—"

    @property
    def humidity_range(self):
        """Formatted humidity range string."""
        if self.humidity_start is not None and self.humidity_end is not None:
            return f"{self.humidity_start}% – {self.humidity_end}% RH"
        elif self.humidity_start is not None:
            return f"{self.humidity_start}% RH"
        return "—"

    @property
    def active_procedures_count(self):
        """Total count of applicable procedures selected for this test session."""
        flags = [
            self.proc_initial_examination,
            self.proc_zero_setting,
            self.proc_weighing,
            self.proc_repeatability,
            self.proc_eccentricity,
            self.proc_discrimination,
            self.proc_tare,
            self.proc_influence_quantities,
        ]
        return sum(bool(f) for f in flags)

    @property
    def selected_procedures(self):
        """Returns structured metadata for all active test procedures in this session."""
        procs = []
        if self.proc_initial_examination:
            procs.append({
                "code": "initial_examination",
                "name": "Initial Examination",
                "clause": "OIML R 76 §A.3 / §A.4",
                "description": "Visual markings, rating plate, levelling, and functional inspection",
                "status": "PASS" if self.initial_examination_passed else "FAIL",
                "notes": self.initial_examination_notes,
                "is_measurement": False,
            })
        if self.proc_zero_setting:
            count = self.zero_setting_measurements.count()
            procs.append({
                "code": "zero_setting",
                "name": "Zero-Setting & Tracking Tests",
                "clause": "OIML R 76 §A.4.1 – §A.4.3",
                "description": "Zero setting accuracy (±0.25e) and zero-tracking range checks",
                "count": count,
                "status": "COMPLETE" if count > 0 else "PENDING",
                "is_measurement": True,
                "url": reverse("measurements:zero_setting_list", kwargs={"session_pk": self.pk}),
            })
        if self.proc_weighing:
            count = self.weighing_measurements.count()
            procs.append({
                "code": "weighing",
                "name": "Weighing Performance Tests",
                "clause": "OIML R 76 §A.4.4 / Table 1",
                "description": "Load points with increasing and decreasing loads up to Max",
                "count": count,
                "status": "COMPLETE" if count > 0 else "PENDING",
                "is_measurement": True,
                "url": reverse("measurements:weighing_list", kwargs={"session_pk": self.pk}),
            })
        if self.proc_repeatability:
            count = self.repeatability_measurements.count()
            procs.append({
                "code": "repeatability",
                "name": "Repeatability Test",
                "clause": "OIML R 76 §A.4.10",
                "description": "Successive loading series at identical nominal loads (min. 3 reps)",
                "count": count,
                "status": "COMPLETE" if count > 0 else "PENDING",
                "is_measurement": True,
                "url": reverse("measurements:repeatability_list", kwargs={"session_pk": self.pk}),
            })
        if self.proc_eccentricity:
            count = self.eccentricity_measurements.count()
            procs.append({
                "code": "eccentricity",
                "name": "Eccentricity Test",
                "clause": "OIML R 76 §A.4.7",
                "description": "Off-center load receptor placement (Centre, Front, Back, Left, Right)",
                "count": count,
                "status": "COMPLETE" if count > 0 else "PENDING",
                "is_measurement": True,
                "url": reverse("measurements:eccentricity_list", kwargs={"session_pk": self.pk}),
            })
        if self.proc_discrimination:
            count = self.discrimination_measurements.count()
            procs.append({
                "code": "discrimination",
                "name": "Discrimination Test",
                "clause": "OIML R 76 §A.4.8",
                "description": "Indicator response to small additional mass (d/10)",
                "count": count,
                "status": "COMPLETE" if count > 0 else "PENDING",
                "is_measurement": True,
                "url": reverse("measurements:discrimination_list", kwargs={"session_pk": self.pk}),
            })
        if self.proc_tare:
            count = self.tare_measurements.count()
            procs.append({
                "code": "tare",
                "name": "Tare Weighing Test",
                "clause": "OIML R 76 §A.4.6",
                "description": "Weighing accuracy with subtractive or additive tare activated",
                "count": count,
                "status": "COMPLETE" if count > 0 else "PENDING",
                "is_measurement": True,
                "url": reverse("measurements:tare_list", kwargs={"session_pk": self.pk}),
            })
        if self.proc_influence_quantities:
            procs.append({
                "code": "influence_quantities",
                "name": "Influence Quantities & Temperature Test",
                "clause": "OIML R 76 §A.5.3",
                "description": "Thermal stability and span drift under temperature variations",
                "status": "OPTIONAL",
                "is_measurement": False,
            })
        return procs


class ApprovalAction(models.TextChoices):
    """Actions recorded in the immutable approval history audit trail."""
    SUBMIT = "SUBMIT", "Submitted for Review"
    START_REVIEW = "START_REVIEW", "Review Commenced"
    APPROVE = "APPROVE", "Approved"
    REJECT = "REJECT", "Returned / Rejected"
    RESUBMIT = "RESUBMIT", "Corrected & Resubmitted"
    GENERATE_REPORT = "GENERATE_REPORT", "Report Generated"
    REVISE = "REVISE", "Controlled Revision Initiated"


class ApprovalHistory(BaseModel):
    """
    Immutable audit ledger for every step in the test review & approval lifecycle:
    DRAFT → SUBMITTED → UNDER REVIEW → APPROVED / REJECTED → REPORT GENERATED.
    """
    session = models.ForeignKey(
        TestSession,
        on_delete=models.CASCADE,
        related_name="approval_history",
        verbose_name="Test Session",
    )
    action = models.CharField(
        max_length=30,
        choices=ApprovalAction.choices,
        verbose_name="Workflow Action",
    )
    from_status = models.CharField(
        max_length=30,
        choices=SessionStatus.choices,
        verbose_name="Previous Status",
    )
    to_status = models.CharField(
        max_length=30,
        choices=SessionStatus.choices,
        verbose_name="New Status",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="approval_history_entries",
        verbose_name="Action Taken By",
    )
    comments = models.TextField(
        blank=True,
        verbose_name="Review Comments / Remediation Notes",
        help_text="Detailed feedback, rejection reasons, or revision justifications.",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Audit Snapshot / Metadata",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Approval History Record"
        verbose_name_plural = "Approval History Records"

    def __str__(self):
        return (
            f"{self.session.session_number} [{self.get_action_display()}] "
            f"by {self.actor} at {self.created_at:%Y-%m-%d %H:%M}"
        )
