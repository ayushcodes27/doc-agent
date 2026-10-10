"""
Download Real-World Enterprise Sample Invoices
==============================================
Downloads a curated collection of 16 real-world enterprise invoice PDFs
from recognized open-source benchmark repositories (including AWS, Azure,
Flipkart, QualityHosting, Coolblue, OYO, and Microsoft samples).

Saves PDFs into `data/real_invoices/` and generates an index `catalog.json`.
"""

import os
import sys
import json
import urllib.request
from datetime import datetime

# Optional PyMuPDF for inspection
try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "real_invoices")

INVOICE_SOURCES = [
    {
        "id": "INV-001",
        "filename": "amazon_web_services.pdf",
        "vendor": "Amazon Web Services",
        "category": "Cloud & Infrastructure",
        "description": "Authentic AWS Cloud monthly billing invoice with tax breakdowns.",
        "url": "https://raw.githubusercontent.com/invoice-x/invoice2data/master/tests/compare/AmazonWebServices.pdf",
    },
    {
        "id": "INV-002",
        "filename": "azure_interior_goods.pdf",
        "vendor": "Azure Interior / Acme",
        "category": "Supplies & Materials",
        "description": "Itemized commercial invoice with unit pricing, taxes, and item numbers.",
        "url": "https://raw.githubusercontent.com/invoice-x/invoice2data/master/tests/compare/AzureInterior.pdf",
    },
    {
        "id": "INV-003",
        "filename": "flipkart_b2b_retail.pdf",
        "vendor": "WS Retail (Flipkart)",
        "category": "E-Commerce / B2B Supply",
        "description": "Indian tax invoice format with GSTIN, authorized signatory, and item lines.",
        "url": "https://raw.githubusercontent.com/invoice-x/invoice2data/master/tests/compare/FlipkartInvoice.pdf",
    },
    {
        "id": "INV-004",
        "filename": "netpresse_it_consulting.pdf",
        "vendor": "Alexinux / Netpresse",
        "category": "IT & Consulting",
        "description": "Professional services invoice with invoice number, date, and client ID.",
        "url": "https://raw.githubusercontent.com/invoice-x/invoice2data/master/tests/compare/NetpresseInvoice.pdf",
    },
    {
        "id": "INV-005",
        "filename": "quality_hosting_servers.pdf",
        "vendor": "QualityHosting AG",
        "category": "Hosting & Data Center",
        "description": "Multi-page hosting invoice with server IDs, line items, and international VAT.",
        "url": "https://raw.githubusercontent.com/invoice-x/invoice2data/master/tests/compare/QualityHosting.pdf",
    },
    {
        "id": "INV-006",
        "filename": "sammy_maystone_supplies.pdf",
        "vendor": "Sammy Maystone",
        "category": "Office & Industrial Supplies",
        "description": "Structured multi-item supply invoice with bill-to and ship-to addresses.",
        "url": "https://raw.githubusercontent.com/invoice-x/invoice2data/master/tests/compare/SammyMaystoneLinesTest.pdf",
    },
    {
        "id": "INV-007",
        "filename": "coolblue_hardware_tablet.pdf",
        "vendor": "Coolblue B.V.",
        "category": "Hardware & Devices",
        "description": "European electronics vendor commercial tax invoice.",
        "url": "https://raw.githubusercontent.com/invoice-x/invoice2data/master/tests/compare/coolblue1.pdf",
    },
    {
        "id": "INV-008",
        "filename": "coolblue_hardware_laptop.pdf",
        "vendor": "Coolblue B.V.",
        "category": "Hardware & Devices",
        "description": "Laptop hardware equipment purchase invoice with Dutch KvK registration.",
        "url": "https://raw.githubusercontent.com/invoice-x/invoice2data/master/tests/compare/coolblue2.pdf",
    },
    {
        "id": "INV-009",
        "filename": "free_telecom_broadband.pdf",
        "vendor": "Free Telecom",
        "category": "Telecom & Connectivity",
        "description": "Multi-page broadband and fiber subscription invoice with recurring monthly fees.",
        "url": "https://raw.githubusercontent.com/invoice-x/invoice2data/master/tests/compare/free_fiber.pdf",
    },
    {
        "id": "INV-010",
        "filename": "oyo_corporate_stay.pdf",
        "vendor": "OYO Rooms",
        "category": "Travel & Corporate Stays",
        "description": "Corporate travel and accommodation tax payment receipt with GST details.",
        "url": "https://raw.githubusercontent.com/invoice-x/invoice2data/master/tests/compare/oyo.pdf",
    },
    {
        "id": "INV-011",
        "filename": "bol_logistics_deliveries.pdf",
        "vendor": "Bol Logistics / Camelot",
        "category": "Logistics & Shipping",
        "description": "Freight and logistics delivery invoice with reference numbers.",
        "url": "https://raw.githubusercontent.com/invoice-x/invoice2data/master/tests/files/camelot-bol100649863.pdf",
    },
    {
        "id": "INV-012",
        "filename": "circle_business_services.pdf",
        "vendor": "Circle B.V.",
        "category": "Business Services",
        "description": "Enterprise consulting and management service invoice.",
        "url": "https://raw.githubusercontent.com/invoice-x/invoice2data/master/tests/files/camelot-example.pdf",
    },
    {
        "id": "INV-013",
        "filename": "contoso_consulting_multipage.pdf",
        "vendor": "Contoso Ltd / Sharp Consulting",
        "category": "Enterprise Consulting",
        "description": "3-page Azure OpenAI benchmark invoice with multi-page line items and delivery schedule.",
        "url": "https://raw.githubusercontent.com/Azure-Samples/azure-openai-gpt-4-vision-pdf-extraction-sample/main/Invoice_1.pdf",
    },
    {
        "id": "INV-014",
        "filename": "microsoft_contoso_enterprise.pdf",
        "vendor": "Contoso Ltd / Microsoft Corp",
        "category": "Software & Enterprise",
        "description": "Official Microsoft Document Intelligence benchmark enterprise invoice layout.",
        "url": "https://raw.githubusercontent.com/ssukhpinder/AzureOpenAI/main/samples/Azure.OpenAI.DocumentIntelligence/sample-document/sample-invoice.pdf",
    },
    {
        "id": "INV-015",
        "filename": "excid3_b2b_service.pdf",
        "vendor": "Example B2B Services",
        "category": "Professional Services",
        "description": "Clean standard format B2B service invoice with item breakdown.",
        "url": "https://raw.githubusercontent.com/excid3/receipts/main/examples/invoice.pdf",
    },
    {
        "id": "INV-016",
        "filename": "excid3_periodic_statement.pdf",
        "vendor": "Example Recurring Services",
        "category": "Recurring Billing / Statement",
        "description": "Periodic billing statement with date intervals and line summary.",
        "url": "https://raw.githubusercontent.com/excid3/receipts/main/examples/statement.pdf",
    },
]


