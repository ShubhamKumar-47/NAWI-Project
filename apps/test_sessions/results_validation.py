"""apps/test_sessions/results_validation.py – Test Results & Validation Service for OIML R 76.

Evaluates:
1. Test-wise result summaries
2. Individual measurement observations and calculation records
3. Calculated error tables & permissible errors
4. Pass / Fail / Unevaluated statuses
5. Missing data warnings (incomplete loading runs, <3 repetitions, missing eccentricity positions)
6. Invalid measurement & draft warnings
7. Procedure-wise status and Overall test status
8. Non-delegable compliance safeguard: A report must NEVER receive an overall PASS
   status if required tests are incomplete or applicable rules are unverified.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from apps.core.constants import PassFail, WeighingTestType
from calculations.models import CalculationCompliance, CalculationProcedureType, CalculationRecord
from calculations.services.coordinator import SessionCalculationCoordinator


@dataclass
class ProcedureValidationSummary:
    """Evaluation summary for a single OIML R 76 test procedure."""
    code: str
    name: str
    clause: str
    is_active: bool
    status: str  # "PASS" | "FAIL" | "INCOMPLETE" | "NOT_EVALUATED"
    total_count: int = 0
    draft_count: int = 0
    pass_count: int = 0
    fail_count: int = 0
    missing_warnings: List[str] = field(default_factory=list)
    invalid_warnings: List[str] = field(default_factory=list)
    rule_warnings: List[str] = field(default_factory=list)
    items: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SessionValidationReport:
    """Comprehensive laboratory validation report for an entire test session."""
    session_id: str
    session_number: str
    overall_status: str  # "PASS" | "FAIL" | "INCOMPLETE" | "NOT_EVALUATED"
    is_pass_eligible: bool
    is_submittable: bool
    total_procedures_active: int = 0
    total_observations: int = 0
    total_passed: int = 0
    total_failed: int = 0
    total_drafts: int = 0
    missing_data_warnings: List[str] = field(default_factory=list)
    invalid_measurement_warnings: List[str] = field(default_factory=list)
    unverified_rule_warnings: List[str] = field(default_factory=list)
    blocking_reasons: List[str] = field(default_factory=list)
    procedure_summaries: Dict[str, ProcedureValidationSummary] = field(default_factory=dict)


class ResultsValidationService:
    """
    Core validation and test result aggregation service.
    Validates completeness, consistency, draft states, and OIML R 76 compliance.
    """

    @classmethod
    def validate_session(cls, session, auto_calculate: bool = True) -> SessionValidationReport:
        """Analyze all active test procedures and return a comprehensive validation report."""
        if auto_calculate:
            # Ensure fresh calculation records exist for all measurements
            SessionCalculationCoordinator.evaluate_session(session)

        instrument = session.instrument
        calc_records = session.calculation_records.all()

        missing_warnings: List[str] = []
        invalid_warnings: List[str] = []
        rule_warnings: List[str] = []
        blocking_reasons: List[str] = []

        total_obs = 0
        total_pass = 0
        total_fail = 0
        total_drafts = 0

        summaries: Dict[str, ProcedureValidationSummary] = {}

        # ── 1. Initial Visual & Functional Examination ────────────────────────
        if session.proc_initial_examination:
            init_summary = ProcedureValidationSummary(
                code="initial_examination",
                name="Initial Visual & Functional Examination",
                clause="OIML R 76 §A.3 / §A.4",
                is_active=True,
                status="PASS" if session.initial_examination_passed else "FAIL",
                total_count=1,
            )
            if not session.initial_examination_passed:
                init_summary.fail_count = 1
                init_summary.invalid_warnings.append("Initial examination marked unsatisfactory.")
                total_fail += 1
            else:
                init_summary.pass_count = 1
                total_pass += 1
            total_obs += 1
            summaries["initial_examination"] = init_summary

        # ── 2. Zero-Setting & Tracking Tests ──────────────────────────────────
        if session.proc_zero_setting:
            zero_measurements = session.zero_setting_measurements.all()
            zero_calcs = calc_records.filter(procedure_type=CalculationProcedureType.ZERO_SETTING)
            z_count = zero_measurements.count()
            z_drafts = zero_measurements.filter(is_draft=True).count()
            z_fails = zero_calcs.filter(comparison_result=CalculationCompliance.FAIL).count()
            z_passes = zero_calcs.filter(comparison_result=CalculationCompliance.PASS).count()

            z_summary = ProcedureValidationSummary(
                code="zero_setting",
                name="Zero-Setting & Tracking Tests",
                clause="OIML R 76 §A.4.1 – §A.4.3",
                is_active=True,
                status="PENDING",
                total_count=z_count,
                draft_count=z_drafts,
                pass_count=z_passes,
                fail_count=z_fails,
            )

            if z_count == 0:
                z_summary.missing_warnings.append("No zero-setting observations recorded.")
                z_summary.status = "INCOMPLETE"
            elif z_drafts > 0:
                z_summary.invalid_warnings.append(f"{z_drafts} zero-setting observation(s) are in draft status.")
                z_summary.status = "INCOMPLETE"
            elif z_fails > 0 or not session.zero_test_passed:
                z_summary.status = "FAIL"
            else:
                z_summary.status = "PASS"

            # Populate row details
            for zm in zero_measurements:
                c_rec = zero_calcs.filter(measurement_reference_id=zm.pk).first()
                z_summary.items.append({
                    "id": zm.pk,
                    "title": zm.get_operation_type_display(),
                    "ref_load": Decimal("0"),
                    "indication": zm.zero_indication_after,
                    "zero_indication": zm.zero_indication_before,
                    "small_weight": zm.small_weight_added,
                    "error": zm.calculated_error,
                    "mpe": zm.mpe,
                    "status": "DRAFT" if zm.is_draft else zm.pass_fail,
                    "is_draft": zm.is_draft,
                    "explanation": c_rec.explanation if c_rec else "",
                })

            total_obs += z_count
            total_drafts += z_drafts
            total_pass += z_passes
            total_fail += z_fails
            summaries["zero_setting"] = z_summary

        # ── 3. Weighing Performance Tests ─────────────────────────────────────
        if session.proc_weighing:
            weigh_measurements = session.weighing_measurements.all()
            weigh_calcs = calc_records.filter(procedure_type=CalculationProcedureType.WEIGHING)
            w_count = weigh_measurements.count()
            w_drafts = weigh_measurements.filter(is_draft=True).count()
            w_inc = weigh_measurements.filter(test_type=WeighingTestType.INCREASING).count()
            w_dec = weigh_measurements.filter(test_type=WeighingTestType.DECREASING).count()
            w_fails = weigh_calcs.filter(comparison_result=CalculationCompliance.FAIL).count()
            w_passes = weigh_calcs.filter(comparison_result=CalculationCompliance.PASS).count()

            w_summary = ProcedureValidationSummary(
                code="weighing",
                name="Weighing Performance Test",
                clause="OIML R 76 §A.4.4 / §3.5 Table 1",
                is_active=True,
                status="PENDING",
                total_count=w_count,
                draft_count=w_drafts,
                pass_count=w_passes,
                fail_count=w_fails,
            )

            if w_count == 0:
                w_summary.missing_warnings.append("No weighing measurements recorded.")
                w_summary.status = "INCOMPLETE"
            else:
                if w_inc == 0:
                    w_summary.missing_warnings.append("No increasing load observations recorded.")
                if w_dec == 0:
                    w_summary.missing_warnings.append("No decreasing load observations recorded (unloading cycle required per §A.4.4).")
                if w_count < 5:
                    w_summary.missing_warnings.append(f"Only {w_count} weighing point(s) recorded. OIML R 76 §A.4.4 recommends at least 5 roughly equal steps up to Max.")
                if w_drafts > 0:
                    w_summary.invalid_warnings.append(f"{w_drafts} weighing observation(s) are in draft status.")

                if w_drafts > 0 or w_inc == 0:
                    w_summary.status = "INCOMPLETE"
                elif w_fails > 0:
                    w_summary.status = "FAIL"
                else:
                    w_summary.status = "PASS"

            # Populate row details
            for wm in weigh_measurements:
                c_rec = weigh_calcs.filter(measurement_reference_id=wm.pk).first()
                w_summary.items.append({
                    "id": wm.pk,
                    "title": f"{wm.test_type} #{wm.sequence_order} @ {wm.nominal_load}",
                    "test_type": wm.test_type,
                    "ref_load": wm.nominal_load,
                    "indication": wm.indication,
                    "zero_indication": wm.zero_indication,
                    "tare": wm.tare_applied,
                    "error": wm.error,
                    "mpe": wm.mpe,
                    "status": "DRAFT" if wm.is_draft else wm.pass_fail,
                    "is_draft": wm.is_draft,
                    "explanation": c_rec.explanation if c_rec else "",
                })

            total_obs += w_count
            total_drafts += w_drafts
            total_pass += w_passes
            total_fail += w_fails
            summaries["weighing"] = w_summary

        # ── 4. Repeatability Tests ────────────────────────────────────────────
        if session.proc_repeatability:
            rep_measurements = session.repeatability_measurements.all()
            rep_calcs = calc_records.filter(procedure_type=CalculationProcedureType.REPEATABILITY)
            r_count = rep_measurements.count()
            r_drafts = rep_measurements.filter(is_draft=True).count()
            r_fails = rep_calcs.filter(comparison_result=CalculationCompliance.FAIL).count()
            r_passes = rep_calcs.filter(comparison_result=CalculationCompliance.PASS).count()

            r_summary = ProcedureValidationSummary(
                code="repeatability",
                name="Repeatability Test",
                clause="OIML R 76 §A.4.10 / §3.6.1",
                is_active=True,
                status="PENDING",
                total_count=r_count,
                draft_count=r_drafts,
                pass_count=r_passes,
                fail_count=r_fails,
            )

            # Analyze series groupings
            series_groups = {}
            for rm in rep_measurements:
                s_name = rm.series_name or "Series 1"
                series_groups.setdefault(s_name, []).append(rm)

            if r_count == 0:
                r_summary.missing_warnings.append("No repeatability observations recorded.")
                r_summary.status = "INCOMPLETE"
            else:
                for s_name, s_items in series_groups.items():
                    if len(s_items) < 3:
                        r_summary.missing_warnings.append(
                            f"Series '{s_name}' has only {len(s_items)} repetition(s). Minimum 3 repetitions required per OIML R 76 §A.4.10."
                        )
                if r_drafts > 0:
                    r_summary.invalid_warnings.append(f"{r_drafts} repeatability observation(s) are in draft status.")

                has_short_series = any(len(v) < 3 for v in series_groups.values())
                if r_drafts > 0 or has_short_series:
                    r_summary.status = "INCOMPLETE"
                elif r_fails > 0:
                    r_summary.status = "FAIL"
                else:
                    r_summary.status = "PASS"

            # Populate row details
            for rm in rep_measurements:
                c_rec = rep_calcs.filter(title__contains=rm.series_name).first() if rm.series_name else None
                r_summary.items.append({
                    "id": rm.pk,
                    "title": f"{rm.series_name} Rep #{rm.repetition_number}",
                    "ref_load": rm.nominal_load,
                    "indication": rm.indication,
                    "zero_indication": rm.zero_indication,
                    "error": rm.error,
                    "mpe": rm.mpe,
                    "status": "DRAFT" if rm.is_draft else rm.pass_fail,
                    "is_draft": rm.is_draft,
                    "explanation": c_rec.explanation if c_rec else "",
                })

            total_obs += r_count
            total_drafts += r_drafts
            total_pass += r_passes
            total_fail += r_fails
            summaries["repeatability"] = r_summary

        # ── 5. Eccentricity Tests ─────────────────────────────────────────────
        if session.proc_eccentricity:
            ecc_measurements = session.eccentricity_measurements.all()
            ecc_calcs = calc_records.filter(procedure_type=CalculationProcedureType.ECCENTRICITY)
            e_count = ecc_measurements.count()
            e_drafts = ecc_measurements.filter(is_draft=True).count()
            e_fails = ecc_calcs.filter(comparison_result=CalculationCompliance.FAIL).count()
            e_passes = ecc_calcs.filter(comparison_result=CalculationCompliance.PASS).count()

            e_summary = ProcedureValidationSummary(
                code="eccentricity",
                name="Eccentricity (Off-Centre Loading) Test",
                clause="OIML R 76 §A.4.7 / §3.6.2",
                is_active=True,
                status="PENDING",
                total_count=e_count,
                draft_count=e_drafts,
                pass_count=e_passes,
                fail_count=e_fails,
            )

            standard_positions = ["CENTRE", "FRONT_LEFT", "BACK_LEFT", "BACK_RIGHT", "FRONT_RIGHT"]
            recorded_positions = [em.load_position for em in ecc_measurements]
            missing_pos = [p for p in standard_positions if p not in recorded_positions]

            if e_count == 0:
                e_summary.missing_warnings.append("No eccentricity observations recorded.")
                e_summary.status = "INCOMPLETE"
            else:
                if missing_pos:
                    e_summary.missing_warnings.append(
                        f"Missing standard receptor position(s): {', '.join(missing_pos)}."
                    )
                if e_drafts > 0:
                    e_summary.invalid_warnings.append(f"{e_drafts} eccentricity observation(s) are in draft status.")

                if e_drafts > 0 or missing_pos:
                    e_summary.status = "INCOMPLETE"
                elif e_fails > 0:
                    e_summary.status = "FAIL"
                else:
                    e_summary.status = "PASS"

            # Populate row details
            for em in ecc_measurements:
                c_rec = ecc_calcs.filter(measurement_reference_id=em.pk).first()
                e_summary.items.append({
                    "id": em.pk,
                    "title": em.get_load_position_display(),
                    "ref_load": em.nominal_load,
                    "indication": em.indication,
                    "zero_indication": em.zero_indication,
                    "error": em.error,
                    "mpe": em.mpe,
                    "status": "DRAFT" if em.is_draft else em.pass_fail,
                    "is_draft": em.is_draft,
                    "explanation": c_rec.explanation if c_rec else "",
                })

            total_obs += e_count
            total_drafts += e_drafts
            total_pass += e_passes
            total_fail += e_fails
            summaries["eccentricity"] = e_summary

        # ── 6. Discrimination Tests ───────────────────────────────────────────
        if session.proc_discrimination:
            disc_measurements = session.discrimination_measurements.all()
            disc_calcs = calc_records.filter(procedure_type=CalculationProcedureType.DISCRIMINATION)
            d_count = disc_measurements.count()
            d_drafts = disc_measurements.filter(is_draft=True).count()
            d_fails = disc_calcs.filter(comparison_result=CalculationCompliance.FAIL).count()
            d_passes = disc_calcs.filter(comparison_result=CalculationCompliance.PASS).count()

            d_summary = ProcedureValidationSummary(
                code="discrimination",
                name="Discrimination Test",
                clause="OIML R 76 §A.4.8 / §3.8",
                is_active=True,
                status="PENDING",
                total_count=d_count,
                draft_count=d_drafts,
                pass_count=d_passes,
                fail_count=d_fails,
            )

            if d_count == 0:
                d_summary.missing_warnings.append("No discrimination tests recorded.")
                d_summary.status = "INCOMPLETE"
            elif d_drafts > 0:
                d_summary.invalid_warnings.append(f"{d_drafts} discrimination check(s) are in draft status.")
                d_summary.status = "INCOMPLETE"
            elif d_fails > 0:
                d_summary.status = "FAIL"
            else:
                d_summary.status = "PASS"

            for dm in disc_measurements:
                c_rec = disc_calcs.filter(measurement_reference_id=dm.pk).first()
                d_summary.items.append({
                    "id": dm.pk,
                    "title": f"Discrimination @ {dm.test_load} {instrument.unit_of_measure}",
                    "ref_load": dm.test_load,
                    "indication_before": dm.indication_before,
                    "small_weight": dm.small_weight_added,
                    "indication_after": dm.indication_after,
                    "change": dm.change,
                    "mpe": instrument.scale_interval,
                    "status": "DRAFT" if dm.is_draft else dm.pass_fail,
                    "is_draft": dm.is_draft,
                    "explanation": c_rec.explanation if c_rec else "",
                })

            total_obs += d_count
            total_drafts += d_drafts
            total_pass += d_passes
            total_fail += d_fails
            summaries["discrimination"] = d_summary

        # ── 7. Tare Weighing Tests ────────────────────────────────────────────
        if session.proc_tare:
            tare_measurements = session.tare_measurements.all()
            tare_calcs = calc_records.filter(procedure_type=CalculationProcedureType.TARE)
            t_count = tare_measurements.count()
            t_drafts = tare_measurements.filter(is_draft=True).count()
            t_fails = tare_calcs.filter(comparison_result=CalculationCompliance.FAIL).count()
            t_passes = tare_calcs.filter(comparison_result=CalculationCompliance.PASS).count()

            t_summary = ProcedureValidationSummary(
                code="tare",
                name="Tare Weighing Test",
                clause="OIML R 76 §A.4.6 / §3.5.3",
                is_active=True,
                status="PENDING",
                total_count=t_count,
                draft_count=t_drafts,
                pass_count=t_passes,
                fail_count=t_fails,
            )

            if t_count == 0:
                t_summary.missing_warnings.append("No tare weighing observations recorded.")
                t_summary.status = "INCOMPLETE"
            elif t_drafts > 0:
                t_summary.invalid_warnings.append(f"{t_drafts} tare observation(s) are in draft status.")
                t_summary.status = "INCOMPLETE"
            elif t_fails > 0:
                t_summary.status = "FAIL"
            else:
                t_summary.status = "PASS"

            for tm in tare_measurements:
                c_rec = tare_calcs.filter(measurement_reference_id=tm.pk).first()
                t_summary.items.append({
                    "id": tm.pk,
                    "title": f"Tare Test @ {tm.tare_load} {instrument.unit_of_measure}",
                    "ref_load": tm.tare_load,
                    "net_load": tm.net_load,
                    "gross_indication": tm.gross_indication,
                    "net_indication": tm.net_indication,
                    "error": tm.error,
                    "mpe": tm.mpe,
                    "status": "DRAFT" if tm.is_draft else tm.pass_fail,
                    "is_draft": tm.is_draft,
                    "explanation": c_rec.explanation if c_rec else "",
                })

            total_obs += t_count
            total_drafts += t_drafts
            total_pass += t_passes
            total_fail += t_fails
            summaries["tare"] = t_summary

        # ── Check Unverified Rules in Calculation Records ─────────────────────
        unverified_recs = calc_records.filter(is_rule_configured=False)
        if unverified_recs.exists():
            rule_msg = (
                f"There are {unverified_recs.count()} unverified/unconfigured rule evaluation(s) in this session. "
                "Compliance decisions cannot be granted for unverified rules."
            )
            rule_warnings.append(rule_msg)
            blocking_reasons.append(rule_msg)

        # Collect all procedure warnings
        for p_code, p_sum in summaries.items():
            missing_warnings.extend(p_sum.missing_warnings)
            invalid_warnings.extend(p_sum.invalid_warnings)

        # ── Non-Delegable Compliance Determination ────────────────────────────
        # "A report must not receive an overall PASS status if required tests
        # are incomplete or applicable rules are unverified."
        any_procedure_failed = any(s.status == "FAIL" for s in summaries.values())
        any_procedure_incomplete = any(s.status == "INCOMPLETE" for s in summaries.values())
        has_unverified_rules = len(rule_warnings) > 0
        has_pending_drafts = total_drafts > 0

        if any_procedure_incomplete:
            blocking_reasons.append("One or more active test procedures have incomplete or missing observation data.")
        if has_pending_drafts:
            blocking_reasons.append(f"{total_drafts} observation(s) remain in preliminary draft status.")

        if any_procedure_failed:
            overall_status = "FAIL"
            is_pass_eligible = False
            is_submittable = True  # Can submit a completed failing report for reviewer decision
        elif any_procedure_incomplete or has_pending_drafts:
            overall_status = "INCOMPLETE"
            is_pass_eligible = False
            is_submittable = False  # Incomplete reports cannot be submitted for formal review
        elif has_unverified_rules:
            overall_status = "UNVERIFIED_RULES"
            is_pass_eligible = False
            is_submittable = False
        elif len(summaries) > 0 and all(s.status == "PASS" for s in summaries.values()):
            overall_status = "PASS"
            is_pass_eligible = True
            is_submittable = True
        else:
            overall_status = "INCOMPLETE"
            is_pass_eligible = False
            is_submittable = False

        # Keep session overall_result synchronized
        session.overall_result = overall_status if overall_status in ["PASS", "FAIL"] else "PENDING"
        session.save(update_fields=["overall_result"])

        return SessionValidationReport(
            session_id=str(session.pk),
            session_number=session.session_number,
            overall_status=overall_status,
            is_pass_eligible=is_pass_eligible,
            is_submittable=is_submittable,
            total_procedures_active=len(summaries),
            total_observations=total_obs,
            total_passed=total_pass,
            total_failed=total_fail,
            total_drafts=total_drafts,
            missing_data_warnings=missing_warnings,
            invalid_measurement_warnings=invalid_warnings,
            unverified_rule_warnings=rule_warnings,
            blocking_reasons=blocking_reasons,
            procedure_summaries=summaries,
        )

