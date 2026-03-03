# AWS Healthcare Waveform Pipeline - Setup Guide

This guide walks you through setting up and deploying the AWS healthcare waveform pipeline for MIMIC data processing.

## Prerequisites

- Python 3.9+
- AWS Account with valid credentials configured (`aws configure`)
- AWS CLI installed
- MIMIC-IV ECG data (from PhysioNet)
- A trained autoencoder model file (`.h5`)

## 1. Environment Setup

### Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

**Note:** TensorFlow is heavy (~2GB). If you only need the dashboard/query tools, you can temporarily skip it:
```bash
pip install -r requirements.txt --ignore-installed | grep -v tensorflow
```

## 2. AWS Configuration

### Configure AWS Credentials

```bash
aws configure
# Enter your AWS Access Key ID
# Enter your AWS Secret Access Key
# Default region: us-east-1 (recommended)
# Default output format: json
```

Or set environment variables:
```bash
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_DEFAULT_REGION="us-east-1"
```

### Deploy CloudFormation Stack

```bash
aws cloudformation deploy \
  --template-file aws/cloudformation.yaml \
  --stack-name healthcare-waveform-pipeline \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

**What gets created:**
- S3 Buckets: `*-raw-waveforms`, `*-processed-data`, `*-athena-results`
- DynamoDB Table: `WaveformRecords` with GSIs for PatientIndex and StatusIndex
- Lambda Function: `*-waveform-processor`
- Athena Workgroup: `healthcare-workgroup`
- Glue Catalog Database: `healthcare_waveforms`

## 3. Configure the Pipeline

Edit `aws_config.py` to customize:
- Stack name (if different from default)
- AWS region
- S3 key prefixes (raw/, processed/, models/)
- DynamoDB table name
- Athena database/workgroup names

## 4. Prepare Your Data

### Download MIMIC-IV Data

```bash
# From PhysioNet (requires access)
cd /path/to/data
wget -r -N -c -np --user <username> --ask-password \
  https://physionet.org/files/mimiciv/3.1/
```

### Extract ECG Signals (Optional: if not already extracted)

If you have raw WFDB files, extract them first:
```bash
python extract_waveforms.py --input-dir <path-to-mimic-data> --output-csv signals.csv
```

## 5. Upload Data to S3

### Dry Run (Verify Discovery)

```bash
python aws_upload_waveforms.py \
  --wfdb-root /path/to/mimic-ecg \
  --dry-run
```

This shows what would be uploaded without making changes.

### Upload Data

```bash
# Upload with sample limit
python aws_upload_waveforms.py \
  --wfdb-root /path/to/mimic-ecg \
  --max-records 50

# Upload all records
python aws_upload_waveforms.py \
  --wfdb-root /path/to/mimic-ecg
```

The script will:
- Scan WFDB files in the directory
- Register metadata in DynamoDB
- Upload raw waveforms to S3
- Skip duplicates automatically

## 6. Process Waveforms

### Prerequisites

- Trained autoencoder model: `ecg_autoencoder_model_fast.h5`
- Data uploaded to S3 (from step 5)

### Process Records

```bash
# Process a single record
python aws_process_pipeline.py \
  --record-id <patient_id>_<record_num> \
  --model-path ecg_autoencoder_model_fast.h5

# Process all unprocessed records
python aws_process_pipeline.py \
  --all-unprocessed \
  --model-path ecg_autoencoder_model_fast.h5 \
  --batch-size 10

# Process specific status
python aws_process_pipeline.py \
  --status "UPLOADED" \
  --model-path ecg_autoencoder_model_fast.h5
```

**Options:**
- `--record-id`: Process single record
- `--all-unprocessed`: Process all records with status "UPLOADED"
- `--status`: Filter by status (UPLOADED, PROCESSING, PROCESSED, FAILED)
- `--batch-size`: Number of concurrent processes (default: 5)
- `--max-workers`: Thread pool size (default: 3)

## 7. Query Data

### Query via CLI

```bash
# DynamoDB - Get specific record
python aws_query.py --patient-id <id> --database

