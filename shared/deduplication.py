"""
Deduplication utility — used across all scrapers.
Normalizes company names before comparison.
"""
import re


def normalize(name: str) -> str:
    """Lowercase, strip punctuation, collapse spaces."""
    name = name.lower().strip()
    name = re.sub(r"[,.\-'\"&]", " ", name)
    name = re.sub(r"\b(llc|inc|corp|ltd|co|the)\b", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def is_duplicate(company_name: str, existing_names: set[str]) -> bool:
    """Return True if normalized name is already in the existing set."""
    return normalize(company_name) in existing_names


def build_existing_set(records: list[dict]) -> set[str]:
    """Build a normalized name set from a list of Airtable records."""
    return {
        normalize(r.get("fields", {}).get("Company Name", ""))
        for r in records
        if r.get("fields", {}).get("Company Name")
    }