# 🧪 DocAgent Benchmark & Evaluation Report

**Execution Timestamp:** `2026-09-25 16:59:56 UTC`  
**Evaluation Mode:** `OFFLINE`  
**Test Invoices Evaluated:** `20`  

## 📊 Executive Summary

| Metric | Result | Target | Status |
| :--- | :--- | :--- | :--- |
| **Rule Compliance Accuracy** | `100.0%` | `≥ 95.0%` | ✅ PASSED |
| **Anomaly Detection F1 Score** | `1.00` | `≥ 0.90` | ✅ PASSED |
| **Decision Routing Accuracy** | `100.0%` | `≥ 95.0%` | ✅ PASSED |
| **Approval Level Routing** | `100.0%` | `≥ 95.0%` | ✅ PASSED |

---

## 📋 Per-Invoice Test Results

| ID | Vendor | Amount | Validations | Anomalies | Decision | Level | Overall |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `inv_01_clean_approved_inr` | Infosys Limited | 45,360.00 | ✅ 9/9 | ✅ Match | ✅ `auto_approve` | ✅ `auto` | ✅ PASS |
| `inv_02_clean_approved_usd` | Amazon Web Services | 2,484.00 | ✅ 9/9 | ✅ Match | ✅ `auto_approve` | ✅ `auto` | ✅ PASS |
| `inv_03_clean_small` | Logitech | 9,500.00 | ✅ 9/9 | ✅ Match | ✅ `auto_approve` | ✅ `auto` | ✅ PASS |
| `inv_04_clean_services` | Deloitte Touche Tohm | 75,040.00 | ✅ 9/9 | ✅ Match | ✅ `auto_approve` | ✅ `auto` | ✅ PASS |
| `inv_05_unapproved_vendor` | QuickFix IT Solution | 22,000.00 | ✅ 9/9 | ✅ Match | ✅ `flag_review` | ✅ `manager` | ✅ PASS |
| `inv_06_over_budget` | Tata Consultancy Ser | 649,000.00 | ✅ 9/9 | ✅ Match | ✅ `flag_review` | ✅ `director` | ✅ PASS |
| `inv_07_future_date` | Dell Technologies | 259,600.00 | ✅ 9/9 | ✅ Match | ✅ `flag_review` | ✅ `director` | ✅ PASS |
| `inv_08_math_mismatch` | HP Inc | 20,350.00 | ✅ 9/9 | ✅ Match | ✅ `auto_approve` | ✅ `auto` | ✅ PASS |
| `inv_09_missing_fields` | Google Cloud Platfor | 34,100.00 | ✅ 9/9 | ✅ Match | ✅ `auto_approve` | ✅ `auto` | ✅ PASS |
| `inv_10_round_number` | Wipro Technologies | 50,000.00 | ✅ 9/9 | ✅ Match | ✅ `flag_review` | ✅ `manager` | ✅ PASS |
| `inv_11_high_tax` | Tech Mahindra | 28,000.00 | ✅ 9/9 | ✅ Match | ✅ `flag_review` | ✅ `manager` | ✅ PASS |
| `inv_12_threshold_avoidance` | Atlassian Pty Ltd | 99,500.00 | ✅ 9/9 | ✅ Match | ✅ `flag_review` | ✅ `manager` | ✅ PASS |
| `inv_13_threshold_avoidance_director` | Salesforce Inc | 198,000.00 | ✅ 9/9 | ✅ Match | ✅ `flag_review` | ✅ `manager` | ✅ PASS |
| `inv_14_multiple_anomalies` | Microsoft Azure | 100,000.00 | ✅ 9/9 | ✅ Match | ✅ `flag_review` | ✅ `manager` | ✅ PASS |
| `inv_15_manager_review` | Ernst & Young LLP | 125,000.00 | ✅ 9/9 | ✅ Match | ✅ `flag_review` | ✅ `manager` | ✅ PASS |
| `inv_16_director_review` | KPMG Advisory Servic | 295,000.00 | ✅ 9/9 | ✅ Match | ✅ `flag_review` | ✅ `director` | ✅ PASS |
| `inv_17_reject_high_risk` | Unknown Corp Interna | 605,000.00 | ✅ 9/9 | ✅ Match | ✅ `reject` | ✅ `auto` | ✅ PASS |
| `inv_18_date_formats` | Blue Dart Express Lt | 21,450.00 | ✅ 9/9 | ✅ Match | ✅ `auto_approve` | ✅ `auto` | ✅ PASS |
| `inv_19_multi_currency_eur` | Sodexo India Service | 3,190.00 | ✅ 9/9 | ✅ Match | ✅ `auto_approve` | ✅ `auto` | ✅ PASS |
| `inv_20_duplicate_pair` | Infosys Limited | 45,360.00 | ✅ 9/9 | ✅ Match | ✅ `reject` | ✅ `auto` | ✅ PASS |

---

## 🛡️ Business Rules Validation Coverage

| Rule Name | Severity | Total Checked | Passed Matches | Failed Matches | Rule Accuracy |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `max_amount` | `error` | 20 | 18 | 2 | `100.0%` |
| `approved_vendor` | `error` | 20 | 18 | 2 | `100.0%` |
| `date_validity` | `error` | 20 | 18 | 2 | `100.0%` |
| `line_item_math` | `warning` | 20 | 19 | 1 | `100.0%` |
| `total_math` | `warning` | 20 | 20 | 0 | `100.0%` |
| `visual_text_consistency` | `error` | 20 | 20 | 0 | `100.0%` |
| `vendor_id_present` | `warning` | 20 | 18 | 2 | `100.0%` |
| `payment_terms_check` | `info` | 20 | 19 | 1 | `100.0%` |
| `currency_consistency` | `warning` | 20 | 20 | 0 | `100.0%` |

---

## 🔍 Anomaly Detection Performance

- **Total Expected Anomaly Triggers:** `6`

- **Total Detected Anomaly Triggers:** `6`

- **True Positives (TP):** `6`  

- **False Positives (FP):** `0`  

- **False Negatives (FN):** `0`  

- **Precision:** `1.00`  

- **Recall:** `1.00`  

- **F1-Score:** `1.00`  
