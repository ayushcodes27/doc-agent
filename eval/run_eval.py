#!/usr/bin/env python3
"""
DocAgent Evaluation & Benchmarking Runner
=========================================
Runs comprehensive evaluation tests across:
  1. LLM Extraction Accuracy (in --mode live or all)
  2. Compliance & Validation Rules (9 business rules)
  3. Anomaly & Fraud Detection Engine (5 heuristic/statistical triggers)
  4. Deduplication Engine (SHA-256 fingerprinting)
  5. Risk Scoring & Decision Routing (Thresholds & Approval Levels)

Usage:
  python eval/run_eval.py --mode offline
  python eval/run_eval.py --mode live
  python eval/run_eval.py --mode all
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Safe UTF-8 encoding for Windows terminals
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

from api.models import ExtractedInvoice, LineItem
from tools.validator import validate_invoice, DEFAULT_COMPLIANCE_RULES
from tools.anomaly_detector import detect_anomalies
from tools.duplicate_checker import check_duplicate, _in_memory_cache


# Terminal ANSI Colors
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def print_banner(title: str):
    width = 75
    print(f"\n{Colors.CYAN}{'=' * width}{Colors.RESET}")
    print(f"{Colors.BOLD}{title.center(width)}{Colors.RESET}")
    print(f"{Colors.CYAN}{'=' * width}{Colors.RESET}\n")


def calculate_risk_and_decision(
    extracted_data: Dict[str, Any],
    validation_results: List[Dict[str, Any]],
    anomalies: List[Dict[str, Any]],
    is_duplicate: bool,
    confidence: float = 1.0,
) -> Tuple[float, str, str, str]:
    """Compute risk score and routing decision matching agent/nodes.py logic."""
    score = 0.0

    if is_duplicate:
        score = 1.0
    else:
        # Failed validations impact
        for val in validation_results:
            if not val.get("passed", True):
                sev = val.get("severity", "error")
                if sev == "error":
                    score += 0.25
                elif sev == "warning":
                    score += 0.10

        # Anomalies impact
        if anomalies:
            max_anomaly = max((float(a.get("score", 0.3)) for a in anomalies), default=0.0)
            score += max_anomaly

        # Extraction confidence penalty
        if confidence < 0.70:
            score += 0.30

    risk_score = min(max(round(score, 2), 0.0), 1.0)

    total_amount = float(extracted_data.get("total_amount", 0.0) or 0.0)
    visual_tampering = any(a.get("type") == "visual_text_mismatch" for a in anomalies)

    if not extracted_data:
        decision = "reject"
        level = "auto"
        reason = "Rejection: No data was extracted from the document."
    elif is_duplicate:
        decision = "reject"
        level = "auto"
        reason = "Duplicate invoice detected with matching vendor, invoice number, and total amount."
    elif visual_tampering:
        decision = "reject"
        level = "auto"
        reason = "Rejection: Critical document tampering alert — embedded scanned copy amount conflicts with digital line items."
    elif risk_score >= 0.70:
        decision = "reject"
        level = "auto"
        reason = f"High risk score ({risk_score:.2f}) exceeds rejection threshold (0.70)."
    elif risk_score >= 0.25:
        level = "director" if (total_amount > 200000.0 or risk_score >= 0.60) else "manager"
        decision = "flag_review"
        reason = f"Moderate risk score ({risk_score:.2f}) requires human review by {level.title()}."
    elif total_amount > 200000.0:
        decision = "flag_review"
        level = "director"
        reason = f"Invoice total amount ({total_amount:,.2f}) exceeds director review threshold (200,000)."
    elif total_amount > 100000.0:
        decision = "flag_review"
        level = "manager"
        reason = f"Invoice total amount ({total_amount:,.2f}) exceeds manager auto-approve threshold (100,000)."
    else:
        decision = "auto_approve"
        level = "auto"
        reason = f"Low risk score ({risk_score:.2f}) and total amount within limits."

    return risk_score, decision, level, reason


def evaluate_field_match(actual: Any, expected: Any, field_name: str) -> Tuple[bool, str]:
    """Compare extracted field value vs ground truth."""
    if expected is None:
        return True, "N/A"
    
    if isinstance(expected, (int, float)):
        try:
            act_num = float(actual) if actual is not None else 0.0
            exp_num = float(expected)
            diff = abs(act_num - exp_num)
            tolerance = max(exp_num * 0.005, 0.05)
            matched = diff <= tolerance
            return matched, f"Act: {act_num:.2f} | Exp: {exp_num:.2f} (diff: {diff:.2f})"
        except (ValueError, TypeError):
            return False, f"Act: {actual} | Exp: {expected}"
            
    if isinstance(expected, str):
        act_str = str(actual or "").strip().lower()
        exp_str = str(expected or "").strip().lower()
        matched = act_str == exp_str or (exp_str in act_str if len(exp_str) > 4 else False)
        return matched, f"Act: '{actual}' | Exp: '{expected}'"

    return actual == expected, f"Act: {actual} | Exp: {expected}"


def run_single_offline_eval(
    invoice_id: str,
    ground_truth: Dict[str, Any],
) -> Dict[str, Any]:
    """Run offline evaluation for one invoice against ground truth expectations."""
    # 1. Validation Engine Evaluation
    val_results = validate_invoice(ground_truth)
    actual_validations = {r.rule_name: "pass" if r.passed else "fail" for r in val_results}
    expected_validations = ground_truth.get("expected_validations", {})

    validation_matches = {}
    all_val_passed = True
    for rule_name, exp_status in expected_validations.items():
        act_status = actual_validations.get(rule_name, "unknown")
        match = (act_status == exp_status)
        validation_matches[rule_name] = {
            "expected": exp_status,
            "actual": act_status,
            "matched": match,
        }
        if not match:
            all_val_passed = False

    # 2. Anomaly Engine Evaluation
    detected_anomalies_list = detect_anomalies(ground_truth)
    detected_anomaly_types = sorted(list(set(a.get("type") for a in detected_anomalies_list)))
    expected_anomaly_types = sorted(ground_truth.get("expected_anomalies", []))
    anomalies_matched = (detected_anomaly_types == expected_anomaly_types)

    # 3. Deduplication Check
    dup_res = check_duplicate(ground_truth, record_if_new=True)
    is_duplicate = bool(dup_res.get("is_duplicate", False))

    # 4. Risk & Decision Routing
    confidence = float(ground_truth.get("confidence_score", 1.0))
    risk_score, decision, approval_level, reasoning = calculate_risk_and_decision(
        extracted_data=ground_truth,
        validation_results=[r.to_dict() for r in val_results],
        anomalies=detected_anomalies_list,
        is_duplicate=is_duplicate,
        confidence=confidence,
    )

    expected_decision = ground_truth.get("expected_decision", "auto_approve")
    expected_level = ground_truth.get("expected_approval_level", "auto")

    decision_matched = (decision == expected_decision)
    level_matched = (approval_level == expected_level)

    overall_pass = all_val_passed and anomalies_matched and decision_matched and level_matched

    return {
        "invoice_id": invoice_id,
        "vendor_name": ground_truth.get("vendor_name"),
        "total_amount": ground_truth.get("total_amount"),
        "category": ground_truth.get("test_category", ""),
        "overall_pass": overall_pass,
        "validations": {
            "all_matched": all_val_passed,
            "details": validation_matches,
        },
        "anomalies": {
            "matched": anomalies_matched,
            "expected": expected_anomaly_types,
            "actual": detected_anomaly_types,
            "raw": detected_anomalies_list,
        },
        "dedup": {
            "is_duplicate": is_duplicate,
        },
        "decision": {
            "matched": decision_matched,
            "expected": expected_decision,
            "actual": decision,
            "level_matched": level_matched,
            "expected_level": expected_level,
            "actual_level": approval_level,
            "risk_score": risk_score,
            "reasoning": reasoning,
        },
    }


def run_single_live_eval(
    invoice_id: str,
    text_content: str,
    ground_truth: Dict[str, Any],
) -> Dict[str, Any]:
    """Run live extraction via LLM and evaluate extraction accuracy + downstream pipeline."""
    from tools.extractor import extract_invoice_data

    start_time = time.time()
    try:
        extracted: ExtractedInvoice = extract_invoice_data(document_text=text_content)
        extraction_time = time.time() - start_time
        extracted_dict = json.loads(extracted.model_dump_json())
        extraction_error = None
    except Exception as exc:
        extraction_time = time.time() - start_time
        extracted_dict = {}
        extraction_error = str(exc)

    # Field-level accuracy checks
    fields_to_check = [
        "vendor_name",
        "vendor_id",
        "invoice_number",
        "invoice_date",
        "currency",
        "subtotal",
        "tax_amount",
        "total_amount",
        "payment_terms",
    ]

    field_scores = {}
    correct_fields = 0
    total_fields = len(fields_to_check)

    for field in fields_to_check:
        act_val = extracted_dict.get(field)
        exp_val = ground_truth.get(field)
        matched, detail = evaluate_field_match(act_val, exp_val, field)
        field_scores[field] = {
            "matched": matched,
            "detail": detail,
            "actual": act_val,
            "expected": exp_val,
        }
        if matched:
            correct_fields += 1

    field_accuracy = (correct_fields / total_fields) if total_fields > 0 else 0.0

    # Line item comparison
    act_items = extracted_dict.get("line_items", [])
    exp_items = ground_truth.get("line_items", [])
    item_count_match = len(act_items) == len(exp_items)

    # Downstream offline checks with LLM extracted data
    if extracted_dict:
        val_results = validate_invoice(extracted_dict)
        detected_anomalies_list = detect_anomalies(extracted_dict)
        dup_res = check_duplicate(extracted_dict, record_if_new=True)
        is_duplicate = bool(dup_res.get("is_duplicate", False))
        confidence = float(extracted_dict.get("confidence_score", 0.95) or 0.95)

        risk_score, decision, approval_level, reasoning = calculate_risk_and_decision(
            extracted_data=extracted_dict,
            validation_results=[r.to_dict() for r in val_results],
            anomalies=detected_anomalies_list,
            is_duplicate=is_duplicate,
            confidence=confidence,
        )
    else:
        val_results = []
        detected_anomalies_list = []
        is_duplicate = False
        risk_score, decision, approval_level, reasoning = 1.0, "reject", "auto", "Extraction failed"

    expected_decision = ground_truth.get("expected_decision", "auto_approve")
    expected_level = ground_truth.get("expected_approval_level", "auto")

    return {
        "invoice_id": invoice_id,
        "extraction_time_s": round(extraction_time, 2),
        "extraction_error": extraction_error,
        "field_accuracy": field_accuracy,
        "field_scores": field_scores,
        "line_items": {
            "count_matched": item_count_match,
            "actual_count": len(act_items),
            "expected_count": len(exp_items),
        },
        "downstream": {
            "decision_matched": (decision == expected_decision),
            "expected_decision": expected_decision,
            "actual_decision": decision,
            "level_matched": (approval_level == expected_level),
            "expected_level": expected_level,
            "actual_level": approval_level,
            "risk_score": risk_score,
        }
    }


def generate_markdown_report(
    eval_results: List[Dict[str, Any]],
    mode: str,
    metrics: Dict[str, Any],
    output_path: Path,
):
    """Generate professional GitHub-ready Markdown evaluation report."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    md = []
    md.append("# 🧪 DocAgent Benchmark & Evaluation Report\n")
    md.append(f"**Execution Timestamp:** `{now_str}`  ")
    md.append(f"**Evaluation Mode:** `{mode.upper()}`  ")
    md.append(f"**Test Invoices Evaluated:** `{len(eval_results)}`  \n")

    # Executive Summary Badges & Cards
    md.append("## 📊 Executive Summary\n")
    md.append("| Metric | Result | Target | Status |")
    md.append("| :--- | :--- | :--- | :--- |")
    
    val_acc = metrics.get("validation_accuracy", 0.0)
    val_badge = "✅ PASSED" if val_acc >= 95.0 else "⚠️ REVIEW"
    md.append(f"| **Rule Compliance Accuracy** | `{val_acc:.1f}%` | `≥ 95.0%` | {val_badge} |")

    anom_f1 = metrics.get("anomaly_f1", 0.0)
    anom_badge = "✅ PASSED" if anom_f1 >= 0.90 else "⚠️ REVIEW"
    md.append(f"| **Anomaly Detection F1 Score** | `{anom_f1:.2f}` | `≥ 0.90` | {anom_badge} |")

    dec_acc = metrics.get("decision_accuracy", 0.0)
    dec_badge = "✅ PASSED" if dec_acc >= 95.0 else "⚠️ REVIEW"
    md.append(f"| **Decision Routing Accuracy** | `{dec_acc:.1f}%` | `≥ 95.0%` | {dec_badge} |")

    level_acc = metrics.get("approval_level_accuracy", 0.0)
    level_badge = "✅ PASSED" if level_acc >= 95.0 else "⚠️ REVIEW"
    md.append(f"| **Approval Level Routing** | `{level_acc:.1f}%` | `≥ 95.0%` | {level_badge} |")

    if mode in ["live", "all"]:
        ext_acc = metrics.get("extraction_accuracy", 0.0)
        ext_badge = "✅ PASSED" if ext_acc >= 90.0 else "⚠️ REVIEW"
        md.append(f"| **LLM Extraction Field Accuracy** | `{ext_acc:.1f}%` | `≥ 90.0%` | {ext_badge} |")

    md.append("\n---\n")

    # Detailed Per-Invoice Results Table
    md.append("## 📋 Per-Invoice Test Results\n")
    md.append("| ID | Vendor | Amount | Validations | Anomalies | Decision | Level | Overall |")
    md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")

    for r in eval_results:
        inv_id = r["invoice_id"]
        vendor = (r.get("vendor_name") or "N/A")[:20]
        amt = f"{r.get('total_amount', 0.0):,.2f}" if r.get("total_amount") else "N/A"
        
        val_status = "✅ 9/9" if r["validations"]["all_matched"] else "❌ MISMATCH"
        anom_status = "✅ Match" if r["anomalies"]["matched"] else "❌ Diff"
        dec_status = f"✅ `{r['decision']['actual']}`" if r["decision"]["matched"] else f"❌ `{r['decision']['actual']}` (exp `{r['decision']['expected']}`)"
        lvl_status = f"✅ `{r['decision']['actual_level']}`" if r["decision"]["level_matched"] else f"❌ `{r['decision']['actual_level']}`"
        overall = "✅ PASS" if r["overall_pass"] else "❌ FAIL"

        md.append(f"| `{inv_id}` | {vendor} | {amt} | {val_status} | {anom_status} | {dec_status} | {lvl_status} | {overall} |")

    md.append("\n---\n")

    # Rule Validation Breakdown
    md.append("## 🛡️ Business Rules Validation Coverage\n")
    md.append("| Rule Name | Severity | Total Checked | Passed Matches | Failed Matches | Rule Accuracy |")
    md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    rule_stats = metrics.get("rule_breakdown", {})
    for rule, stat in rule_stats.items():
        total = stat["total"]
        matched = stat["matched"]
        acc = (matched / total * 100) if total > 0 else 100.0
        md.append(f"| `{rule}` | `{stat['severity']}` | {total} | {stat['pass_count']} | {stat['fail_count']} | `{acc:.1f}%` |")

    md.append("\n---\n")

    # Anomaly Engine Breakdown
    md.append("## 🔍 Anomaly Detection Performance\n")
    md.append(f"- **Total Expected Anomaly Triggers:** `{metrics.get('anomalies_expected_total', 0)}`\n")
    md.append(f"- **Total Detected Anomaly Triggers:** `{metrics.get('anomalies_detected_total', 0)}`\n")
    md.append(f"- **True Positives (TP):** `{metrics.get('anomalies_tp', 0)}`  \n")
    md.append(f"- **False Positives (FP):** `{metrics.get('anomalies_fp', 0)}`  \n")
    md.append(f"- **False Negatives (FN):** `{metrics.get('anomalies_fn', 0)}`  \n")
    md.append(f"- **Precision:** `{metrics.get('anomaly_precision', 0.0):.2f}`  \n")
    md.append(f"- **Recall:** `{metrics.get('anomaly_recall', 0.0):.2f}`  \n")
    md.append(f"- **F1-Score:** `{metrics.get('anomaly_f1', 0.0):.2f}`  \n")

    # Output file write
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))


