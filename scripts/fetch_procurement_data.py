"""
Fetch real government procurement data from USASpending.gov API.
Pulls 500 real contract award records with vendor, amount, date, and description fields.
Saves to both CSV and JSON for seeding the DocAgent vendor database.

API Docs: https://api.usaspending.gov/
No API key required -- fully public.
"""

import json
import csv
import os
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

API_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
CSV_OUTPUT = os.path.join(OUTPUT_DIR, "real_procurement_data.csv")
JSON_OUTPUT = os.path.join(OUTPUT_DIR, "real_procurement_data.json")

# Pull across multiple NAICS categories for vendor diversity
AWARD_CATEGORIES = [
    {"name": "IT & Software", "naics": ["541511", "541512", "541519"]},
    {"name": "Professional Services", "naics": ["541611", "541612", "541613", "541614", "541618"]},
    {"name": "Office Supplies & Equipment", "naics": ["423420", "423210", "339940"]},
    {"name": "Construction & Facilities", "naics": ["236220", "238210", "561210"]},
    {"name": "Healthcare & Medical", "naics": ["621111", "339112", "325411"]},
    {"name": "Logistics & Transportation", "naics": ["484110", "492110", "493110"]},
]

TARGET_ROWS = 500
ROWS_PER_PAGE = 100  # API max per request


def fetch_page(page: int, naics_codes: list, fiscal_year: str = "2024") -> dict:
    """Fetch a single page of award data from USASpending API."""
    payload = {
        "filters": {
            "time_period": [
                {"start_date": f"{fiscal_year}-01-01", "end_date": f"{fiscal_year}-12-31"}
            ],
            "award_type_codes": ["A", "B", "C", "D"],
            "naics_codes": naics_codes,
        },
        "fields": [
            "Award ID",
            "Recipient Name",
            "Award Amount",
            "Total Outlays",
            "Description",
            "Start Date",
            "End Date",
            "Awarding Agency",
            "Awarding Sub Agency",
            "Contract Award Type",
            "recipient_id",
            "NAICS Code",
        ],
        "page": page,
        "limit": ROWS_PER_PAGE,
        "sort": "Award Amount",
        "order": "desc",
        "subawards": False,
    }

    body = json.dumps(payload).encode("utf-8")
    req = Request(API_URL, data=body, headers={"Content-Type": "application/json"})

    try:
        with urlopen(req, timeout=45) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8")[:500]
        except Exception:
            pass
        print(f"  [!] HTTP {e.code}: {err_body}")
        return {}
    except URLError as e:
        print(f"  [!] Network error: {e.reason}")
        return {}


def clean_record(raw: dict, category_name: str):
    """Transform a raw API result into a clean, flat record."""
    vendor = (raw.get("Recipient Name") or "").strip()
    amount = raw.get("Award Amount")
    description = (raw.get("Description") or "").strip()
    start_date = (raw.get("Start Date") or "").strip()
    agency = (raw.get("Awarding Agency") or "").strip()
    sub_agency = (raw.get("Awarding Sub Agency") or "").strip()
    award_id = (raw.get("Award ID") or "").strip()
    award_type = (raw.get("Contract Award Type") or "").strip()
    naics = (raw.get("NAICS Code") or "").strip()

    if not vendor or amount is None or not start_date:
        return None

    try:
        amount_float = float(amount)
    except (ValueError, TypeError):
        return None

    if amount_float < 1000.0:
        return None

    return {
        "vendor_name": vendor,
        "award_amount": round(amount_float, 2),
        "contract_date": start_date,
        "item_description": description[:300] if description else "N/A",
        "awarding_agency": agency,
        "sub_agency": sub_agency,
        "award_id": award_id,
        "award_type": award_type,
        "naics_code": naics,
        "category": category_name,
        "currency": "USD",
    }


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    all_records = []
    seen_award_ids = set()

    print("=" * 60)
    print("  DocAgent -- Real Procurement Data Fetcher")
    print("  Source: USASpending.gov (U.S. Federal Contracts)")
    print("=" * 60)

    for cat in AWARD_CATEGORIES:
        if len(all_records) >= TARGET_ROWS:
            break

        cat_name = cat["name"]
        naics_codes = cat["naics"]
        print(f"\n[+] Fetching: {cat_name} (NAICS: {', '.join(naics_codes)})")

        pages_to_fetch = 2
        for page in range(1, pages_to_fetch + 1):
            if len(all_records) >= TARGET_ROWS:
                break

            print(f"  -> Page {page}...", end=" ", flush=True)
            data = fetch_page(page, naics_codes)

            results = data.get("results", [])
            if not results:
                print("no results.")
                break

            added = 0
            for raw in results:
                record = clean_record(raw, cat_name)
                if record and record["award_id"] not in seen_award_ids:
                    seen_award_ids.add(record["award_id"])
                    all_records.append(record)
                    added += 1

            print(f"{added} records added (total: {len(all_records)})")
            time.sleep(0.5)

    if not all_records:
        print("\n[X] No records fetched. Check your internet connection.")
        sys.exit(1)

    all_records = all_records[:TARGET_ROWS]

    # Save JSON
    with open(JSON_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_records, f, indent=2, ensure_ascii=False)

    # Save CSV
    fieldnames = [
        "vendor_name", "award_amount", "contract_date", "item_description",
        "awarding_agency", "sub_agency", "award_id", "award_type",
        "naics_code", "category", "currency",
    ]
    with open(CSV_OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_records)

    # Summary
    amounts = [r["award_amount"] for r in all_records]
    unique_vendors = len(set(r["vendor_name"] for r in all_records))
    categories_hit = len(set(r["category"] for r in all_records))

    print("\n" + "=" * 60)
    print("  DOWNLOAD COMPLETE")
    print("=" * 60)
    print(f"  Total Records:    {len(all_records)}")
    print(f"  Unique Vendors:   {unique_vendors}")
    print(f"  Categories:       {categories_hit}")
    print(f"  Amount Range:     ${min(amounts):,.2f} -- ${max(amounts):,.2f}")
    print(f"  Median Amount:    ${sorted(amounts)[len(amounts)//2]:,.2f}")
    print(f"  CSV saved to:     {os.path.abspath(CSV_OUTPUT)}")
    print(f"  JSON saved to:    {os.path.abspath(JSON_OUTPUT)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
