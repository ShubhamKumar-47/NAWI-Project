"""apps/test_sessions/services.py – Business logic for session lifecycle transitions & approval workflow.

Workflow:
    DRAFT → SUBMITTED → UNDER REVIEW → APPROVED / REJECTED → REPORT GENERATED
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.constants import SessionStatus, AuditAction, InstrumentStatus
from apps.audit.utils import log_action
from apps.test_sessions.models import ApprovalAction, ApprovalHistory


class SessionService:
    """
    Encapsulates all status transitions, approval workflow governance,
    and business-rule validation for TestSession records under OIML R 76.
    Views must call this service instead of mutating session fields directly.
    """

    @staticmethod
    def submit_for_review(session, user, request=None, comments=""):
        """
        Move DRAFT / IN_PROGRESS / REJECTED → SUBMITTED.
        Validates metrological completeness and observation requirements.
        """
        if session.is_locked:
            raise ValidationError("Cannot submit a locked test session.")
        if session.status not in [
            SessionStatus.DRAFT,
            SessionStatus.IN_PROGRESS,
            SessionStatus.REJECTED,
        ]:
            raise ValidationError(
                f"Cannot submit a session in '{session.get_status_display()}' status."
            )

        from apps.test_sessions.results_validation import ResultsValidationService
        validation = ResultsValidationService.validate_session(session)
        if not validation.is_submittable:
            reasons = "; ".join(validation.blocking_reasons)
            raise ValidationError(f"Cannot submit test session: {reasons}")

        from_status = session.status
        action = ApprovalAction.RESUBMIT if from_status == SessionStatus.REJECTED else ApprovalAction.SUBMIT
        now = timezone.now()

        with transaction.atomic():
            session.status = SessionStatus.SUBMITTED
            session.submitted_at = now
            session.submitted_by = user
            session.save(update_fields=["status", "submitted_at", "submitted_by", "updated_at"])

            ApprovalHistory.objects.create(
                session=session,
                action=action,
                from_status=from_status,
                to_status=SessionStatus.SUBMITTED,
                actor=user,
                comments=comments.strip() if comments else "",
                metadata={
                    "overall_result": session.overall_result,
                    "active_procedures": session.active_procedures_count,
                    "observations_count": validation.total_observations,
                },
            )

            log_action(
                user=user,
                action=AuditAction.SUBMIT,
                obj=session,
                description=f"Session {session.session_number} submitted for technical review.",
                request=request,
            )

    @staticmethod
    def start_review(session, reviewer, request=None, comments=""):
        """
        Move SUBMITTED / PENDING_REVIEW → UNDER_REVIEW.
        Reviewer claims and commences verification.
        """
        if not reviewer.can_approve_sessions:
            raise PermissionDenied("You do not have permission to review test sessions.")
        if session.is_locked:
            raise ValidationError("Cannot review an already locked test session.")
        if session.status not in [SessionStatus.SUBMITTED, SessionStatus.PENDING_REVIEW]:
            raise ValidationError(
                f"Cannot start review on a session in '{session.get_status_display()}' status."
            )

        from_status = session.status
        now = timezone.now()

        with transaction.atomic():
            session.status = SessionStatus.UNDER_REVIEW
            session.reviewer = reviewer
            session.review_started_at = now
            session.save(update_fields=["status", "reviewer", "review_started_at", "updated_at"])

            ApprovalHistory.objects.create(
                session=session,
                action=ApprovalAction.START_REVIEW,
                from_status=from_status,
                to_status=SessionStatus.UNDER_REVIEW,
                actor=reviewer,
                comments=comments.strip() if comments else "",
                metadata={
                    "reviewer_name": reviewer.full_name,
                    "reviewer_email": reviewer.email,
                },
            )

            log_action(
                user=reviewer,
                action=AuditAction.START_REVIEW,
                obj=session,
                description=f"Session {session.session_number} review commenced by {reviewer.full_name}.",
                request=request,
            )

    @staticmethod
    def approve(session, reviewer, comments="", request=None):
        """
        Move SUBMITTED / PENDING_REVIEW / UNDER_REVIEW → APPROVED.
        Locks the session permanently to prevent unauthorized modifications.
        Enforces OIML R 76 compliance: PASS requires verified completeness.
        """
        if not reviewer.can_approve_sessions:
            raise PermissionDenied("You do not have permission to approve test sessions.")
        if session.status not in [
            SessionStatus.SUBMITTED,
            SessionStatus.PENDING_REVIEW,
            SessionStatus.UNDER_REVIEW,
        ]:
            raise ValidationError(
                f"Cannot approve a session in '{session.get_status_display()}' status."
            )

        from apps.test_sessions.results_validation import ResultsValidationService
        validation = ResultsValidationService.validate_session(session)
        if not validation.is_pass_eligible:
            reasons = "; ".join(validation.blocking_reasons) or "Session has incomplete test procedures or unverified rules."
            raise ValidationError(f"Session cannot receive an overall PASS approval: {reasons}")

        from_status = session.status
        now = timezone.now()

        with transaction.atomic():
            session.status = SessionStatus.APPROVED
            session.is_locked = True
            session.reviewer = reviewer
            session.approved_at = now
            session.save(update_fields=["status", "is_locked", "reviewer", "approved_at", "updated_at"])

            # Synchronize instrument status to TESTED
            instrument = session.instrument
            instrument.status = InstrumentStatus.TESTED
            instrument.save(update_fields=["status"])

            ApprovalHistory.objects.create(
                session=session,
                action=ApprovalAction.APPROVE,
                from_status=from_status,
                to_status=SessionStatus.APPROVED,
                actor=reviewer,
                comments=comments.strip() if comments else "",
                metadata={
                    "overall_result": "PASS",
                    "approved_at": now.isoformat(),
                    "reviewer": reviewer.full_name,
                    "oiml_edition": session.get_oiml_edition_display(),
                    "instrument_sn": instrument.serial_number,
                },
            )

            log_action(
                user=reviewer,
                action=AuditAction.APPROVE,
                obj=session,
                description=f"Session {session.session_number} approved and locked by {reviewer.full_name}.",
                request=request,
            )

    @staticmethod
    def reject(session, reviewer, reason, request=None):
        """
        Move SUBMITTED / PENDING_REVIEW / UNDER_REVIEW → REJECTED with a mandatory reason.
        Unlocks the record so the laboratory operator can correct observations.
        """
        if not reviewer.can_approve_sessions:
            raise PermissionDenied("You do not have permission to reject test sessions.")
        if session.status not in [
            SessionStatus.SUBMITTED,
            SessionStatus.PENDING_REVIEW,
            SessionStatus.UNDER_REVIEW,
        ]:
            raise ValidationError(
                f"Cannot reject a session in '{session.get_status_display()}' status."
            )
        if not reason or not reason.strip() or len(reason.strip()) < 10:
            raise ValidationError("A detailed technical rejection reason is mandatory (minimum 10 characters).")

        from_status = session.status
        clean_reason = reason.strip()
        now = timezone.now()

        with transaction.atomic():
            session.status = SessionStatus.REJECTED
            session.is_locked = False
            session.rejection_reason = clean_reason
            session.reviewer = reviewer
            session.rejected_at = now
            session.save(update_fields=["status", "is_locked", "rejection_reason", "reviewer", "rejected_at", "updated_at"])

            ApprovalHistory.objects.create(
                session=session,
                action=ApprovalAction.REJECT,
                from_status=from_status,
                to_status=SessionStatus.REJECTED,
                actor=reviewer,
                comments=clean_reason,
                metadata={
                    "reviewer": reviewer.full_name,
                    "rejected_at": now.isoformat(),
                },
            )

            log_action(
                user=reviewer,
                action=AuditAction.REJECT,
                obj=session,
                description=f"Session {session.session_number} returned/rejected. Reason: {clean_reason[:100]}",
                request=request,
            )

    @staticmethod
    def generate_report(session, user, request=None):
        """
        Move APPROVED → REPORT_GENERATED.
        Records formal report generation timestamp and authority.
        """
        if not user.can_generate_reports:
            raise PermissionDenied("You do not have permission to generate test reports.")
        if session.status not in [SessionStatus.APPROVED, SessionStatus.REPORT_GENERATED]:
            raise ValidationError(
                f"Cannot generate report for session in '{session.get_status_display()}' status. Record must be Approved."
            )

        from_status = session.status
        now = timezone.now()

        with transaction.atomic():
            session.status = SessionStatus.REPORT_GENERATED
            session.report_generated_at = now
            session.report_generated_by = user
            session.save(update_fields=["status", "report_generated_at", "report_generated_by", "updated_at"])

            ApprovalHistory.objects.create(
                session=session,
                action=ApprovalAction.GENERATE_REPORT,
                from_status=from_status,
                to_status=SessionStatus.REPORT_GENERATED,
                actor=user,
                comments=f"Formal report generated by {user.full_name}.",
                metadata={
                    "generated_at": now.isoformat(),
                    "generated_by": user.full_name,
                },
            )

            log_action(
                user=user,
                action=AuditAction.GENERATE,
                obj=session,
                description=f"Report generated for session {session.session_number} by {user.full_name}.",
                request=request,
            )

    @staticmethod
    def initiate_revision(session, user, revision_reason, request=None):
        """
        Controlled Revision Process:
        Approved / Report Generated records are immutable except via this controlled process.
        Requires an authorized reviewer or administrator and a mandatory change justification.
        Increments revision_number, unlocks record, and sets status back to UNDER_REVIEW.
        """
        if not user.can_approve_sessions:
            raise PermissionDenied("Only authorized reviewers or laboratory administrators can initiate revisions.")
        if session.status not in [SessionStatus.APPROVED, SessionStatus.REPORT_GENERATED]:
            raise ValidationError(
                f"Controlled revision is only applicable to Approved or Report Generated sessions (current: '{session.get_status_display()}')."
            )
        if not revision_reason or not revision_reason.strip() or len(revision_reason.strip()) < 15:
            raise ValidationError(
                "A formal change-control justification is mandatory to revise an approved record (minimum 15 characters)."
            )

        from_status = session.status
        clean_reason = revision_reason.strip()
        new_rev = (session.revision_number or 1) + 1

        with transaction.atomic():
            session.revision_number = new_rev
            session.revision_reason = clean_reason
            session.is_locked = False
            session.status = SessionStatus.UNDER_REVIEW
            session.save(update_fields=["revision_number", "revision_reason", "is_locked", "status", "updated_at"])

            ApprovalHistory.objects.create(
                session=session,
                action=ApprovalAction.REVISE,
                from_status=from_status,
                to_status=SessionStatus.UNDER_REVIEW,
                actor=user,
                comments=f"Controlled Revision #{new_rev} initiated: {clean_reason}",
                metadata={
                    "revision_number": new_rev,
                    "previous_status": from_status,
                    "justification": clean_reason,
                    "initiated_by": user.full_name,
                },
            )

            log_action(
                user=user,
                action=AuditAction.REVISION,
                obj=session,
                description=f"Session {session.session_number} revision #{new_rev} initiated by {user.full_name}.",
                request=request,
            )
