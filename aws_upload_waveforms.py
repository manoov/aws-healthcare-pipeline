#!/usr/bin/env python3
"""
Upload local MIMIC WFDB waveform files to S3 and register metadata in DynamoDB.

Usage:
    python aws_upload_waveforms.py --wfdb-root physionet.org/files/mimic-iv-ecg/1.0
    python aws_upload_waveforms.py --wfdb-root /data/mimic --max-records 10 --dry-run
"""

import argparse
import hashlib
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from aws_config import AWSConfig


# ---------------------------------------------------------------------------
# WFDB discovery (reuses logic from the existing codebase)
# ---------------------------------------------------------------------------
def discover_wfdb_records(wfdb_root: str, max_records: int | None = None):
    """Find WFDB record base paths under *wfdb_root*."""
    import csv

    root = Path(wfdb_root)
    if not root.exists():
        raise FileNotFoundError(f"WFDB root not found: {wfdb_root}")

    records: list[str] = []
    record_list = root / "record_list.csv"

    if record_list.exists():
        with record_list.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames or "path" not in reader.fieldnames:
                raise ValueError(f"'path' column missing in {record_list}")
            for row in reader:
                rel = (row.get("path") or "").strip()
                if not rel:
                    continue
                if rel.startswith("./"):
                    rel = rel[2:]
                if rel.endswith((".hea", ".dat")):
                    rel = rel.rsplit(".", 1)[0]
                records.append(str((root / rel).resolve()))
                if max_records and len(records) >= max_records:
                    break
    else:
        for hea in sorted(root.rglob("*.hea")):
            records.append(str(hea.with_suffix("").resolve()))
            if max_records and len(records) >= max_records:
                break

    if not records:
        raise ValueError("No WFDB records found under the specified root.")
    return records


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------
def extract_record_metadata(record_base: str) -> dict:
    """Read a WFDB record header and return metadata dict."""
    try:
        import wfdb
    except ImportError as exc:
        raise ImportError("pip install wfdb") from exc

    header = wfdb.rdheader(record_base)
    return {
        "channels": header.sig_name if header.sig_name else [],
        "num_signals": int(header.n_sig) if header.n_sig else 0,
        "sampling_freq": float(header.fs) if header.fs else 0.0,
        "duration_sec": round(
            float(header.sig_len / header.fs) if header.fs and header.sig_len else 0.0,
            2,
        ),
        "sig_len": int(header.sig_len) if header.sig_len else 0,
        "units": header.units if hasattr(header, "units") and header.units else [],
    }


# ---------------------------------------------------------------------------
# S3 upload
# ---------------------------------------------------------------------------
def upload_record_files(
    s3_client,
    bucket: str,
    record_base: str,
    prefix: str,
    dry_run: bool = False,
) -> list[str]:
    """Upload all files belonging to a WFDB record (.hea, .dat, etc.) to S3."""
    base = Path(record_base)
    parent = base.parent
    stem = base.name

    files_to_upload = list(parent.glob(f"{stem}.*"))
    uploaded_keys: list[str] = []

    for local_file in files_to_upload:
        s3_key = f"{prefix}{local_file.name}"
        if dry_run:
            print(f"  [DRY-RUN] Would upload {local_file} → s3://{bucket}/{s3_key}")
        else:
            s3_client.upload_file(str(local_file), bucket, s3_key)
            print(f"  Uploaded {local_file.name} → s3://{bucket}/{s3_key}")
        uploaded_keys.append(s3_key)

    return uploaded_keys


