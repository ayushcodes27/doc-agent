"""
Seed DocAgent Database with Real US Government Procurement Data
==============================================================
Reads records from data/real_procurement_data.json and persists them
into the database (invoices, invoice_line_items, invoice_audit_trail).

This provides a real-world statistical baseline for:
- Historical vendor spend distributions
- Statistical anomaly detection (Z-scores vs authentic vendor history)
- Approved vendor verification against real federal contractors
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from db.session import init_db, get_db_context
from db.models import InvoiceRecord, LineItemRecord, AuditTrailRecord
from sqlalchemy import select, func

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_db")

DATA_PATH = os.path.join(PROJECT_ROOT, "data", "real_procurement_data.json")


def seed_database(json_path: str = DATA_PATH):
    if not os.path.exists(json_path):
        logger.error(f"Procurement data file not found at: {json_path}")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    logger.info(f"Loaded {len(records)} records from {json_path}")

    # Ensure schema exists
    init_db()

    inserted_count = 0
    skipped_count = 0
    unique_vendors = set()

    with get_db_context() as db:
        for idx, rec in enumerate(records, 1):
            award_id = rec.get("award_id", f"award-{idx}")
            thread_id = f"procurement-{award_id}"

            # Check for existing record (idempotent)
            existing = db.scalar(
                select(InvoiceRecord.id).where(InvoiceRecord.thread_id == thread_id)
            )
            if existing:
                skipped_count += 1
                continue

            vendor_name = rec.get("vendor_name", "UNKNOWN VENDOR")
            amount = float(rec.get("award_amount", 0.0) or 0.0)
            contract_date = rec.get("contract_date", "2024-01-01")
            description = rec.get("item_description", "Federal Contract Deliverable")
            agency = rec.get("awarding_agency", "U.S. Federal Government")
            category = rec.get("category", "Procurement")
            award_type = rec.get("award_type", "CONTRACT")
            currency = rec.get("currency", "USD")

            unique_vendors.add(vendor_name)

            invoice = InvoiceRecord(
                thread_id=thread_id,
                filename=f"contract_{award_id}.pdf",
                vendor_name=vendor_name,
                vendor_id=f"USA-{rec.get('naics_code') or 'FED'}",
                invoice_number=award_id,
                invoice_date=contract_date,
                due_date=contract_date,
                currency=currency,
                subtotal=amount,
                tax_amount=0.0,
                total_amount=amount,
                payment_terms="Net 30 (Federal Acquisition)",
                confidence_score=1.0,
                is_duplicate=False,
                fingerprint=None,
                risk_score=0.05,
                decision="auto_approve",
                approval_level="auto",
                decision_reasoning=f"Verified federal contract award via {agency} ({category})",
                status="completed",
                reviewed_by="USASpending Ingestion",
                review_notes=f"Award Type: {award_type} | Category: {category}",
            )

            # Add Itemized Line Item
            invoice.line_items.append(
                LineItemRecord(
                    description=description[:490],
                    quantity=1.0,
                    unit_price=amount,
                    total=amount,
                )
            )

            # Add Immutable Audit Log
            invoice.audit_trail.append(
                AuditTrailRecord(
                    step="procurement_seeding",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    detail=f"Imported contract award '{award_id}' from USASpending.gov ({agency}).",
                )
            )

            db.add(invoice)
            inserted_count += 1

            if inserted_count % 100 == 0:
                db.flush()
                logger.info(f"Progress: {inserted_count} new records staged...")

        db.commit()

    # Query aggregate stats from DB
    with get_db_context() as db:
        total_in_db = db.scalar(select(func.count(InvoiceRecord.id))) or 0
        total_vendors = db.scalar(select(func.count(func.distinct(InvoiceRecord.vendor_name)))) or 0
        total_volume = db.scalar(select(func.sum(InvoiceRecord.total_amount))) or 0.0

    print("\n" + "=" * 65)
    print("  DATABASE SEEDING COMPLETE")
    print("=" * 65)
    print(f"  New Records Inserted : {inserted_count}")
    print(f"  Existing (Skipped)   : {skipped_count}")
    print(f"  Total Invoices in DB : {total_in_db}")
    print(f"  Distinct Vendors     : {total_vendors}")
    print(f"  Total Spend Volume   : ${total_volume:,.2f}")
    print("=" * 65)


if __name__ == "__main__":
    seed_database()
