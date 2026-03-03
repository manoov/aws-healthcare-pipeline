"""
Central AWS configuration for the healthcare waveform pipeline.

All resource names, regions, and S3 key conventions are defined here.
At runtime, resolved bucket names come from CloudFormation stack outputs
so the same code works across dev / staging / prod deployments.
"""

import boto3
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Defaults (override via environment or constructor arguments)
# ---------------------------------------------------------------------------
DEFAULT_STACK_NAME = "healthcare-waveform-pipeline"
DEFAULT_REGION = "us-east-1"


@dataclass
class AWSConfig:
    """Immutable configuration object for the pipeline."""

    stack_name: str = DEFAULT_STACK_NAME
    region: str = DEFAULT_REGION

    # S3 key prefixes
    raw_prefix: str = "raw/"
    processed_prefix: str = "processed/"
    models_prefix: str = "models/"

    # DynamoDB
    dynamodb_table_name: str = "WaveformRecords"

    # Athena
    athena_database: str = "healthcare_waveforms"
    athena_workgroup: str = "healthcare-workgroup"

    # Resolved from CloudFormation outputs (populated lazily)
    _stack_outputs: dict = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------
    # Lazy resolution helpers
    # ------------------------------------------------------------------
    def _ensure_outputs(self) -> None:
        """Fetch CloudFormation stack outputs once and cache them."""
        if self._stack_outputs:
            return
        cfn = boto3.client("cloudformation", region_name=self.region)
        try:
            resp = cfn.describe_stacks(StackName=self.stack_name)
            outputs = resp["Stacks"][0].get("Outputs", [])
            self._stack_outputs = {o["OutputKey"]: o["OutputValue"] for o in outputs}
        except Exception:
            # Stack may not exist yet (local dev / dry-run mode)
            self._stack_outputs = {}

    def _output(self, key: str, fallback: str) -> str:
        self._ensure_outputs()
        return self._stack_outputs.get(key, fallback)

    # ------------------------------------------------------------------
    # Resolved bucket names
    # ------------------------------------------------------------------
    @property
    def raw_bucket(self) -> str:
        return self._output("RawWaveformBucketName", f"{self.stack_name}-raw-waveforms")

    @property
    def processed_bucket(self) -> str:
        return self._output("ProcessedDataBucketName", f"{self.stack_name}-processed-data")

    @property
    def athena_results_bucket(self) -> str:
        return self._output("AthenaResultsBucketName", f"{self.stack_name}-athena-results")

    # ------------------------------------------------------------------
    # Boto3 client / resource helpers
    # ------------------------------------------------------------------
    def s3_client(self):
        return boto3.client("s3", region_name=self.region)

    def dynamodb_resource(self):
        return boto3.resource("dynamodb", region_name=self.region)

    def dynamodb_table(self):
        return self.dynamodb_resource().Table(self.dynamodb_table_name)

    def athena_client(self):
        return boto3.client("athena", region_name=self.region)
