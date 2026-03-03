#!/usr/bin/env python3
"""
Process waveform records: download from S3, run autoencoder compression,
upload results back to S3, and update DynamoDB with metrics.

Usage:
    # Process a single record
    python aws_process_pipeline.py --record-id <record_id>

    # Process all unprocessed records
    python aws_process_pipeline.py --all-unprocessed

    # Process with a specific model from S3
    python aws_process_pipeline.py --record-id <id> --model-s3-key models/autoencoder.h5
"""

import argparse
import csv
import io
import os
import tempfile
from datetime import datetime, timezone
from math import sqrt
from pathlib import Path

import numpy as np

from aws_config import AWSConfig


# ---------------------------------------------------------------------------
# Signal processing (adapted from existing codebase)
# ---------------------------------------------------------------------------
def create_blocks(signal, block_size=36):
    """Segment signal into fixed-length blocks."""
    n = len(signal) // block_size
    if n == 0:
        raise ValueError(
            f"Signal length ({len(signal)}) too short for block size {block_size}."
        )
    return signal[: n * block_size].reshape(n, block_size)


def compute_metrics(original, reconstructed):
    """Compute reconstruction quality metrics."""
    o = np.nan_to_num(original)
    r = np.nan_to_num(reconstructed)
    mse = float(np.mean((o - r) ** 2))
    mae = float(np.mean(np.abs(o - r)))
    prd = float(100 * sqrt(np.sum((o - r) ** 2) / (np.sum(o ** 2) + 1e-12)))
    rms = float(sqrt(mse))
    quality = float(1 - (np.linalg.norm(o - r) / (np.linalg.norm(o) + 1e-8)))
    return {"mse": mse, "mae": mae, "prd": prd, "rms": rms, "quality": quality}


