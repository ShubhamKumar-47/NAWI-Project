"""calculations/services/coordinator.py – Orchestrates full session calculations and persistence."""
from typing import List, Optional
from django.db import transaction

from apps.core.constants import PassFail
from calculations.models import CalculationCompliance, CalculationRecord
from .weighing_performance import WeighingPerformanceService
from .repeatability import RepeatabilityService
from .eccentricity import EccentricityService
from .zero_tests import ZeroTestsService
from .discrimination import DiscriminationService
from .tare import TareService


class SessionCalculationCoordinator:
    """
    Automated Engine Coordinator.
    Runs calculation services across all raw measurement observations in a TestSession,
    persisting CalculationRecords with full audit traceability and evaluating overall result.
    """

    @classmethod
    def evaluate_session(cls, session, calculated_by=None) -> List[CalculationRecord]:
        """Execute automated calculations for all observations in the session."""
        instrument = session.instrument
        raw_edition = getattr(session, "oiml_edition", "OIML R 76-1:2006")
        if "2006" in str(raw_edition):
            standard_edition = "OIML R 76-1:2006"
        elif "1992" in str(raw_edition):
            standard_edition = "OIML R 76-1:1992"
        else:
            standard_edition = raw_edition or "OIML R 76-1:2006"
        accuracy_class = instrument.accuracy_class
        actual_scale_interval = instrument.actual_scale_interval
        scale_interval = instrument.scale_interval

        records: List[CalculationRecord] = []

        with transaction.atomic():
            # 1. Weighing Performance
            weighing_measurements = session.weighing_measurements.all().order_by("test_type", "sequence_order", "id")
            for idx, wm in enumerate(weighing_measurements):
                rec = WeighingPerformanceService.save_record(
                    session=session,
                    nominal_load=wm.nominal_load,
                    indication=wm.indication,
                    accuracy_class=accuracy_class,
                    actual_scale_interval=actual_scale_interval,
                    scale_interval=scale_interval,
                    zero_indication=wm.zero_indication,
                    sequence_number=idx + 1,
                    title=f"Weighing ({wm.test_type}) @ {wm.nominal_load} {instrument.unit_of_measure}",
                    measurement_id=wm.pk,
                    calculated_by=calculated_by,
                    standard_edition=standard_edition,
                )
                # Keep source observation record synced
                wm.error = rec.calculated_error
                wm.mpe = rec.permissible_error_mpe
                wm.pass_fail = PassFail.PASS if rec.comparison_result == CalculationCompliance.PASS else (
                    PassFail.FAIL if rec.comparison_result == CalculationCompliance.FAIL else PassFail.PENDING
                )
                wm.save(update_fields=["error", "mpe", "pass_fail"])
                records.append(rec)

            # 2. Repeatability (grouped by series_name)
            rep_series_map = {}
            for rm in session.repeatability_measurements.all().order_by("series_name", "repetition_number"):
                s_key = rm.series_name or "Series 1"
                if s_key not in rep_series_map:
                    rep_series_map[s_key] = {
                        "nominal_load": rm.nominal_load,
                        "indications": [],
                        "models": [],
                    }
                rep_series_map[s_key]["indications"].append(rm.indication)
                rep_series_map[s_key]["models"].append(rm)

            for s_idx, (s_name, s_data) in enumerate(rep_series_map.items()):
                if len(s_data["indications"]) >= 3:
                    rec = RepeatabilityService.save_record(
                        session=session,
                        nominal_load=s_data["nominal_load"],
                        indications=s_data["indications"],
                        accuracy_class=accuracy_class,
                        actual_scale_interval=actual_scale_interval,
                        sequence_number=s_idx + 1,
                        series_name=s_name,
                        calculated_by=calculated_by,
                        standard_edition=standard_edition,
                    )
                    # Update each measurement in the series
                    for m_row in s_data["models"]:
                        m_row.mpe = rec.permissible_error_mpe
                        m_row.pass_fail = PassFail.PASS if rec.comparison_result == CalculationCompliance.PASS else PassFail.FAIL
                        m_row.save(update_fields=["mpe", "pass_fail"])
                    records.append(rec)

            # 3. Eccentricity
            ecc_measurements = session.eccentricity_measurements.all().order_by("load_position")
            for idx, em in enumerate(ecc_measurements):
                rec = EccentricityService.save_record(
                    session=session,
                    nominal_load=em.nominal_load,
                    indication=em.indication,
                    position=em.load_position,
                    accuracy_class=accuracy_class,
                    actual_scale_interval=actual_scale_interval,
                    sequence_number=idx + 1,
                    zero_indication=em.zero_indication,
                    measurement_id=em.pk,
                    calculated_by=calculated_by,
                    standard_edition=standard_edition,
                )
                em.error = rec.calculated_error
                em.mpe = rec.permissible_error_mpe
                em.pass_fail = PassFail.PASS if rec.comparison_result == CalculationCompliance.PASS else PassFail.FAIL
                em.save(update_fields=["error", "mpe", "pass_fail"])
                records.append(rec)

            # 4. Discrimination
            disc_measurements = session.discrimination_measurements.all().order_by("id")
            for idx, dm in enumerate(disc_measurements):
                rec = DiscriminationService.save_record(
                    session=session,
                    test_load=dm.test_load,
                    indication_before=dm.indication_before,
                    small_weight_added=dm.small_weight_added,
                    indication_after=dm.indication_after,
                    scale_interval=scale_interval,
                    sequence_number=idx + 1,
                    measurement_id=dm.pk,
                    calculated_by=calculated_by,
                    standard_edition=standard_edition,
                )
                dm.change = rec.calculated_error
                dm.pass_fail = PassFail.PASS if rec.comparison_result == CalculationCompliance.PASS else PassFail.FAIL
                dm.save(update_fields=["change", "pass_fail"])
                records.append(rec)

            # 5. Tare Weighing
            tare_measurements = session.tare_measurements.all().order_by("tare_load", "id")
            for idx, tm in enumerate(tare_measurements):
                rec = TareService.save_record(
                    session=session,
                    tare_load=tm.tare_load,
                    gross_indication=tm.gross_indication,
                    net_indication=tm.net_indication,
                    accuracy_class=accuracy_class,
                    actual_scale_interval=actual_scale_interval,
                    net_load=tm.net_load,
                    sequence_number=idx + 1,
                    measurement_id=tm.pk,
                    calculated_by=calculated_by,
                    standard_edition=standard_edition,
                )
                tm.error = rec.calculated_error
                tm.mpe = rec.permissible_error_mpe
                tm.pass_fail = PassFail.PASS if rec.comparison_result == CalculationCompliance.PASS else PassFail.FAIL
                tm.save(update_fields=["error", "mpe", "pass_fail"])
                records.append(rec)

            # 6. Zero-Setting & Tracking
            zero_measurements = session.zero_setting_measurements.all().order_by("operation_type", "-created_at")
            for idx, zm in enumerate(zero_measurements):
                rec = ZeroTestsService.save_record(
                    session=session,
                    zero_indication_after=zm.zero_indication_after,
                    scale_interval=scale_interval,
                    actual_scale_interval=actual_scale_interval,
                    sequence_number=idx + 1,
                    zero_indication_before=zm.zero_indication_before,
                    small_weight_added=zm.small_weight_added,
                    operation_type=zm.operation_type,
                    measurement_id=zm.pk,
                    calculated_by=calculated_by,
                    standard_edition=standard_edition,
                )
                zm.calculated_error = rec.calculated_error
                zm.mpe = rec.permissible_error_mpe
                zm.pass_fail = PassFail.PASS if rec.comparison_result == CalculationCompliance.PASS else PassFail.FAIL
                zm.save(update_fields=["calculated_error", "mpe", "pass_fail"])
                records.append(rec)

            # Overall compliance evaluation for the session
            has_fail = CalculationRecord.objects.filter(session=session, comparison_result=CalculationCompliance.FAIL).exists()
            total_records = CalculationRecord.objects.filter(session=session).count()

            if has_fail:
                session.overall_result = "FAIL"
            elif total_records > 0 and not CalculationRecord.objects.filter(
                session=session, comparison_result=CalculationCompliance.NOT_EVALUATED
            ).exists():
                session.overall_result = "PASS"
            else:
                session.overall_result = "PENDING"

            session.save(update_fields=["overall_result"])

        return records
