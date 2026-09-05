from datetime import date
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class InvoiceStatus(str, Enum):
    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    VALIDATING = "validating"
    FLAGGED = "flagged"
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING_REVIEW = "pending_review"


class ApprovalLevel(str, Enum):
    AUTO = "auto"
    MANAGER = "manager"
    DIRECTOR = "director"
    CFO = "cfo"


class LineItem(BaseModel):
    description: str = Field(description="Description of the item or service")
    quantity: float = Field(default=1.0, description="Quantity or units")
    unit_price: float = Field(default=0.0, description="Price per unit")
    total: float = Field(default=0.0, description="Total amount for this line item")


class ExtractedInvoice(BaseModel):
    vendor_name: str = Field(description="Name of the vendor/supplier")
    vendor_id: Optional[str] = Field(default=None, description="Vendor tax or registration ID if present")
    invoice_number: str = Field(description="Unique invoice/bill identifier")
    invoice_date: date = Field(description="Date invoice was issued (YYYY-MM-DD)")
    due_date: Optional[date] = Field(default=None, description="Payment due date (YYYY-MM-DD)")
    currency: str = Field(default="INR", description="Currency code (e.g. INR, USD, EUR)")
    subtotal: float = Field(description="Sum of all line items before tax")
    tax_amount: float = Field(default=0.0, description="Total tax amount")
    total_amount: float = Field(description="Final invoice total including taxes")
    line_items: List[LineItem] = Field(default_factory=list, description="List of invoiced items")
    payment_terms: Optional[str] = Field(default=None, description="Terms of payment (e.g., Net 30)")
    confidence_score: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="LLM confidence score between 0.0 and 1.0"
    )

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, v: str) -> str:
        if not v:
            return "INR"
        cleaned = v.strip().upper()
        # Common currency symbols normalization
        symbols = {"₹": "INR", "$": "USD", "€": "EUR", "£": "GBP"}
        return symbols.get(cleaned, cleaned)
