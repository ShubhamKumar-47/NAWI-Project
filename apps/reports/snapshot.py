"""apps/reports/snapshot.py – Point-in-time metrological data snapshot generator.

Captures complete immutable JSON representations of approved test sessions,
instruments, measurement observations, and calculation results for ISO/IEC 17025 audit traceability.
"""
from decimal import Decimal


def serialize_val(val):
    """Serialize Decimals, dates, and non-primitives into clean strings or numbers."""
    if val is None:
        return None
    if isinstance(val, Decimal):
        return f"{val:g}"
    return str(val)


def create_session_snapshot(session) -> dict:
    """
    Construct a complete point-in-time metrological snapshot of a test session.
    Ensures that historical reports retain their exact data state even if the session
    is subsequent opened for a controlled revision.
    """
    inst = session.instrument
    org = session.organization

    # 1. Instrument Specifications
    uom = inst.unit_of_measure or "g"
    n_intervals = str(inst.n_max) if inst.n_max else (
        str(int(Decimal(str(inst.max_capacity)) / Decimal(str(inst.actual_scale_interval))))
        if inst.actual_scale_interval and inst.max_capacity else "—"
    )

    instrument_data = {
        "id": str(inst.pk),
        "name": inst.display_name,
        "manufacturer": inst.manufacturer or "—",
        "model_name": inst.model_name or "—",
        "serial_number": inst.serial_number,
        "accuracy_class": inst.accuracy_class,
        "accuracy_class_display": inst.get_accuracy_class_display(),
        "max_capacity": serialize_val(inst.max_capacity),
        "min_capacity": serialize_val(inst.min_capacity),
        "scale_interval": serialize_val(inst.scale_interval),
        "actual_scale_interval": serialize_val(inst.actual_scale_interval),
        "n_max": n_intervals,
        "unit": uom,
        "customer_name": inst.customer_name or "—",
        "location": inst.location or "—",
        "approval_number": inst.approval_number or "—",
        "year_of_manufacture": inst.year_of_manufacture,
    }

    # 2. Test Session & Governance Details
    session_data = {
        "session_id": str(session.pk),
        "session_number": session.session_number,
        "lab_reference_number": session.lab_reference_number or "—",
        "test_date": session.test_date.strftime("%Y-%m-%d") if session.test_date else None,
        "test_location": session.test_location or "—",
        "status": session.status,
        "status_display": session.get_status_display(),
        "overall_result": session.overall_result,
        "revision_number": session.revision_number or 1,
        "revision_reason": session.revision_reason or "—",
        "oiml_edition": session.oiml_edition,
        "oiml_edition_display": session.get_oiml_edition_display(),
        "technician": session.technician.full_name if session.technician else "—",
        "technician_title": getattr(session.technician, "job_title", "") or "Metrologist",
        "reviewer": session.reviewer.full_name if session.reviewer else "—",
        "reviewer_title": getattr(session.reviewer, "job_title", "") or "Authorized Reviewer",
        "approved_at": session.approved_at.isoformat() if session.approved_at else None,
        "temperature_start": serialize_val(session.temperature_start),
        "temperature_end": serialize_val(session.temperature_end),
        "humidity_start": serialize_val(session.humidity_start),
        "humidity_end": serialize_val(session.humidity_end),
        "reference_standards": session.reference_standards or "—",
        "initial_examination_passed": session.initial_examination_passed,
        "initial_examination_notes": session.initial_examination_notes or "—",
        "zero_test_passed": session.zero_test_passed,
        "zero_test_notes": session.zero_test_notes or "—",
        "remarks": session.remarks or session.notes or "—",
    }

    # 3. Observation Datasets
    weighing_data = [
        {
            "sequence_order": m.sequence_order,
            "test_type": m.test_type,
            "nominal_load": serialize_val(m.nominal_load),
            "indication": serialize_val(m.indication),
            "zero_indication": serialize_val(m.zero_indication),
            "error": serialize_val(m.error),
            "mpe": serialize_val(m.mpe),
            "pass_fail": m.pass_fail,
        }
        for m in session.weighing_measurements.all().order_by("test_type", "sequence_order")
    ]

    repeatability_data = [
        {
            "series_name": m.series_name,
            "repetition_number": m.repetition_number,
            "nominal_load": serialize_val(m.nominal_load),
            "indication": serialize_val(m.indication),
            "error": serialize_val(m.error),
            "mpe": serialize_val(m.mpe),
            "pass_fail": m.pass_fail,
        }
        for m in session.repeatability_measurements.all().order_by("series_name", "repetition_number")
    ]

    eccentricity_data = [
        {
            "load_position": m.load_position,
            "load_position_display": m.get_load_position_display(),
            "nominal_load": serialize_val(m.nominal_load),
            "indication": serialize_val(m.indication),
            "error": serialize_val(m.error),
            "mpe": serialize_val(m.mpe),
            "pass_fail": m.pass_fail,
        }
        for m in session.eccentricity_measurements.all().order_by("load_position")
    ]

    discrimination_data = [
        {
            "test_load": serialize_val(m.test_load),
            "indication_before": serialize_val(m.indication_before),
            "small_weight_added": serialize_val(m.small_weight_added),
            "indication_after": serialize_val(m.indication_after),
            "change": serialize_val(m.change),
            "pass_fail": m.pass_fail,
        }
        for m in session.discrimination_measurements.all()
    ]

    tare_data = [
        {
            "tare_load": serialize_val(m.tare_load),
            "gross_indication": serialize_val(m.gross_indication),
            "net_indication": serialize_val(m.net_indication),
            "error": serialize_val(m.error),
            "mpe": serialize_val(m.mpe),
            "pass_fail": m.pass_fail,
        }
        for m in session.tare_measurements.all().order_by("tare_load")
    ]

    zero_setting_data = [
        {
            "operation_type": m.get_operation_type_display(),
            "zero_indication_before": serialize_val(m.zero_indication_before),
            "zero_indication_after": serialize_val(m.zero_indication_after),
            "calculated_error": serialize_val(m.calculated_error),
            "mpe": serialize_val(m.mpe),
            "pass_fail": m.pass_fail,
        }
        for m in session.zero_setting_measurements.all()
    ]

    # 4. Approval History Summary
    approval_history_data = [
        {
            "action": h.action,
            "action_display": h.get_action_display(),
            "actor": h.actor.full_name if h.actor else "System",
            "timestamp": h.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "comments": h.comments,
        }
        for h in session.approval_history.all().order_by("created_at")
    ]

    return {
        "instrument": instrument_data,
        "session": session_data,
        "organization": {
            "name": org.name if org else "—",
            "accreditation_number": org.accreditation_number if org else "—",
        },
        "observations": {
            "weighing": weighing_data,
            "repeatability": repeatability_data,
            "eccentricity": eccentricity_data,
            "discrimination": discrimination_data,
            "tare": tare_data,
            "zero_setting": zero_setting_data,
        },
        "approval_history": approval_history_data,
        "counts": {
            "weighing_points": len(weighing_data),
            "repeatability_points": len(repeatability_data),
            "eccentricity_points": len(eccentricity_data),
            "discrimination_points": len(discrimination_data),
            "tare_points": len(tare_data),
            "zero_points": len(zero_setting_data),
        }
    }

