"""apps/core/constants.py — System-wide enumerations and constants."""
from django.db import models


# ─── User Roles ──────────────────────────────────────────────────────────────
class UserRole(models.TextChoices):
    ADMINISTRATOR = "administrator", "Administrator"
    LAB_OPERATOR = "lab_operator", "Laboratory Operator"
    REVIEWER = "reviewer", "Reviewer / Approver"
    SUPERADMIN = "superadmin", "Administrator (Superadmin)"
    LAB_MANAGER = "lab_manager", "Laboratory Manager"
    TECHNICIAN = "technician", "Laboratory Operator (Technician)"
    VIEWER = "viewer", "Viewer"


# ─── Accuracy Classes (OIML R 76-1 Clause 3.2) ───────────────────────────────
# ⚠️ [VERIFY vs. OIML R 76] Confirm class designations
class AccuracyClass(models.TextChoices):
    CLASS_I = "I", "Class I (Special)"
    CLASS_II = "II", "Class II (High)"
    CLASS_III = "III", "Class III (Medium)"
    CLASS_IIII = "IIII", "Class IIII (Ordinary)"


# ─── Instrument Status ────────────────────────────────────────────────────────
class InstrumentStatus(models.TextChoices):
    IN_LAB = "IN_LAB", "In Laboratory"
    IN_PROGRESS = "IN_PROGRESS", "Testing in Progress"
    TESTED = "TESTED", "Tested"
    RETURNED = "RETURNED", "Returned to Owner"
    REJECTED = "REJECTED", "Rejected / Failed"


# ─── Test Session Status ──────────────────────────────────────────────────────
class SessionStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    SUBMITTED = "SUBMITTED", "Submitted"
    PENDING_REVIEW = "PENDING_REVIEW", "Pending Review"
    UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    REPORT_GENERATED = "REPORT_GENERATED", "Report Generated"


# ─── Pass / Fail Result ───────────────────────────────────────────────────────
class PassFail(models.TextChoices):
    PASS = "PASS", "Pass"
    FAIL = "FAIL", "Fail"
    PENDING = "PENDING", "Pending"
    NOT_APPLICABLE = "N/A", "Not Applicable"


# ─── Weighing Test Types ──────────────────────────────────────────────────────
# ⚠️ [VERIFY vs. OIML R 76] Confirm required test directions
class WeighingTestType(models.TextChoices):
    INCREASING = "INCREASING", "Increasing Load"
    DECREASING = "DECREASING", "Decreasing Load"


# ─── Influence Quantity Types ─────────────────────────────────────────────────
# ⚠️ [VERIFY vs. OIML R 76 Clause 5] Confirm all influence quantities
class InfluenceType(models.TextChoices):
    TEMPERATURE = "TEMPERATURE", "Temperature"
    VOLTAGE = "VOLTAGE", "Voltage Variation"
    HUMIDITY = "HUMIDITY", "Damp Heat"
    VIBRATION = "VIBRATION", "Vibration"
    TILT = "TILT", "Tilt / Inclination"


# ─── Report Types ────────────────────────────────────────────────────────────
class ReportType(models.TextChoices):
    PDF = "PDF", "PDF Document"
    DOCX = "DOCX", "Word Document"


# ─── Audit Actions ───────────────────────────────────────────────────────────
class AuditAction(models.TextChoices):
    CREATE = "CREATE", "Created"
    UPDATE = "UPDATE", "Updated"
    DELETE = "DELETE", "Deleted"
    LOGIN = "LOGIN", "Logged In"
    LOGOUT = "LOGOUT", "Logged Out"
    APPROVE = "APPROVE", "Approved"
    REJECT = "REJECT", "Rejected"
    GENERATE = "GENERATE", "Generated Report"
    DOWNLOAD = "DOWNLOAD", "Downloaded Report"
    VIEW = "VIEW", "Viewed / Previewed"
    SUBMIT = "SUBMIT", "Submitted for Review"
    START_REVIEW = "START_REVIEW", "Review Started"
    REVISION = "REVISION", "Controlled Revision"
    LOCK = "LOCK", "Session Locked"
