#!/bin/bash
# AWS Healthcare Pipeline - Quick Reference Commands
# Copy any command and paste into terminal

# ============================================================================
# ACTIVATION & SETUP
# ============================================================================

# Activate virtual environment
source .venv/bin/activate

# Run AWS setup (interactive credential configuration)
python setup_aws.py

# Verify AWS credentials work
aws sts get-caller-identity

# ============================================================================
# FEATURE EXTRACTION & ANALYSIS
# ============================================================================

# Run feature extraction (structured data only)
python examples_feature_extraction.py \
  --mimic-root ./mimic_data \
  --skip-waveforms \
  --output-dir ./results

# Run feature extraction with waveforms (when available)
python examples_feature_extraction.py \
  --mimic-root ./mimic_data \
  --waveform-root ./mimic_data/icu/waveforms \
  --output-dir ./results

# Test with small sample (for quick testing)
python examples_feature_extraction.py \
  --mimic-root ./mimic_data \
  --skip-waveforms \
  --output-dir ./results \
  --test-size 1000

# ============================================================================
# AWS DEPLOYMENT
# ============================================================================

# Deploy CloudFormation stack (create AWS resources)
aws cloudformation deploy \
  --template-file aws/cloudformation.yaml \
  --stack-name healthcare-waveform-pipeline \
  --capabilities CAPABILITY_IAM \
  --region us-east-1

# Check stack status
aws cloudformation describe-stacks \
  --stack-name healthcare-waveform-pipeline \
  --query 'Stacks[0].StackStatus'

# Get stack outputs (S3 bucket names, DynamoDB table, etc.)
aws cloudformation describe-stacks \
  --stack-name healthcare-waveform-pipeline \
  --query 'Stacks[0].Outputs'

# ============================================================================
# DATA MANAGEMENT
# ============================================================================

# Check MIMIC data structure
ls -lh ./mimic_data/hosp/

# Verify all required MIMIC files exist
python verify_mimic_data.py \
  --mimic-path ./mimic_data \
  --project-root .

# Upload raw waveforms to S3 (dry run - no actual upload)
python aws_upload_waveforms.py \
  --wfdb-root ./mimic_data/icu/waveforms \
  --dry-run

# Upload waveforms to S3 (with sample limit of 50 records)
python aws_upload_waveforms.py \
  --wfdb-root ./mimic_data/icu/waveforms \
  --max-records 50

# Upload all waveforms to S3
python aws_upload_waveforms.py \
  --wfdb-root ./mimic_data/icu/waveforms

# ============================================================================
# PROCESSING & QUERIES
# ============================================================================

# Query DynamoDB for specific patient
python aws_query.py --patient-id 10001401 --database

# List all records in DynamoDB
python aws_query.py --all-records

# Run SQL query via Athena
python aws_query.py --sql "SELECT COUNT(*) FROM processed_waveforms"

# Process waveforms with autoencoder (requires model file)
python aws_process_pipeline.py \
  --all-unprocessed \
  --model-path ecg_autoencoder_model_fast.h5 \
  --batch-size 10

# Process single record
python aws_process_pipeline.py \
  --record-id 10001401_01 \
  --model-path ecg_autoencoder_model_fast.h5

# ============================================================================
# DASHBOARD
# ============================================================================

# Launch Streamlit dashboard (opens at http://localhost:8501)
streamlit run dashboard/app.py

# ============================================================================
# TROUBLESHOOTING & MONITORING
# ============================================================================

# Check AWS configuration
aws configure list

# Verify Python environment
python --version
pip list | grep boto3

# Check Lambda function logs (if deployed)
aws logs tail /aws/lambda/healthcare-waveform-processor --follow

# View CloudFormation events
aws cloudformation describe-stack-events \
  --stack-name healthcare-waveform-pipeline \
  --query 'StackEvents[0:5]'

# ============================================================================
# USEFUL PATHS
# ============================================================================

# View current results
cat results/summary_stats.txt
head -20 results/trajectory_assignments.csv

# View configuration
cat aws_config.py

# View AWS credentials (DO NOT SHARE!)
cat .env