# ---------------------------------------------------------------------------
# DynamoDB metadata registration
# ---------------------------------------------------------------------------
def register_metadata(
    table,
    record_id: str,
    patient_id: str,
    s3_prefix: str,
    metadata: dict,
    dry_run: bool = False,
):
    """Write record metadata to the DynamoDB table."""
    item = {
        "record_id": record_id,
        "patient_id": patient_id,
        "s3_raw_prefix": s3_prefix,
        "channels": metadata.get("channels", []),
        "num_signals": metadata.get("num_signals", 0),
        "sampling_freq": str(metadata.get("sampling_freq", 0)),
        "duration_sec": str(metadata.get("duration_sec", 0)),
        "sig_len": metadata.get("sig_len", 0),
        "units": metadata.get("units", []),
        "processing_status": "uploaded",
        "upload_timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if dry_run:
        print(f"  [DRY-RUN] Would write DynamoDB item: {record_id}")
    else:
        table.put_item(Item=item)
        print(f"  Registered metadata for {record_id}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def derive_ids(record_base: str):
    """Derive a record_id and patient_id from the file path."""
    parts = Path(record_base).parts
    # Try to extract patient-like folder from the path
    # Typical MIMIC paths: .../p1000/p10000032/s12345678/...
    patient_id = "unknown"
    for part in parts:
        if part.startswith("p") and part[1:].isdigit():
            patient_id = part
            # Keep looking — deeper match is more specific
    record_id = Path(record_base).stem
    # Make unique if record names repeat across patients
    unique_hash = hashlib.md5(record_base.encode()).hexdigest()[:8]
    record_id = f"{record_id}_{unique_hash}"
    return record_id, patient_id


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Upload MIMIC WFDB waveform files to S3 and register metadata."
    )
    parser.add_argument(
        "--wfdb-root",
        required=True,
        help="Local path to MIMIC WFDB root directory.",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Maximum number of records to upload.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without making AWS calls.",
    )
    parser.add_argument(
        "--stack-name",
        default=None,
        help="CloudFormation stack name (overrides default).",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="AWS region (overrides default).",
    )
    args = parser.parse_args()

    # Config
    cfg_kwargs = {}
    if args.stack_name:
        cfg_kwargs["stack_name"] = args.stack_name
    if args.region:
        cfg_kwargs["region"] = args.region
    cfg = AWSConfig(**cfg_kwargs)

    # AWS clients (skip if dry-run and stack doesn't exist)
    s3 = None
    table = None
    if not args.dry_run:
        s3 = cfg.s3_client()
        table = cfg.dynamodb_table()

    # Discover records
    record_bases = discover_wfdb_records(args.wfdb_root, max_records=args.max_records)
    print(f"Found {len(record_bases)} WFDB records to upload.\n")

    uploaded = 0
    skipped = 0

    for record_base in record_bases:
        record_id, patient_id = derive_ids(record_base)
        s3_prefix = f"{cfg.raw_prefix}{patient_id}/{record_id}/"

        print(f"[{uploaded + skipped + 1}/{len(record_bases)}] {Path(record_base).name}")

        # Extract metadata
        try:
            metadata = extract_record_metadata(record_base)
        except Exception as exc:
            print(f"  ⚠ Skipping (metadata error): {exc}")
            skipped += 1
            continue

        # Upload files to S3
        try:
            upload_record_files(
                s3_client=s3,
                bucket=cfg.raw_bucket,
                record_base=record_base,
                prefix=s3_prefix,
                dry_run=args.dry_run,
            )
        except Exception as exc:
            print(f"  ⚠ Skipping (upload error): {exc}")
            skipped += 1
            continue

        # Register in DynamoDB
        try:
            register_metadata(
                table=table,
                record_id=record_id,
                patient_id=patient_id,
                s3_prefix=s3_prefix,
                metadata=metadata,
                dry_run=args.dry_run,
            )
        except Exception as exc:
            print(f"  ⚠ Metadata registration failed: {exc}")

        uploaded += 1

    print(f"\n{'=' * 50}")
    print(f"Upload complete: {uploaded} uploaded, {skipped} skipped")
    if args.dry_run:
        print("(dry-run mode — no AWS resources were modified)")


if __name__ == "__main__":
    main()