def run_evaluation_suite(
    eval_dir: Path,
    mode: str = "offline",
    output_md: Path = None,
    output_json: Path = None,
    verbose: bool = False,
):
    """Main evaluation orchestrator."""
    print_banner(f"DocAgent Benchmark Suite — Running in {mode.upper()} Mode")

    invoices_dir = eval_dir / "invoices"
    ground_truth_dir = eval_dir / "ground_truth"

    # Fallback to flat eval_dir if subdirectories don't exist
    if not ground_truth_dir.exists():
        ground_truth_dir = eval_dir
    if not invoices_dir.exists():
        invoices_dir = eval_dir

    json_files = sorted(list(ground_truth_dir.glob("*.json")))

    if not json_files:
        print(f"{Colors.RED}❌ Error: No ground truth JSON files found in {ground_truth_dir}{Colors.RESET}")
        sys.exit(1)

    print(f"📁 Located {len(json_files)} test invoices in `{eval_dir}`.")
    print(f"⚙️  Executing {mode.upper()} benchmarking...\n")

    # Clear duplicate cache before running evaluation suite
    _in_memory_cache.clear()

    eval_results = []
    live_results = []

    # Metrics collectors
    total_rule_evals = 0
    matched_rule_evals = 0
    rule_breakdown = {
        rule.get("name", "unknown"): {
            "total": 0,
            "matched": 0,
            "severity": rule.get("severity", "error"),
            "pass_count": 0,
            "fail_count": 0,
        }
        for rule in DEFAULT_COMPLIANCE_RULES
    }

    tp_anomalies = 0
    fp_anomalies = 0
    fn_anomalies = 0
    expected_anom_total = 0
    detected_anom_total = 0

    decision_matches = 0
    level_matches = 0

    for json_path in json_files:
        invoice_id = json_path.stem
        with open(json_path, "r", encoding="utf-8") as f:
            ground_truth = json.load(f)

        # 1. Run Offline Evaluation
        res = run_single_offline_eval(invoice_id, ground_truth)
        eval_results.append(res)

        # Update rule breakdown metrics
        for rule_name, v_data in res["validations"]["details"].items():
            if rule_name in rule_breakdown:
                rule_breakdown[rule_name]["total"] += 1
                if v_data["matched"]:
                    rule_breakdown[rule_name]["matched"] += 1
                if v_data["actual"] == "pass":
                    rule_breakdown[rule_name]["pass_count"] += 1
                else:
                    rule_breakdown[rule_name]["fail_count"] += 1
                total_rule_evals += 1
                if v_data["matched"]:
                    matched_rule_evals += 1

        # Update anomaly metrics
        exp_anoms = set(res["anomalies"]["expected"])
        act_anoms = set(res["anomalies"]["actual"])
        expected_anom_total += len(exp_anoms)
        detected_anom_total += len(act_anoms)
        tp = len(exp_anoms.intersection(act_anoms))
        fp = len(act_anoms - exp_anoms)
        fn = len(exp_anoms - act_anoms)
        tp_anomalies += tp
        fp_anomalies += fp
        fn_anomalies += fn

        # Update decision metrics
        if res["decision"]["matched"]:
            decision_matches += 1
        if res["decision"]["level_matched"]:
            level_matches += 1

        # 2. Run Live Evaluation if requested
        if mode in ["live", "all"]:
            txt_path = invoices_dir / f"{invoice_id}.txt"
            if txt_path.exists():
                with open(txt_path, "r", encoding="utf-8") as f:
                    txt_content = f.read()
                live_res = run_single_live_eval(invoice_id, txt_content, ground_truth)
                live_results.append(live_res)

        # Print inline progress
        status_icon = f"{Colors.GREEN}✔ PASS{Colors.RESET}" if res["overall_pass"] else f"{Colors.RED}✖ FAIL{Colors.RESET}"
        dec_info = f"Decision: {res['decision']['actual']} (risk: {res['decision']['risk_score']:.2f})"
        print(f"[{status_icon}] {invoice_id.ljust(35)} | {dec_info}")
        if verbose and not res["overall_pass"]:
            if not res["validations"]["all_matched"]:
                print(f"    {Colors.YELLOW}Validation mismatch: {res['validations']['details']}{Colors.RESET}")
            if not res["anomalies"]["matched"]:
                print(f"    {Colors.YELLOW}Anomaly mismatch — Exp: {res['anomalies']['expected']}, Act: {res['anomalies']['actual']}{Colors.RESET}")
            if not res["decision"]["matched"]:
                print(f"    {Colors.YELLOW}Decision mismatch — Exp: {res['decision']['expected']}, Act: {res['decision']['actual']}{Colors.RESET}")

    # Compute Aggregate Metrics
    n = len(eval_results)
    val_accuracy = (matched_rule_evals / total_rule_evals * 100) if total_rule_evals > 0 else 0.0
    dec_accuracy = (decision_matches / n * 100) if n > 0 else 0.0
    level_accuracy = (level_matches / n * 100) if n > 0 else 0.0

    precision = tp_anomalies / (tp_anomalies + fp_anomalies) if (tp_anomalies + fp_anomalies) > 0 else 1.0
    recall = tp_anomalies / (tp_anomalies + fn_anomalies) if (tp_anomalies + fn_anomalies) > 0 else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 1.0

    live_field_accuracy = 0.0
    if live_results:
        live_field_accuracy = (sum(r["field_accuracy"] for r in live_results) / len(live_results)) * 100

    metrics = {
        "total_invoices": n,
        "validation_accuracy": round(val_accuracy, 2),
        "decision_accuracy": round(dec_accuracy, 2),
        "approval_level_accuracy": round(level_accuracy, 2),
        "rule_breakdown": rule_breakdown,
        "anomalies_expected_total": expected_anom_total,
        "anomalies_detected_total": detected_anom_total,
        "anomalies_tp": tp_anomalies,
        "anomalies_fp": fp_anomalies,
        "anomalies_fn": fn_anomalies,
        "anomaly_precision": round(precision, 4),
        "anomaly_recall": round(recall, 4),
        "anomaly_f1": round(f1, 4),
        "extraction_accuracy": round(live_field_accuracy, 2),
    }

    # Print Summary Card to Terminal
    print_banner("Benchmark Results & Summary Metrics")
    print(f"  • Total Test Invoices Evaluated : {Colors.BOLD}{n}{Colors.RESET}")
    print(f"  • Business Validation Accuracy  : {Colors.GREEN if val_accuracy >= 95 else Colors.YELLOW}{val_accuracy:.1f}%{Colors.RESET} ({matched_rule_evals}/{total_rule_evals} rule checks)")
    print(f"  • Anomaly Detection Precision   : {Colors.CYAN}{precision:.2f}{Colors.RESET}")
    print(f"  • Anomaly Detection Recall      : {Colors.CYAN}{recall:.2f}{Colors.RESET}")
    print(f"  • Anomaly Detection F1-Score    : {Colors.GREEN if f1 >= 0.9 else Colors.YELLOW}{f1:.2f}{Colors.RESET}")
    print(f"  • Decision Routing Accuracy     : {Colors.GREEN if dec_accuracy >= 95 else Colors.YELLOW}{dec_accuracy:.1f}%{Colors.RESET} ({decision_matches}/{n})")
    print(f"  • Approval Level Accuracy       : {Colors.GREEN if level_accuracy >= 95 else Colors.YELLOW}{level_accuracy:.1f}%{Colors.RESET} ({level_matches}/{n})")

    if mode in ["live", "all"] and live_results:
        print(f"  • LLM Field Extraction Accuracy : {Colors.GREEN if live_field_accuracy >= 90 else Colors.YELLOW}{live_field_accuracy:.1f}%{Colors.RESET}")

    # Generate Markdown Report
    if output_md:
        generate_markdown_report(eval_results, mode, metrics, output_md)
        print(f"\n📄 Saved Markdown Evaluation Report to: {Colors.CYAN}{output_md}{Colors.RESET}")

    # Generate JSON Report
    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        export_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "metrics": metrics,
            "eval_results": eval_results,
            "live_results": live_results if live_results else None,
        }
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2)
        print(f"💾 Saved JSON Evaluation Data to: {Colors.CYAN}{output_json}{Colors.RESET}")

    print(f"\n{Colors.GREEN}{'=' * 75}{Colors.RESET}\n")
    return metrics


def main():
    parser = argparse.ArgumentParser(description="DocAgent Benchmark & Evaluation Suite")
    parser.add_argument(
        "--mode",
        choices=["offline", "live", "all"],
        default="offline",
        help="Evaluation mode: 'offline' (fast/deterministic logic tests), 'live' (with LLM extraction), 'all'",
    )
    parser.add_argument(
        "--eval-dir",
        type=Path,
        default=PROJECT_ROOT / "eval",
        help="Path to eval directory containing invoices/ and ground_truth/",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=PROJECT_ROOT / "eval" / "eval_report.md",
        help="Path to write Markdown summary report",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=PROJECT_ROOT / "eval" / "eval_report.json",
        help="Path to write full JSON report",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print verbose failure information during test execution",
    )

    args = parser.parse_args()
    run_evaluation_suite(
        eval_dir=args.eval_dir,
        mode=args.mode,
        output_md=args.output_md,
        output_json=args.output_json,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
