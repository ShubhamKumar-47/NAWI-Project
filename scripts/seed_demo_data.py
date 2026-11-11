"""scripts/seed_demo_data.py – Create demo organization, users, instruments, and test sessions."""
import os
import sys
import django
from decimal import Decimal
import datetime

# Set up Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from apps.accounts.models import Organization, CustomUser
from apps.core.constants import UserRole, AccuracyClass, InstrumentStatus, SessionStatus
from apps.instruments.models import Instrument
from apps.test_sessions.models import TestSession


def run():
    print("Seeding comprehensive data for NAWI Test Report Management System...")
    today = datetime.date.today()

    # 1. Organization
    org, _ = Organization.objects.get_or_create(
        name="National Metrology & Calibration Institute",
        defaults={
            "accreditation_number": "ISO-17025-MET-2026-001",
            "address": "Metrology Park, Sector 4, Technical Zone",
            "phone": "+1 (555) 019-2831",
            "email": "lab@nawi-metrology.org",
            "website": "https://nawi-metrology.org",
            "is_active": True,
        },
    )

    # 2. Users
    def make_user(email, username, first_name, last_name, role, password):
        user, created = CustomUser.objects.get_or_create(
            email=email,
            defaults={
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "role": role,
                "organization": org,
                "is_staff": (role in [UserRole.ADMINISTRATOR, UserRole.SUPERADMIN]),
                "is_superuser": (role in [UserRole.ADMINISTRATOR, UserRole.SUPERADMIN]),
                "must_change_password": False,
                "is_active": True,
            },
        )
        if created:
            user.set_password(password)
            user.save()
        return user

    admin = make_user("admin@nawi.local", "admin", "System", "Administrator", UserRole.ADMINISTRATOR, "Admin@12345")
    manager = make_user("manager@nawi.local", "manager", "Alice", "Vance", UserRole.LAB_MANAGER, "Manager@12345")
    tech = make_user("tech@nawi.local", "tech", "David", "Miller", UserRole.LAB_OPERATOR, "Tech@12345")
    reviewer = make_user("reviewer@nawi.local", "reviewer", "Elena", "Rostova", UserRole.REVIEWER, "Reviewer@12345")

    # 3. Instruments across all 4 Accuracy Classes
    instruments_data = [
        {
            "serial_number": "MET-2026-X15",
            "instrument_name": "Precision Bench Scale",
            "manufacturer": "Sartorius Industrial",
            "model_name": "Signum Pro 15",
            "model_number": "SIG-15P",
            "instrument_type": "Bench Scale",
            "year_of_manufacture": 2023,
            "accuracy_class": AccuracyClass.CLASS_III,
            "max_capacity": Decimal("15.0000"),
            "min_capacity": Decimal("0.1000"),
            "scale_interval": Decimal("0.0050"),
            "actual_scale_interval": Decimal("0.0050"),
            "unit_of_measurement": "kg",
            "customer_name": "Acme Pharmaceuticals Ltd",
            "lab_reference_number": "LAB-INS-2026-001",
            "location": "Calibration Bay A-2",
            "description": "Stainless steel bench platform scale with backlit graphic terminal and IP65 protection.",
            "status": InstrumentStatus.IN_PROGRESS,
            "received_date": today - datetime.timedelta(days=20),
            "registration_date": today - datetime.timedelta(days=20),
        },
        {
            "serial_number": "XP205-MICRO-01",
            "instrument_name": "Micro-Analytical Dual Range Balance",
            "manufacturer": "Mettler Toledo",
            "model_name": "XP205 Analytical",
            "model_number": "XP205-DR",
            "instrument_type": "Analytical Balance",
            "year_of_manufacture": 2024,
            "accuracy_class": AccuracyClass.CLASS_I,
            "max_capacity": Decimal("0.2200"),
            "min_capacity": Decimal("0.0010"),
            "scale_interval": Decimal("0.00001"),
            "actual_scale_interval": Decimal("0.0010"),
            "unit_of_measurement": "g",
            "customer_name": "BioHealth Genomics Center",
            "lab_reference_number": "LAB-INS-2026-002",
            "location": "Cleanroom Suite 1",
            "description": "High precision dual-range microbalance equipped with motorized glass draft shield.",
            "status": InstrumentStatus.IN_LAB,
            "received_date": today - datetime.timedelta(days=12),
            "registration_date": today - datetime.timedelta(days=12),
        },
        {
            "serial_number": "KERN-KB-1200",
            "instrument_name": "Top-Loading Precision Balance",
            "manufacturer": "Kern & Sohn",
            "model_name": "KB 1200-2N",
            "model_number": "KB-1200-2N",
            "instrument_type": "Precision Balance",
            "year_of_manufacture": 2022,
            "accuracy_class": AccuracyClass.CLASS_II,
            "max_capacity": Decimal("1.2000"),
            "min_capacity": Decimal("0.0200"),
            "scale_interval": Decimal("0.0001"),
            "actual_scale_interval": Decimal("0.0010"),
            "unit_of_measurement": "kg",
            "customer_name": "Advanced Materials Testing Lab",
            "lab_reference_number": "LAB-INS-2026-003",
            "location": "Materials Test Bay 4",
            "description": "Precision balance with ring-shaped draft shield, external calibration, and RS-232 interface.",
            "status": InstrumentStatus.TESTED,
            "received_date": today - datetime.timedelta(days=45),
            "registration_date": today - datetime.timedelta(days=45),
        },
        {
            "serial_number": "OHAUS-DEF-60",
            "instrument_name": "Industrial Platform Bench Scale",
            "manufacturer": "OHAUS Corporation",
            "model_name": "Defender 3000",
            "model_number": "D31P60BR",
            "instrument_type": "Platform Scale",
            "year_of_manufacture": 2023,
            "accuracy_class": AccuracyClass.CLASS_III,
            "max_capacity": Decimal("60.0000"),
            "min_capacity": Decimal("0.4000"),
            "scale_interval": Decimal("0.0200"),
            "actual_scale_interval": Decimal("0.0200"),
            "unit_of_measurement": "kg",
            "customer_name": "Global Express Freight",
            "lab_reference_number": "LAB-INS-2026-004",
            "location": "Warehouse Reception Bay",
            "description": "Heavy duty painted steel tubular base with 304 stainless steel pan and column mount.",
            "status": InstrumentStatus.TESTED,
            "received_date": today - datetime.timedelta(days=60),
            "registration_date": today - datetime.timedelta(days=60),
        },
        {
            "serial_number": "AVERY-BR-3000",
            "instrument_name": "Vehicle Weighbridge Scale",
            "manufacturer": "Avery Weigh-Tronix",
            "model_name": "BridgeScale 30T",
            "model_number": "BS-30T-STEEL",
            "instrument_type": "Weighbridge / Truck Scale",
            "year_of_manufacture": 2021,
            "accuracy_class": AccuracyClass.CLASS_IIII,
            "max_capacity": Decimal("30000.0000"),
            "min_capacity": Decimal("200.0000"),
            "scale_interval": Decimal("10.0000"),
            "actual_scale_interval": Decimal("10.0000"),
            "unit_of_measurement": "kg",
            "customer_name": "Metro Logistics Terminal",
            "lab_reference_number": "LAB-INS-2026-005",
            "location": "Outdoor Weighbridge Pit 1",
            "description": "Multi-cell pitless modular steel deck weighbridge with hermetically sealed canister load cells.",
            "status": InstrumentStatus.IN_LAB,
            "received_date": today - datetime.timedelta(days=5),
            "registration_date": today - datetime.timedelta(days=5),
        },
    ]

    instruments = []
    for d in instruments_data:
        inst, created = Instrument.objects.get_or_create(
            organization=org,
            serial_number=d["serial_number"],
            defaults={
                "instrument_name": d["instrument_name"],
                "manufacturer": d["manufacturer"],
                "model_name": d["model_name"],
                "model_number": d["model_number"],
                "instrument_type": d["instrument_type"],
                "year_of_manufacture": d["year_of_manufacture"],
                "accuracy_class": d["accuracy_class"],
                "max_capacity": d["max_capacity"],
                "min_capacity": d["min_capacity"],
                "scale_interval": d["scale_interval"],
                "actual_scale_interval": d["actual_scale_interval"],
                "unit_of_measurement": d["unit_of_measurement"],
                "customer_name": d["customer_name"],
                "lab_reference_number": d["lab_reference_number"],
                "location": d["location"],
                "description": d["description"],
                "status": d["status"],
                "received_date": d["received_date"],
                "registration_date": d["registration_date"],
                "created_by": admin,
            },
        )
        if not created:
            for field, val in d.items():
                setattr(inst, field, val)
            inst.save()
        instruments.append(inst)

    # 4. Test Records across multiple months & statuses
    sessions_data = [
        # In Progress (current)
        {
            "session_number": "TS-202611-001",
            "instrument": instruments[0],
            "test_date": today - datetime.timedelta(days=1),
            "status": SessionStatus.IN_PROGRESS,
            "result": "PENDING",
            "reviewer": reviewer,
        },
        # Pending Approval 1
        {
            "session_number": "TS-202611-002",
            "instrument": instruments[1],
            "test_date": today - datetime.timedelta(days=2),
            "status": SessionStatus.PENDING_REVIEW,
            "result": "PASS",
            "reviewer": reviewer,
        },
        # Pending Approval 2
        {
            "session_number": "TS-202611-003",
            "instrument": instruments[4],
            "test_date": today - datetime.timedelta(days=4),
            "status": SessionStatus.PENDING_REVIEW,
            "result": "PASS",
            "reviewer": reviewer,
        },
        # Approved 1 (last month)
        {
            "session_number": "TS-202610-015",
            "instrument": instruments[2],
            "test_date": today - datetime.timedelta(days=35),
            "status": SessionStatus.APPROVED,
            "result": "PASS",
            "reviewer": reviewer,
            "is_locked": True,
        },
        # Approved 2 (2 months ago)
        {
            "session_number": "TS-202609-008",
            "instrument": instruments[3],
            "test_date": today - datetime.timedelta(days=68),
            "status": SessionStatus.APPROVED,
            "result": "PASS",
            "reviewer": reviewer,
            "is_locked": True,
        },
        # Rejected (required adjustments)
        {
            "session_number": "TS-202610-022",
            "instrument": instruments[0],
            "test_date": today - datetime.timedelta(days=18),
            "status": SessionStatus.REJECTED,
            "result": "FAIL",
            "reviewer": reviewer,
            "rejection_reason": "Repeatability error at 10 kg exceeds MPE (Clause 3.6.1). Zero tracking recalibration required.",
        },
        # Approved 3 (3 months ago)
        {
            "session_number": "TS-202608-012",
            "instrument": instruments[2],
            "test_date": today - datetime.timedelta(days=95),
            "status": SessionStatus.APPROVED,
            "result": "PASS",
            "reviewer": reviewer,
            "is_locked": True,
        },
        # Draft (recently created)
        {
            "session_number": "TS-202611-004",
            "instrument": instruments[3],
            "test_date": today,
            "status": SessionStatus.DRAFT,
            "result": "PENDING",
            "reviewer": None,
        },
    ]

    for s in sessions_data:
        session, created = TestSession.objects.get_or_create(
            session_number=s["session_number"],
            defaults={
                "organization": org,
                "instrument": s["instrument"],
                "test_date": s["test_date"],
                "technician": tech,
                "reviewer": s.get("reviewer"),
                "status": s["status"],
                "overall_result": s["result"],
                "is_locked": s.get("is_locked", False),
                "temperature_start": Decimal("20.1"),
                "temperature_end": Decimal("20.4"),
                "humidity_start": Decimal("50.0"),
                "humidity_end": Decimal("52.0"),
                "test_location": "Metrology Bay 1",
                "reference_standards": "Class F1 Weight Set STD-2026",
                "rejection_reason": s.get("rejection_reason", ""),
                "created_by": tech,
            },
        )
        if not created:
            session.organization = org
            session.instrument = s["instrument"]
            session.technician = tech
            session.status = s["status"]
            session.overall_result = s["result"]
            session.is_locked = s.get("is_locked", False)
            session.save()

    print("✅ Comprehensive demo data generated!")
    print(f"Total Instruments: {Instrument.objects.filter(organization=org).count()}")
    print(f"Total Test Sessions: {TestSession.objects.filter(organization=org).count()}")


if __name__ == "__main__":
    run()