# ---------------------------------------------------------------------------
# S3 download helpers
# ---------------------------------------------------------------------------
def download_wfdb_from_s3(s3_client, bucket: str, s3_prefix: str, local_dir: str):
    """Download all files under an S3 prefix to a local directory."""
    paginator = s3_client.get_paginator("list_objects_v2")
    downloaded = []

    for page in paginator.paginate(Bucket=bucket, Prefix=s3_prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            filename = key.split("/")[-1]
            if not filename:
                continue
            local_path = os.path.join(local_dir, filename)
            s3_client.download_file(bucket, key, local_path)
            downloaded.append(local_path)

    return downloaded


def find_record_base(local_dir: str) -> str:
    """Find the WFDB record base path from downloaded files."""
    for f in os.listdir(local_dir):
        if f.endswith(".hea"):
            return os.path.join(local_dir, f.replace(".hea", ""))
    raise FileNotFoundError(f"No .hea file found in {local_dir}")


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------
def load_and_extract_signal(record_base: str, preferred_channels=None):
    """Load one channel from a WFDB record."""
    import wfdb

    if preferred_channels is None:
        preferred_channels = ["II", "ABP", "ART", "V1"]

    signals, metadata = wfdb.rdsamp(record_base)
    signals = np.asarray(signals, dtype=np.float32)

    if signals.ndim == 1:
        return signals, "single_channel"

    channel_names = [str(x).upper() for x in metadata.get("sig_name", [])]

    # Find best channel
    for pref in preferred_channels:
        pref_upper = pref.upper()
        for idx, name in enumerate(channel_names):
            if pref_upper == name or pref_upper in name:
                channel_used = metadata["sig_name"][idx]
                return signals[:, idx], channel_used

    return signals[:, 0], (metadata["sig_name"][0] if metadata["sig_name"] else "ch0")


def run_autoencoder_pipeline(
    signal: np.ndarray,
    model_path: str,
    channel_name: str,
    record_id: str,
):
    """Run the autoencoder compression and return results."""
    from tensorflow.keras import backend as K
    from tensorflow.keras.models import load_model

    def combined_loss(y_true, y_pred):
        mse = K.mean(K.square(y_true - y_pred))
        mae = K.mean(K.abs(y_true - y_pred))
        return mse + mae

    # Load model
    autoencoder = load_model(model_path, custom_objects={"combined_loss": combined_loss})
    block_size = int(autoencoder.input_shape[-1])

    # Clean signal
    signal = signal[np.isfinite(signal)]
    if len(signal) == 0:
        raise ValueError("No finite values in signal.")

    # Create blocks and normalize
    blocks = create_blocks(signal, block_size=block_size)
    mean_val = blocks.mean()
    std_val = blocks.std() + 1e-8
    blocks_norm = (blocks - mean_val) / std_val

    # Reconstruct
    recon_norm = autoencoder.predict(blocks_norm, verbose=0)
    recon = (recon_norm * std_val + mean_val).flatten()

    original = signal[: len(recon)]
    metrics = compute_metrics(original, recon)

    # Build result rows
    rows = []
    for i in range(len(original)):
        rows.append({
            "record_id": record_id,
            "sample_index": i,
            "original_value": float(original[i]),
            "reconstructed_value": float(recon[i]),
            "channel": channel_name,
            "compression_method": "autoencoder",
        })

    return rows, metrics


def results_to_csv_bytes(rows: list[dict]) -> bytes:
    """Convert result rows to CSV bytes for S3 upload."""
    output = io.StringIO()
    if not rows:
        return b""
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# Upload results
# ---------------------------------------------------------------------------
def upload_results(s3_client, bucket: str, s3_key: str, csv_bytes: bytes):
    """Upload processed CSV to S3."""
    s3_client.put_object(Bucket=bucket, Key=s3_key, Body=csv_bytes)


def update_dynamodb_status(table, record_id: str, status: str, metrics: dict = None):
    """Update DynamoDB record with processing status and metrics."""
    update_expr = "SET processing_status = :status, processed_timestamp = :ts"
    expr_values = {
        ":status": status,
        ":ts": datetime.now(timezone.utc).isoformat(),
    }

    if metrics:
        update_expr += (
            ", metric_mse = :mse, metric_mae = :mae, metric_prd = :prd"
            ", metric_rms = :rms, metric_quality = :quality"
        )
        expr_values.update({
            ":mse": str(round(metrics["mse"], 8)),
            ":mae": str(round(metrics["mae"], 8)),
            ":prd": str(round(metrics["prd"], 4)),
            ":rms": str(round(metrics["rms"], 8)),
            ":quality": str(round(metrics["quality"], 6)),
        })

    table.update_item(
        Key={"record_id": record_id},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_values,
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def process_record(cfg: AWSConfig, record_id: str, model_path: str):
    """Full pipeline for a single record."""
    s3 = cfg.s3_client()
    table = cfg.dynamodb_table()

    # 1. Get metadata from DynamoDB
    response = table.get_item(Key={"record_id": record_id})
    item = response.get("Item")
    if not item:
        raise ValueError(f"Record {record_id} not found in DynamoDB.")

    s3_prefix = item["s3_raw_prefix"]
    print(f"Processing record: {record_id}")
    print(f"  S3 raw prefix: {s3_prefix}")

    # 2. Download waveform files
    with tempfile.TemporaryDirectory() as tmp_dir:
        print("  Downloading from S3...")
        download_wfdb_from_s3(s3, cfg.raw_bucket, s3_prefix, tmp_dir)

        record_base = find_record_base(tmp_dir)
        print(f"  Record base: {Path(record_base).name}")

        # 3. Extract signal
        signal, channel_name = load_and_extract_signal(record_base)
        print(f"  Channel: {channel_name}, Signal length: {len(signal)}")

        # Update status
        update_dynamodb_status(table, record_id, "processing")

        # 4. Run autoencoder pipeline
        print("  Running autoencoder pipeline...")
        rows, metrics = run_autoencoder_pipeline(
            signal, model_path, channel_name, record_id
        )
        print(f"  Quality: {metrics['quality']:.6f}, MSE: {metrics['mse']:.8f}")

    # 5. Upload results to S3
    csv_bytes = results_to_csv_bytes(rows)
    result_key = f"{cfg.processed_prefix}{record_id}/waveform_results.csv"
    upload_results(s3, cfg.processed_bucket, result_key, csv_bytes)
    print(f"  Uploaded results to s3://{cfg.processed_bucket}/{result_key}")

    # 6. Update DynamoDB
    update_dynamodb_status(table, record_id, "completed", metrics)
    print(f"  ✓ Record {record_id} processed successfully.\n")


def get_unprocessed_records(cfg: AWSConfig) -> list[str]:
    """Query DynamoDB for records with status 'uploaded'."""
    table = cfg.dynamodb_table()
    response = table.query(
        IndexName="StatusIndex",
        KeyConditionExpression="processing_status = :status",
        ExpressionAttributeValues={":status": "uploaded"},
    )
    return [item["record_id"] for item in response.get("Items", [])]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Process waveform records: S3 → autoencoder → S3 + DynamoDB."
    )
    parser.add_argument("--record-id", help="Process a specific record by ID.")
    parser.add_argument(
        "--all-unprocessed",
        action="store_true",
        help="Process all records with status 'uploaded'.",
    )
    parser.add_argument(
        "--model-path",
        default="ecg_autoencoder_model_fast.h5",
        help="Local path to the autoencoder model (.h5).",
    )
    parser.add_argument(
        "--model-s3-key",
        default=None,
        help="S3 key to download the model from (inside raw bucket).",
    )
    parser.add_argument("--stack-name", default=None)
    parser.add_argument("--region", default=None)
    args = parser.parse_args()

    cfg_kwargs = {}
    if args.stack_name:
        cfg_kwargs["stack_name"] = args.stack_name
    if args.region:
        cfg_kwargs["region"] = args.region
    cfg = AWSConfig(**cfg_kwargs)

    # Optionally download model from S3
    model_path = args.model_path
    if args.model_s3_key:
        s3 = cfg.s3_client()
        model_path = os.path.join(tempfile.gettempdir(), "autoencoder_model.h5")
        print(f"Downloading model from S3: {args.model_s3_key}")
        s3.download_file(cfg.raw_bucket, args.model_s3_key, model_path)

    if not Path(model_path).exists():
        raise FileNotFoundError(
            f"Model not found: {model_path}. "
            "Provide a local --model-path or --model-s3-key."
        )

    if args.record_id:
        process_record(cfg, args.record_id, model_path)
    elif args.all_unprocessed:
        record_ids = get_unprocessed_records(cfg)
        print(f"Found {len(record_ids)} unprocessed records.\n")
        for rid in record_ids:
            try:
                process_record(cfg, rid, model_path)
            except Exception as exc:
                print(f"  ✗ Failed to process {rid}: {exc}\n")
    else:
        parser.error("Specify --record-id or --all-unprocessed.")


if __name__ == "__main__":
    main()
