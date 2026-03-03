"""
AWS Lambda handler — triggered on S3 PutObject events for raw waveform uploads.

Performs lightweight processing: extracts waveform metadata and basic statistics,
then updates DynamoDB. For full autoencoder pipeline, use aws_process_pipeline.py
or invoke a SageMaker endpoint.
"""

import json
import os
import tempfile
import urllib.parse
from datetime import datetime, timezone

import boto3
import numpy as np

DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "WaveformRecords")
PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET", "")

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")


def lambda_handler(event, context):
    """Process S3 event notifications for new waveform uploads."""
    results = []

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

        # Only process .hea files (one per WFDB record)
        if not key.endswith(".hea"):
            continue

        print(f"Processing: s3://{bucket}/{key}")

        try:
            result = process_waveform(bucket, key)
            results.append({"key": key, "status": "success", **result})
        except Exception as exc:
            print(f"Error processing {key}: {exc}")
            results.append({"key": key, "status": "error", "error": str(exc)})

    return {
        "statusCode": 200,
        "body": json.dumps({"processed": len(results), "results": results}),
    }


def process_waveform(bucket: str, hea_key: str) -> dict:
    """
    Download the WFDB record, extract basic statistics, and update DynamoDB.
    """
    # Derive record info from the S3 key
    # Expected key pattern: raw/<patient_id>/<record_id>/<filename>.hea
    parts = hea_key.rstrip("/").split("/")
    record_stem = parts[-1].replace(".hea", "")

    # Find the S3 prefix for all files of this record
    prefix = "/".join(parts[:-1]) + "/"

    # Derive record_id from the path
    record_id = parts[-2] if len(parts) >= 3 else record_stem

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Download all files for this record
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                obj_key = obj["Key"]
                filename = obj_key.split("/")[-1]
                if filename:
                    local_path = os.path.join(tmp_dir, filename)
                    s3.download_file(bucket, obj_key, local_path)

        record_base = os.path.join(tmp_dir, record_stem)

        # Read waveform and compute basic statistics
        try:
            import wfdb

            signals, metadata = wfdb.rdsamp(record_base)
            signals = np.asarray(signals, dtype=np.float32)

            # Basic stats per channel
            channel_stats = {}
            sig_names = metadata.get("sig_name", [])
            for i, name in enumerate(sig_names):
                col = signals[:, i] if signals.ndim > 1 else signals
                finite = col[np.isfinite(col)]
                if len(finite) > 0:
                    channel_stats[name] = {
                        "mean": round(float(np.mean(finite)), 4),
                        "std": round(float(np.std(finite)), 4),
                        "min": round(float(np.min(finite)), 4),
                        "max": round(float(np.max(finite)), 4),
                        "num_samples": int(len(finite)),
                    }

            stats_summary = {
                "channels": sig_names,
                "sampling_freq": float(metadata.get("fs", 0)),
                "duration_sec": round(
                    float(metadata.get("sig_len", 0)) / max(metadata.get("fs", 1), 1),
                    2,
                ),
                "channel_stats": channel_stats,
            }

        except ImportError:
            # wfdb not in Lambda layer — store minimal info
            stats_summary = {"error": "wfdb not available in Lambda runtime"}

    # Update DynamoDB
    table = dynamodb.Table(DYNAMODB_TABLE)
    table.update_item(
        Key={"record_id": record_id},
        UpdateExpression=(
            "SET processing_status = :status, "
            "lambda_processed_timestamp = :ts, "
            "channel_stats = :stats"
        ),
        ExpressionAttributeValues={
            ":status": "lambda_processed",
            ":ts": datetime.now(timezone.utc).isoformat(),
            ":stats": json.dumps(stats_summary),
        },
    )

    # Optionally upload stats as JSON to processed bucket
    if PROCESSED_BUCKET:
        stats_key = f"processed/{record_id}/channel_stats.json"
        s3.put_object(
            Bucket=PROCESSED_BUCKET,
            Key=stats_key,
            Body=json.dumps(stats_summary, indent=2).encode("utf-8"),
        )

    print(f"✓ Processed {record_id}: {len(stats_summary.get('channels', []))} channels")
    return stats_summary
