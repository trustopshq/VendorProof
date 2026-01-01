#!/usr/bin/env python3
"""
Optional Notion import helper.
Dry-run by default. Use --apply to import questions and sample data into an existing template.
Requires the Marketplace template to be installed first.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Dict, Optional
from urllib.error import HTTPError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_SAMPLE_DATA_DIR = PROJECT_ROOT / "product" / "sample_data"
DEFAULT_QUESTIONS_CSV = PROJECT_ROOT / "product" / "packs" / "saas_core" / "questions.csv"

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2025-09-03"


class BootstrapError(Exception):
    pass


@dataclass
class BootstrapPlan:
    questions: int
    vendors: int
    assessments: int
    assessment_items: int


def count_csv_rows(csv_path: Path) -> int:
    if not csv_path.exists():
        raise BootstrapError(f"Missing CSV file: {csv_path}")
    with csv_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    return len(rows)


def build_plan(sample_data_dir: Path, questions_csv: Path) -> BootstrapPlan:
    return BootstrapPlan(
        questions=count_csv_rows(questions_csv),
        vendors=count_csv_rows(sample_data_dir / "vendors.csv"),
        assessments=count_csv_rows(sample_data_dir / "assessments.csv"),
        assessment_items=count_csv_rows(sample_data_dir / "assessment_items.csv"),
    )


def format_plan(plan: BootstrapPlan) -> str:
    lines = ["Notion import plan (dry-run)", ""]
    lines.append("CSV imports (row counts):")
    lines.append(f"- questions.csv: {plan.questions} rows")
    lines.append(f"- vendors.csv: {plan.vendors} rows")
    lines.append(f"- assessments.csv: {plan.assessments} rows")
    lines.append(f"- assessment_items.csv: {plan.assessment_items} rows")
    lines.append("")
    lines.append("Template databases required:")
    lines.append("- Vendors")
    lines.append("- Assessments")
    lines.append("- Question Library")
    lines.append("- Assessment Items")
    return "\n".join(lines)


def notion_request(token: str, method: str, path: str, payload: Optional[dict] = None) -> dict:
    url = f"{NOTION_API_BASE}{path}"
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Notion-Version", NOTION_VERSION)
    request.add_header("Content-Type", "application/json")
    try:
        with urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8") if exc.fp else ""
        raise BootstrapError(f"Notion API error {exc.code}: {body}") from exc


def find_data_source_id(token: str, name: str) -> str:
    payload = {
        "filter": {"property": "object", "value": "data_source"},
        "query": name,
        "page_size": 10,
    }
    result = notion_request(token, "POST", "/search", payload)
    results = result.get("results", [])
    for item in results:
        title = item.get("title", [])
        title_text = "".join(part.get("plain_text", "") for part in title)
        if title_text == name:
            return item["id"]
    raise BootstrapError(
        f"Data source not found: {name}. Ensure the template is installed and shared with the integration."
    )


def build_text_value(value: str) -> list:
    return [{"text": {"content": value}}]


def build_property_value(prop_type: str, value: str):
    raw = value.strip()
    if raw == "":
        return None
    if prop_type == "title":
        return {"title": build_text_value(raw)}
    if prop_type == "rich_text":
        return {"rich_text": build_text_value(raw)}
    if prop_type == "select":
        return {"select": {"name": raw}}
    if prop_type == "multi_select":
        parts = [v.strip() for v in raw.split(",") if v.strip()]
        return {"multi_select": [{"name": part} for part in parts]}
    if prop_type == "number":
        return {"number": float(raw)}
    if prop_type == "checkbox":
        return {"checkbox": raw.upper() == "TRUE"}
    if prop_type == "email":
        return {"email": raw}
    if prop_type == "date":
        return {"date": {"start": raw}}
    if prop_type == "url":
        return {"url": raw}
    return None


def create_page(token: str, data_source_id: str, properties: dict) -> str:
    payload = {
        "parent": {"type": "data_source_id", "data_source_id": data_source_id},
        "properties": properties,
    }
    result = notion_request(token, "POST", "/pages", payload)
    return result["id"]


def import_questions(token: str, data_source_id: str, csv_path: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    with csv_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            question_title = row["Question"].strip()
            props = {
                "Question": build_property_value("title", question_title),
                "Question Code": build_property_value("rich_text", row["Question Code"]),
                "Domain": build_property_value("select", row["Domain"]),
                "Question Type": build_property_value("select", row["Question Type"]),
                "Weight": build_property_value("number", row["Weight"]),
                "Critical": build_property_value("checkbox", row["Critical"]),
                "Evidence Required": build_property_value("checkbox", row["Evidence Required"]),
                "Suggested Evidence": build_property_value("rich_text", row["Suggested Evidence"]),
                "Reference Tags": build_property_value("rich_text", row["Reference Tags"]),
                "Pack": build_property_value("multi_select", row["Pack"]),
            }
            props = {k: v for k, v in props.items() if v is not None}
            page_id = create_page(token, data_source_id, props)
            mapping[question_title] = page_id
            time.sleep(0.1)
    return mapping


def import_vendors(token: str, data_source_id: str, csv_path: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    with csv_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            vendor_name = row["Vendor"].strip()
            props = {
                "Vendor": build_property_value("title", vendor_name),
                "Category": build_property_value("select", row["Category"]),
                "Criticality": build_property_value("select", row["Criticality"]),
                "Data Access": build_property_value("multi_select", row["Data Access"]),
                "Vendor Contact Email": build_property_value("email", row["Vendor Contact Email"]),
                "Status": build_property_value("select", row["Status"]),
                "Renewal Date": build_property_value("date", row["Renewal Date"]),
                "Notes": build_property_value("rich_text", row["Notes"]),
            }
            props = {k: v for k, v in props.items() if v is not None}
            page_id = create_page(token, data_source_id, props)
            mapping[vendor_name] = page_id
            time.sleep(0.1)
    return mapping


def import_assessments(
    token: str,
    data_source_id: str,
    csv_path: Path,
    vendor_ids: Dict[str, str],
) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    with csv_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            vendor_name = row["Vendor"].strip()
            vendor_id = vendor_ids.get(vendor_name)
            if not vendor_id:
                raise BootstrapError(f"Unknown vendor in assessments.csv: {vendor_name}")
            assessment_title = row["Assessment"].strip()
            props = {
                "Assessment": build_property_value("title", assessment_title),
                "Vendor": {"relation": [{"id": vendor_id}]},
                "Type": build_property_value("select", row["Type"]),
                "Scope Pack": build_property_value("select", row["Scope Pack"]),
                "Status": build_property_value("select", row["Status"]),
                "Start Date": build_property_value("date", row["Start Date"]),
                "Due Date": build_property_value("date", row["Due Date"]),
                "End Date": build_property_value("date", row["End Date"]),
                "Decision": build_property_value("select", row["Decision"]),
                "Conditions": build_property_value("rich_text", row["Conditions"]),
                "Decision Date": build_property_value("date", row["Decision Date"]),
            }
            props = {k: v for k, v in props.items() if v is not None}
            page_id = create_page(token, data_source_id, props)
            mapping[assessment_title] = page_id
            time.sleep(0.1)
    return mapping


def import_assessment_items(
    token: str,
    data_source_id: str,
    csv_path: Path,
    assessment_ids: Dict[str, str],
    question_ids: Dict[str, str],
) -> None:
    with csv_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            assessment_title = row["Assessment"].strip()
            assessment_id = assessment_ids.get(assessment_title)
            if not assessment_id:
                raise BootstrapError(
                    f"Unknown assessment in assessment_items.csv: {assessment_title}"
                )
            question_title = row["Question"].strip()
            question_id = question_ids.get(question_title)
            if not question_id:
                raise BootstrapError(f"Unknown question in assessment_items.csv: {question_title}")
            title = f"{assessment_title} | {question_title}"
            props = {
                "Item": build_property_value("title", title),
                "Assessment": {"relation": [{"id": assessment_id}]},
                "Question": {"relation": [{"id": question_id}]},
                "Response Score Raw": build_property_value("number", row["Response Score Raw"]),
                "Response Text": build_property_value("rich_text", row["Response Text"]),
                "Evidence Status": build_property_value("select", row["Evidence Status"]),
                "Finding Severity": build_property_value("select", row["Finding Severity"]),
                "Notes": build_property_value("rich_text", row["Notes"]),
            }
            props = {k: v for k, v in props.items() if v is not None}
            create_page(token, data_source_id, props)
            time.sleep(0.1)


def apply_import(token: str, sample_data_dir: Path, questions_csv: Path) -> None:
    question_ds = find_data_source_id(token, "Question Library")
    vendors_ds = find_data_source_id(token, "Vendors")
    assessments_ds = find_data_source_id(token, "Assessments")
    items_ds = find_data_source_id(token, "Assessment Items")

    question_ids = import_questions(token, question_ds, questions_csv)
    vendor_ids = import_vendors(token, vendors_ds, sample_data_dir / "vendors.csv")
    assessment_ids = import_assessments(
        token,
        assessments_ds,
        sample_data_dir / "assessments.csv",
        vendor_ids,
    )
    import_assessment_items(
        token,
        items_ds,
        sample_data_dir / "assessment_items.csv",
        assessment_ids,
        question_ids,
    )

    print("Import complete. Evidence Inbox remains empty by design.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Notion import helper (optional).")
    parser.add_argument("--sample-data-dir", type=Path, default=DEFAULT_SAMPLE_DATA_DIR)
    parser.add_argument("--questions-csv", type=Path, default=DEFAULT_QUESTIONS_CSV)
    parser.add_argument("--apply", action="store_true", help="Import data via Notion API.")
    parser.add_argument("--token", help="Notion integration token (overrides NOTION_TOKEN).")
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Do not prompt for missing credentials.",
    )
    return parser.parse_args()


def resolve_token(token_arg: Optional[str], allow_prompt: bool) -> str:
    import os

    token = token_arg or os.environ.get("NOTION_TOKEN")
    if token:
        return token

    if not allow_prompt:
        raise BootstrapError("Missing required env var: NOTION_TOKEN")

    token = getpass("Enter NOTION_TOKEN: ").strip()
    if not token:
        raise BootstrapError("NOTION_TOKEN is empty")
    return token


def main() -> int:
    args = parse_args()
    plan = build_plan(args.sample_data_dir, args.questions_csv)

    if not args.apply:
        print(format_plan(plan))
        return 0

    token = resolve_token(args.token, not args.no_prompt)
    apply_import(token, args.sample_data_dir, args.questions_csv)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BootstrapError as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)
