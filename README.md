# AWS Healthcare Critical Care Research Platform

**Clinical Research Focus**: Group-Based Trajectory Modeling for Predicting Sepsis Non-Response in ICU Patients

AWS-powered platform combining structured data (MIMIC-IV hosp module) with continuous physiological waveforms to extract trajectory-level features for predicting patient response to critical care interventions.

## Clinical Objectives

### Objective 1: Trajectory Modeling
Identify 3-5 distinct trajectory patterns for key clinical features (HR, HRV, BP, perfusion) over 72-hour ICU stay using Group-Based Trajectory Modeling (GBTM). Compare trajectory class distributions between responders (SOFA↓ ≥2) and non-responders, computing AUROC and comparing with baseline SOFA via DeLong test.

### Data Flow

```
MIMIC-IV Hosp Data         Continuous Waveforms (ECG, ABP, PPG, Respiratory)
       ↓                                    ↓
[Cohort Definition]        [Feature Extraction: 5-min windows, quality control]
       ↓                                    ↓
[Patient Filtering]        [HRV (time + freq domain), BP variability, morphology]
       ↓                                    ↓
[Outcome Labels]           [Aggregate: mean, median, SD, slope, CV (30-50 features/patient)]
       ↓                                    ↓
[Integration] ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ←
       ↓
[Trajectory Modeling: GBTM / scikit-learn LCA]
       ↓
[Statistical Comparison: χ², AUROC, DeLong test]
```

## Key Features

### Data Processing
- **Cohort Definition**: Load MIMIC-IV demographics, diagnoses, ICU admissions; filter by sepsis, organ dysfunction indicators
- **Waveform Quality Assessment**: Auto-reject artefact-laden windows, validate signal integrity
- **Feature Extraction**: Compute 30-50 trajectory-level features per patient

### Physiological Features Extracted

| Category | Features | Clinical Relevance |
|----------|----------|-------------------|
| **HRV (ECG)** | Mean RR, SDNN, RMSSD, pNN50, LF, HF, LF/HF ratio | Autonomic function, sepsis severity |
| **BP Variability** | Systolic/diastolic SD, PP variation (PPV), dP/dt | Vascular tone, contractility |
| **Morphology** | QRS width, QT interval, T-wave amplitude, dicrotic notch | Conduction, repolarization |
| **Perfusion** | PPG perfusion index, skewness/kurtosis, pulse transit time (PTT) | Peripheral perfusion, vascular stiffness |

### Trajectory Modeling
- **GBTM**: Identify distinct patient trajectory classes (3-5 groups)
- **Class Comparison**: χ² test for responder/non-responder distribution
- **Prediction**: AUROC for trajectory class membership vs non-response
- **Baseline Comparison**: DeLong test vs baseline SOFA score

## Quick Start

### 1. Prerequisites

```bash
# Python 3.9+
python --version

# Install core dependencies
pip install -r requirements.txt

# Additional for feature extraction:
pip install wfdb scipy scikit-learn
```

### 2. Prepare Data

```bash
# Expected structure:
# /data/physionet.org/files/mimiciv/3.1/
#   ├── hosp/          # MIMIC-IV hospital records (already downloaded)
#   └── icu/waveforms/ # Download waveforms (ongoing)

# Check downloaded data
ls -lh /data/physionet.org/files/mimiciv/3.1/hosp/
```

### 3. Build Sepsis Cohort & Extract Features

```bash
python examples_feature_extraction.py \
  --mimic-root /data/physionet.org/files/mimiciv/3.1 \
  --waveform-root /data/physionet.org/files/mimiciv/3.1/icu/waveforms \
  --n-classes 3 \
  --output-dir ./results

# Without waveforms (use structured data only):
python examples_feature_extraction.py \
  --mimic-root /data/physionet.org/files/mimiciv/3.1 \
  --skip-waveforms \
  --output-dir ./results
```

### 4. Trajectory Modeling & Publication Results

```
Results:
✓ results/summary_stats.txt          # Table 1: Cohort demographics
✓ results/feature_correlations.csv   # Feature inter-correlations
✓ results/trajectory_assignments.csv # Patient → class mapping
```

## Project Structure

```
├── data_ingestion/                  # Clinical data processing pipeline
│   ├── __init__.py
│   ├── mimic_loader.py              # MIMIC-IV hospital data loading
│   ├── cohort_builder.py            # Cohort definition, GBTM, DeLong test
│   ├── waveform_loader.py           # ECG/ABP/PPG waveform loading + quality control
│   ├── feature_extractor.py         # HRV, BP variability, morphology features
│   └── utils.py                     # Data preprocessing, standardization, deidentification
│
├── aws/                             # AWS Infrastructure (optional)
│   └── cloudformation.yaml          # S3, DynamoDB, Lambda, Athena setup
│
├── dashboard/                       # Streamlit visualization (optional)
│   ├── app.py                       # Interactive dashboard
│   └── requirements.txt
│
├── lambda_processor/                # AWS Lambda function (optional)
│   ├── handler.py
│   └── requirements.txt
│
├── examples_feature_extraction.py   # Full end-to-end example
├── aws_config.py                    # AWS configuration
├── aws_upload_waveforms.py          # S3 data upload
├── aws_process_pipeline.py          # Waveform autoencoder processing
├── aws_query.py                     # Athena/DynamoDB queries
├── requirements.txt                 # Dependencies
└── README.md                        # This file
```