def download_all_invoices():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    catalog = []
    print("=" * 65)
    print("  DocAgent -- Real Enterprise Sample Invoice Downloader")
    print("=" * 65)

    for item in INVOICE_SOURCES:
        filename = item["filename"]
        target_path = os.path.join(OUTPUT_DIR, filename)
        url = item["url"]

        print(f"\n[+] Fetching {item['id']}: {item['vendor']} ({item['category']})...")
        print(f"    Target: {filename}")

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                pdf_bytes = resp.read()

            with open(target_path, "wb") as f:
                f.write(pdf_bytes)

            size_kb = len(pdf_bytes) / 1024
            pages = 1
            sample_snippet = ""

            if fitz:
                try:
                    doc = fitz.open(target_path)
                    pages = len(doc)
                    sample_snippet = doc[0].get_text()[:150].replace("\n", " ").strip()
                except Exception:
                    pass

            catalog_entry = {
                "id": item["id"],
                "filename": filename,
                "file_path": target_path,
                "vendor": item["vendor"],
                "category": item["category"],
                "description": item["description"],
                "size_kb": round(size_kb, 1),
                "pages": pages,
                "text_preview": sample_snippet,
                "source_url": url,
            }
            catalog.append(catalog_entry)
            print(f"    -> Saved successfully! ({size_kb:.1f} KB, {pages} page(s))")

        except Exception as e:
            print(f"    [!] Error downloading {filename}: {e}")

    # Save catalog.json
    catalog_path = os.path.join(OUTPUT_DIR, "catalog.json")
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 65)
    print("  DOWNLOAD COMPLETED")
    print("=" * 65)
    print(f"  Successfully Downloaded : {len(catalog)} / {len(INVOICE_SOURCES)} invoices")
    print(f"  Target Directory        : {OUTPUT_DIR}")
    print(f"  Catalog Metadata File   : {catalog_path}")
    print("=" * 65)


if __name__ == "__main__":
    download_all_invoices()