# Athena - SQL query
python aws_query.py --sql "SELECT * FROM processed_waveforms LIMIT 5"

# List all records
python aws_query.py --all-records
```

### Query via Python

```python
from aws_query import WaveformQueryAPI

api = WaveformQueryAPI()

# Get record by patient ID
record = api.get_record("patient_12345")

# Run SQL query
results = api.query_sql("SELECT COUNT(*) FROM processed_waveforms")

# List records by status
processed = api.get_records_by_status("PROCESSED")
```

## 8. Launch Dashboard

```bash
streamlit run dashboard/app.py
```

Opens interactive dashboard at `http://localhost:8501` with:
- **Records Browser**: Search and filter waveform records
- **Waveform Viewer**: Plot raw and compressed waveforms
- **Metrics Dashboard**: Compression ratios and quality metrics
- **Query Console**: Run custom SQL queries

## 9. Deploy Lambda Processor (Optional)

For automatic processing on S3 uploads:

```bash
# Package Lambda function
cd lambda_processor
zip -r handler.zip .
cd ..

# Update Lambda function code
aws lambda update-function-code \
  --function-name healthcare-waveform-processor \
  --zip-file fileb://lambda_processor/handler.zip
```

## Troubleshooting

### "NoCredentialsError" or "InvalidUser"
- Verify AWS credentials: `aws sts get-caller-identity`
- Ensure region is set: `export AWS_DEFAULT_REGION=us-east-1`

### CloudFormation Deployment Fails
- Check IAM permissions for CloudFormation, S3, DynamoDB, Lambda
- Verify bucket names don't already exist (S3 names are globally unique)
- Check CloudFormation events: `aws cloudformation describe-stack-events --stack-name healthcare-waveform-pipeline`

### "Model file not found"
- Ensure autoencoder model `.h5` file is in current directory or specify full path
- Model should match the data preprocessing used (normalization, shape)

### Athena Queries Timeout
- Check S3 Athena results bucket exists and is readable
- Verify Glue catalog database is created
- Run simpler queries first (e.g., `SELECT COUNT(*) FROM processed_waveforms`)

### Lambda Execution Fails
- Check CloudWatch logs: `aws logs tail /aws/lambda/healthcare-waveform-processor --follow`
- Verify IAM role has S3, DynamoDB, ECR permissions
- Check function timeout and memory settings

## Next Steps

1. **Monitor Costs**: Check AWS Cost Explorer for S3 storage and Lambda execution costs
2. **Optimize Models**: Fine-tune autoencoder on your specific MIMIC subset
3. **Integrate Data Pipeline**: Connect to your existing healthcare workflows
4. **Scale Processing**: Use Lambda scheduled rules or Glue jobs for batch processing
5. **Set Alerts**: Configure CloudWatch alarms for pipeline failures

## File Structure

```
.
├── aws/
│   └── cloudformation.yaml      # AWS infrastructure template
├── dashboard/
│   ├── app.py                   # Streamlit dashboard
│   └── requirements.txt          # Dashboard dependencies
├── lambda_processor/
│   ├── handler.py               # Lambda function code
│   └── requirements.txt          # Lambda dependencies
├── aws_config.py                # Central configuration
├── aws_upload_waveforms.py      # Data ingestion CLI
├── aws_process_pipeline.py      # Autoencoder processing
├── aws_query.py                 # Query interface
├── README.md                    # Project overview
├── SETUP.md                     # This file
└── requirements.txt             # Main dependencies
```

## Support & Resources

- **AWS Documentation**: https://docs.aws.amazon.com/
- **MIMIC-IV Data**: https://physionet.org/content/mimiciv/
- **TensorFlow/Keras**: https://www.tensorflow.org/
- **Streamlit**: https://docs.streamlit.io/

---

**Last Updated**: March 2026