## Data Ingestion Module API

### MIMICLoader
```python
from data_ingestion import MIMICLoader

loader = MIMICLoader('/data/physionet.org/files/mimiciv/3.1')

# Load hospital data
admissions = loader.load_admissions()
labs = loader.load_labevents()
diagnoses = loader.load_diagnoses()

# Get ICU admissions with sepsis
cohort = loader.filter_cohort(require_sepsis=True)
```

### CohortBuilder
```python
from data_ingestion import CohortBuilder

builder = CohortBuilder(mimic_loader)
cohort = builder.define_sepsis_cohort()
builder.add_outcome_labels(sofa_baseline_col='sofa_0h', sofa_followup_col='sofa_48h')

# Responder definition: SOFA improvement ≥2 points in 48h
print(cohort['response'].value_counts())
```

### WaveformLoader
```python
from data_ingestion import WaveformLoader

wf_loader = WaveformLoader('/data/physionet.org/files/mimiciv/3.1/icu/waveforms')

# Load ECG signal
ecg, sr, metadata = wf_loader.load_wfdb_record('p103/p103234/p103234-2110-04-12')

# Segment into 5-minute windows
windows = wf_loader.segment_into_windows(
    ecg, sr, window_minutes=5, assess_quality=True
)

# Only use high-quality windows
valid_windows = [w for w in windows if w['quality']['is_valid']]
```

### FeatureExtractor (HRV example)
```python
from data_ingestion.feature_extractor import HRVFeatureExtractor

# Extract RR intervals
rr_intervals = HRVFeatureExtractor.extract_rr_intervals(ecg_signal, sampling_rate=250)

# Time-domain HRV
td_hrv = HRVFeatureExtractor.time_domain_hrv(rr_intervals)
print(f"Mean HR: {td_hrv['mean_hr']:.1f} bpm")
print(f"SDNN: {td_hrv['sdnn']:.1f} ms")
print(f"RMSSD: {td_hrv['rmssd']:.1f} ms")

# Frequency-domain HRV
fd_hrv = HRVFeatureExtractor.frequency_domain_hrv(rr_intervals)
print(f"LF/HF ratio: {fd_hrv['lf_hf_ratio']:.2f}")
```

### Trajectory Modeling
```python
from data_ingestion.cohort_builder import TrajectoryModeler

# Fit GBTM model
modeler = TrajectoryModeler(n_classes=3)
modeler.fit_sklearn_mixture(feature_matrix)

# Compare trajectory distribution between responders/non-responders
comparison = modeler.trajectory_comparison(responder_ids, nonresponder_ids)
print(f"χ² test p-value: {comparison['pvalue']:.4f}")

# AUROC for trajectory class predicting non-response
roc = modeler.roc_analysis(trajectory_class=1, outcomes=binary_outcomes)
print(f"AUROC: {roc['auroc']:.3f}")
```

## Expected Output (Table 1 Format)

```
Cohort Demographics:
Total N: 2,547
Responders:    1,234 (48.5%)
Non-responders: 1,313 (51.5%)

Age (years):              67 ± 15
Male (%):                 62%

Baseline SOFA:            8 ± 3
SOFA at 48h (responders):  5 ± 2 *
SOFA at 48h (non-responders): 8 ± 4

Trajectory Classes:
├─ Class 0 (Stable):           45% responders, 20% non-responders (χ²=245, p<0.001)
├─ Class 1 (Progressive):      30% responders, 65% non-responders
└─ Class 2 (Volatile):         25% responders, 15% non-responders

Model Performance:
Trajectory AUROC:        0.78 (95% CI: 0.75-0.81)
Baseline SOFA AUROC:     0.72 (95% CI: 0.69-0.75)
DeLong Test (p-value):   0.0023 *
```

## Key Citations & Methods

- **GBTM**: Nagin, D.S. (2005). Group-Based Trajectory Modeling. *Harvard University Press*
  - Implemented via: `scikit-learn` GaussianMixture + `lcmm` (R interface available)
  
- **HRV Standards**: Task Force of the European Society of Cardiology (1996). *Circulation*
  - Time domain: SDNN, RMSSD, pNN50
  - Frequency domain: LF (0.04-0.15 Hz), HF (0.15-0.4 Hz), LF/HF ratio
  
- **Statistical Comparison**: DeLong et al. (1988). *Biometrics*
  - Non-parametric AUC comparison with SE calculation
  
- **Data**: MIMIC-IV v3.1 (Goldberger et al. 2003, Physionet)
  - 61,532 ICU admissions, 196,520 patients
  - Requires access application at physionet.org
