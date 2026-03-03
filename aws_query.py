#!/usr/bin/env python3
"""
Query interface for healthcare waveform data.

Supports:
  - Athena SQL queries over processed waveform CSVs in S3
  - DynamoDB lookups for record metadata

Usage:
    # Athena query
    python aws_query.py --type athena --query "SELECT * FROM processed_waveforms LIMIT 10"

    # DynamoDB: get a specific record
    python aws_query.py --type dynamodb --record-id <record_id>

    # DynamoDB: list records for a patient
    python aws_query.py --type dynamodb --patient-id <patient_id>

    # DynamoDB: list records by status
    python aws_query.py --type dynamodb --status uploaded
"""

import argparse
import json
import time

import pandas as pd

from aws_config import AWSConfig


# ---------------------------------------------------------------------------
# Athena queries
# ---------------------------------------------------------------------------
class AthenaQuerier:
    """Execute Athena SQL queries and return results as DataFrames."""

    def __init__(self, cfg: AWSConfig):
        self.cfg = cfg
        self.client = cfg.athena_client()

    def run_query(self, sql: str, timeout_sec: int = 120) -> pd.DataFrame:
        """Submit an Athena query, wait for completion, and return results."""
        print(f"Submitting Athena query...")
        print(f"  SQL: {sql[:200]}{'...' if len(sql) > 200 else ''}")

        response = self.client.start_query_execution(
            QueryString=sql,
            QueryExecutionContext={"Database": self.cfg.athena_database},
            WorkGroup=self.cfg.athena_workgroup,
        )
        query_id = response["QueryExecutionId"]
        print(f"  Query ID: {query_id}")

        # Poll for completion
        start = time.time()
        while True:
            status_resp = self.client.get_query_execution(QueryExecutionId=query_id)
            state = status_resp["QueryExecution"]["Status"]["State"]

            if state == "SUCCEEDED":
                break
            elif state in ("FAILED", "CANCELLED"):
                reason = status_resp["QueryExecution"]["Status"].get(
                    "StateChangeReason", "Unknown"
                )
                raise RuntimeError(f"Athena query {state}: {reason}")

            if time.time() - start > timeout_sec:
                raise TimeoutError(
                    f"Athena query did not complete within {timeout_sec}s."
                )
            time.sleep(1)

        elapsed = round(time.time() - start, 1)
        print(f"  Completed in {elapsed}s")

        # Fetch results
        return self._fetch_results(query_id)

    def _fetch_results(self, query_id: str) -> pd.DataFrame:
        """Download Athena query results into a DataFrame."""
        results = []
        columns = []
        next_token = None

        while True:
            kwargs = {"QueryExecutionId": query_id, "MaxResults": 1000}
            if next_token:
                kwargs["NextToken"] = next_token

            resp = self.client.get_query_results(**kwargs)

            # Extract column names from the first page
            if not columns:
                col_info = resp["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]
                columns = [c["Name"] for c in col_info]

            rows = resp["ResultSet"]["Rows"]
            # Skip header row on first page
            start_idx = 1 if not results else 0
            for row in rows[start_idx:]:
                values = [d.get("VarCharValue", "") for d in row["Data"]]
                results.append(values)

            next_token = resp.get("NextToken")
            if not next_token:
                break

        df = pd.DataFrame(results, columns=columns)
        print(f"  Returned {len(df)} rows, {len(columns)} columns")
        return df


# ---------------------------------------------------------------------------
# DynamoDB queries
# ---------------------------------------------------------------------------
class DynamoDBQuerier:
    """Query the WaveformRecords DynamoDB table."""

    def __init__(self, cfg: AWSConfig):
        self.cfg = cfg
        self.table = cfg.dynamodb_table()

    def get_record(self, record_id: str) -> dict | None:
        """Fetch a single record by record_id."""
        resp = self.table.get_item(Key={"record_id": record_id})
        return resp.get("Item")

    def get_patient_records(self, patient_id: str) -> list[dict]:
        """Fetch all records for a given patient using the PatientIndex GSI."""
        resp = self.table.query(
            IndexName="PatientIndex",
            KeyConditionExpression="patient_id = :pid",
            ExpressionAttributeValues={":pid": patient_id},
        )
        return resp.get("Items", [])

    def get_records_by_status(self, status: str) -> list[dict]:
        """Fetch records by processing status using the StatusIndex GSI."""
        resp = self.table.query(
            IndexName="StatusIndex",
            KeyConditionExpression="processing_status = :status",
            ExpressionAttributeValues={":status": status},
        )
        return resp.get("Items", [])

    def scan_all_records(self, limit: int = 100) -> list[dict]:
        """Scan all records (for dashboard browsing)."""
        resp = self.table.scan(Limit=limit)
        return resp.get("Items", [])

    def get_processing_summary(self) -> dict:
        """Get counts by processing status."""
        items = self.table.scan(
            ProjectionExpression="processing_status",
        ).get("Items", [])

        summary = {}
        for item in items:
            status = item.get("processing_status", "unknown")
            summary[status] = summary.get(status, 0) + 1
        return summary


# ---------------------------------------------------------------------------
# Convenience functions (importable from other modules)
# ---------------------------------------------------------------------------
def get_record_metadata(record_id: str, cfg: AWSConfig = None) -> dict | None:
    """Quick lookup for a single record."""
    if cfg is None:
        cfg = AWSConfig()
    return DynamoDBQuerier(cfg).get_record(record_id)


def search_records(patient_id: str = None, status: str = None, cfg: AWSConfig = None):
    """Search records by patient or status."""
    if cfg is None:
        cfg = AWSConfig()
    querier = DynamoDBQuerier(cfg)
    if patient_id:
        return querier.get_patient_records(patient_id)
    if status:
        return querier.get_records_by_status(status)
    return querier.scan_all_records()


def run_athena_query(sql: str, cfg: AWSConfig = None) -> pd.DataFrame:
    """Execute an Athena query and return a DataFrame."""
    if cfg is None:
        cfg = AWSConfig()
    return AthenaQuerier(cfg).run_query(sql)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Query healthcare waveform data.")
    parser.add_argument(
        "--type",
        choices=["athena", "dynamodb"],
        required=True,
        help="Query backend.",
    )
    parser.add_argument("--query", help="Athena SQL query string.")
    parser.add_argument("--record-id", help="DynamoDB: specific record ID.")
    parser.add_argument("--patient-id", help="DynamoDB: patient ID.")
    parser.add_argument("--status", help="DynamoDB: filter by processing status.")
    parser.add_argument("--limit", type=int, default=50, help="Max results to display.")
    parser.add_argument("--output-csv", help="Save results to CSV file.")
    parser.add_argument("--stack-name", default=None)
    parser.add_argument("--region", default=None)
    args = parser.parse_args()

    cfg_kwargs = {}
    if args.stack_name:
        cfg_kwargs["stack_name"] = args.stack_name
    if args.region:
        cfg_kwargs["region"] = args.region
    cfg = AWSConfig(**cfg_kwargs)

    if args.type == "athena":
        if not args.query:
            parser.error("--query is required for Athena queries.")
        df = run_athena_query(args.query, cfg)
        print(f"\n{df.to_string(max_rows=args.limit)}")
        if args.output_csv:
            df.to_csv(args.output_csv, index=False)
            print(f"\nSaved to {args.output_csv}")

    elif args.type == "dynamodb":
        querier = DynamoDBQuerier(cfg)
        if args.record_id:
            item = querier.get_record(args.record_id)
            if item:
                print(json.dumps(item, indent=2, default=str))
            else:
                print(f"Record '{args.record_id}' not found.")
        elif args.patient_id:
            items = querier.get_patient_records(args.patient_id)
            print(f"Found {len(items)} records for patient {args.patient_id}:")
            for item in items[: args.limit]:
                print(
                    f"  {item['record_id']}  "
                    f"status={item.get('processing_status', '?')}  "
                    f"channels={item.get('channels', [])}"
                )
        elif args.status:
            items = querier.get_records_by_status(args.status)
            print(f"Found {len(items)} records with status '{args.status}':")
            for item in items[: args.limit]:
                print(f"  {item['record_id']}")
        else:
            # Show summary
            summary = querier.get_processing_summary()
            print("Processing status summary:")
            for status, count in sorted(summary.items()):
                print(f"  {status}: {count}")


if __name__ == "__main__":
    main()
