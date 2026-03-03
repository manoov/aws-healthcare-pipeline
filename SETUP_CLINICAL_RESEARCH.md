# Clinical Research Platform - Complete Setup Guide

End-to-end setup for **Group-Based Trajectory Modeling and Sepsis Response Prediction** using MIMIC-IV data.

## Prerequisites

- **Python 3.9+** on Linux/Mac (Windows: WSL2)
- **MIMIC-IV Access**: Approved physionet.org account
- **~50 GB disk**: For hosp (~2 GB) + waveforms (>40 GB, optional)
- **Git, wget**: For downloading

### Optional (Cloud Deployment)
- **AWS Account** + AWS CLI configured

## Quick Start (5-10 minutes)

### Step 1: Clone & Setup

```bash
git clone https://github.com/manoov/aws-healthcare-pipeline.git
cd aws-healthcare-pipeline

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 2: Verify MIMIC Data

```bash
# Ensure data is downloaded
ls /data/physionet.org/files/mimiciv/3.1/hosp/
# Expected output:
# admissions.csv.gz
# diagnoses_icd.csv.gz
# labevents.csv.gz
# ... (10+ files, ~2 GB total)
```

### Step 3: Run End-to-End Pipeline

```bash
# Extract features & fit trajectory model (structured data only)
python examples_feature_extraction.py \
  --mimic-root /data/physionet.org/files/mimiciv/3.1 \
  --skip-waveforms \
  --n-classes 3 \
  --output-dir ./manuscript_results

# ✓ Creates:
# - manuscript_results/summary_stats.txt (Table 1)
# - manuscript_results/feature_correlations.csv
# - manuscript_results/trajectory_assignments.csv
```

## Detailed Setup

### Download MIMIC-IV Data

⚠️ **Requires PhysioNet credentialed access**. [Apply here](https://physionet.org/settings/sessions/) (48-72 hour approval)

```bash
# Create data directory
mkdir -p /data
cd /data

# Download hospital module (CSV.gz, ~2 GB, ~5-10 minutes)
wget -r -N -c -np \
  --user <YOUR_PHYSIONET_USERNAME> \
  --ask-password \
  https://physionet.org/files/mimiciv/3.1/hosp/

# Optional: Download waveforms (>40 GB, ~1-2 days)
# Run in separate terminal window
wget -r -N -c -np \
  --user <YOUR_PHYSIONET_USERNAME> \
  --ask-password \
  https://physionet.org/files/mimiciv/3.1/icu/waveforms/
```

**Download structure:**
```
/data/physionet.org/files/mimiciv/3.1/
├── hosp/
│   ├── admissions.csv.gz (76K admissions)
│   ├── labevents.csv.gz (63M lab events)
│   ├── diagnoses_icd.csv.gz (ICD-10 codes)
│   └── [9 more files]
├── icu/
│   ├── waveforms/ (optional, 61K+ patient-stay records)
│   └── ...
└── CHANGELOG.txt
```

### Verify Installation

```bash
# Test imports
python -c "
from data_ingestion import MIMICLoader, CohortBuilder
from data_ingestion.feature_extractor import HRVFeatureExtractor
print('✓ All imports successful')
"

# Check data access
python -c "
from data_ingestion import MIMICLoader
loader = MIMICLoader('/data/physionet.org/files/mimiciv/3.1')
admissions = loader.load_admissions()
print(f'✓ Loaded {len(admissions)} admissions')
"
```

## Running the Pipeline

### Scenario A: Structured Data Only (No Waveforms)

```bash
python examples_feature_extraction.py \
  --mimic-root /data/physionet.org/files/mimiciv/3.1 \
  --skip-waveforms \
  --n-classes 3 \
  --output-dir ./results_structured

# Runtime: ~5-10 minutes
# Uses: Lab values, diagnoses, demographics
```

### Scenario B: With Continuous Waveforms

```bash
python examples_feature_extraction.py \
  --mimic-root /data/physionet.org/files/mimiciv/3.1 \
  --waveform-root /data/physionet.org/files/mimiciv/3.1/icu/waveforms \
  --n-classes 3 \
  --output-dir ./results_full

# Runtime: ~1-2 hours (first time)
# Extracts HRV, BP variability, PPG features
```

### Output Files Explained

```
results_*/
├── summary_stats.txt
│   └── Cohort size, demographics, SOFA scores  [→ Table 1 for manuscript]
│
├── feature_correlations.csv
│   └── Pearson correlations between all features [→ Supplementary Table]
│
├── trajectory_assignments.csv
│   └── subject_id,trajectory_class
│       ├── Class 0: "Stable responders" (high baseline HR, recovers)
│       ├── Class 1: "Progressive deteriorators" (low baseline, worsens)
│       └── Class 2: "Volatile pattern" (high variance)
│
└── roi_analysis.csv
    └── AUROC, sensitivity, specificity, AIC, BIC
```

## Understanding Output: Trajectory Classes

### Example Classification

Suppose you have 2,500 sepsis patients (50% responder/non-responder), and fit 3 classes:

```
Trajectory Class Assignment:
├─ Class 0 (40% of cohort):  "Stable" 
│  ├─ Mean HR: 95±15 bpm, stays stable
│  ├─ Responders: 65% 
│  ├─ Non-responders: 35%
│  └─ Interpretation: Good prognosis
│
├─ Class 1 (35% of cohort):  "Progressive"
│  ├─ Mean HR: 110±25 bpm, worsening over 72h
│  ├─ Responders: 30%
│  ├─ Non-responders: 70%
│  └─ Interpretation: Poor prognosis → intensive intervention
│
└─ Class 2 (25% of cohort):  "Volatile"   
   ├─ Mean HR: 100±35 bpm, high variability
   ├─ Responders: 45%
   ├─ Non-responders: 55%
   └─ Interpretation: Unclear trajectory
```

**Statistical Test:** χ² = 245, p < 0.001 → Classes differ significantly between responders/non-responders

## Feature Categories Extracted

### From ECG → HRV
| Feature | Calculation | Clinical Meaning |
|---------|-----------|-------------------|
| Mean RR | Avg inter-beat interval (ms) | Baseline heart rate |
| SDNN | Std of RR intervals | Overall HR variability |
| RMSSD | Root mean square of RR differences | Parasympathetic tone |  
| pNN50 | % of consecutive RR > 50ms diff | Vagal activity |
| LF Power | 0.04-0.15 Hz spectral power | Sympathetic + parasympathetic |
| HF Power | 0.15-0.4 Hz spectral power | Parasympathetic (vagal) |
| LF/HF Ratio | Sympathetic-parasympathetic balance | Autonomic tone |

### From ABP → Variability
| Feature | Meaning |
|---------|---------|
| Systolic SD | Systolic pressure variability |
| Diastolic SD | Diastolic pressure variability |
| Pulse Pressure (PP) | Systolic - Diastolic |
| PP Variation | Breath-to-breath PP change (mechanically ventilated) |
| MAP | (Systolic + 2×Diastolic) / 3 |
| dP/dt | Rate of systolic pressure rise (contractility) |

### From PPG → Perfusion
| Feature | Meaning |
|---------|---------|
| Perfusion Index | AC/DC amplitude ratio (peripheral perfusion) |
| Skewness | Waveform asymmetry |
| Kurtosis | Sharpness of pulse peak |
| Pulse Transit Time | ECG R-wave → PPG pulse delay |

### Aggregation Statistics
For each feature, compute:
- **mean**: Average over 72-hour window
- **median**: Central tendency
- **sd**: Variability
- **slope**: Linear trend over 72h (increases = worsening?decreasing = improving?)
- **cv**: Coefficient of variation = sd/mean (normalized variability)

**Result: ~50 patient-level features for trajectory modeling**

## Statistical Analysis for Publication

### AUROC Comparison (DeLong Test)

Your model's prediction vs. baseline SOFA:

```python
from data_ingestion.cohort_builder import BaselineComparison
from sklearn.metrics import roc_auc_score, roc_curve

# Trajectory model: probability of non-response = class membership
auroc_traj = roc_auc_score(outcomes_binary, trajectory_probs)
# e.g., 0.78 (95% CI: 0.75-0.81)

# Baseline: SOFA score (higher = worse prognosis)
auroc_sofa = roc_auc_score(outcomes_binary, baseline_sofa)
# e.g., 0.72 (95% CI: 0.69-0.75)

# DeLong test: is the difference significant?
z, pval = BaselineComparison.delong_test(
    auc_traj, se_traj, 
    auc_sofa, se_sofa, 
    n_samples=2500
)
# If pval < 0.05, trajectory model is significantly better
```

### Publication Table Template

```markdown
Table 1: Clinical Characteristics of Sepsis Cohort by Response

                          Total       Responders  Non-Responders  P-Value
                          (n=2547)    (n=1234)    (n=1313)
                          
Age (years)               67±15       66±14       68±16           0.12
Male (%)                  1569 (62)   760 (62)    809 (62)        0.89

ICU LOS (days)            4.8±2.5     3.2±1.8     6.2±3.1        <0.001

Baseline SOFA             8.2±2.9     7.5±2.5     8.9±3.2        <0.001
SOFA at 48h               5.8±3.1     4.1±2.3*    7.8±2.6         <0.001
SOFA improvement          2.4±3.5     3.4±2.1     1.1±2.1        <0.001

Mechanical ventilation    1698 (67)   789 (64)    909 (69)        0.02
Vasopressor use           1201 (47)   479 (39)    722 (55)       <0.001

---

Table 2: Model Performance Comparison

                          AUROC        95% CI         Sensitivity  Specificity
Trajectory Model (3-class) 0.78         0.75-0.81     0.72         0.71
Baseline SOFA Score       0.72         0.69-0.75     0.65         0.71
DeLong Test p-value       0.0023 †
```

## AWS Optional: Cloud Deployment

For handling large-scale multi-site data:

```bash
# Deploy infrastructure
aws cloudformation deploy \
  --template-file aws/cloudformation.yaml \
  --stack-name healthcare-trajectory-pipeline

# Upload processed features (not raw waveforms - data privacy!)
python aws_upload_waveforms.py \
  --wfdb-root ./trajectory_results_full \
  --max-records 5000

# Query via Athena
python aws_query.py \
  --type athena \
  --query "SELECT trajectory_class, COUNT(*) FROM features GROUP BY trajectory_class"
```

## Troubleshooting

### "No module named 'data_ingestion'"

```bash
# Ensure you're in repo root
pwd  # Should end with: aws-healthcare-pipeline

# Add current dir to Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
python examples_feature_extraction.py ...
```

### "MIMIC file not found" Error

```bash
# Check exact path
ls /data/physionet.org/files/mimiciv/3.1/hosp/ | head -5

# Update script if path differs
python examples_feature_extraction.py \
  --mimic-root /YOUR/ACTUAL/PATH/mimiciv/3.1
```

### Slow First Run

- First execution: Decompresses MIMIC CSVs (gz → csv in memory)
- Takes ~30-60 seconds, then caches results
- Subsequent runs: <5 seconds per file

## Next Steps → Publication

1. **Run full pipeline** with n_classes = 3, 4, 5
2. **Select optimal** based on BIC/entropy/interpretability
3. **Generate figures**:
   - Trajectory plots (mean feature per class over time)
   - ROC curves (trajectory vs baseline SOFA)
   - Heatmaps (feature importance by class)
4. **Write manuscript** (target journals: *Chest*, *Critical Care Medicine*, *Intensive Care Med*)
5. **Register** on OSF Registries for preregistration

## References

### GBTM Methodology
- Nagin, D.S. Group-Based Trajectory Modeling. *Harvard University Press* (2005).
- Muthen et al. Latent class growth modeling. *Sociological Methods & Research* (2000).

### Clinical Application
- Shankar-Hari et al. Developing the Third International Consensus Definitions for Sepsis and Septic Shock (2016).
- Knaus et al. APACHE: A physiologically based classification system. *Critical Care Medicine* (1985).

### Data Source
- Goldberger et al. PhysioBank, PhysioToolkit. *Circulation* (2000).
- MIMIC-IV Documentation: https://mimic.mit.edu/

## Support

- Issues: Create GitHub issues with reproduction steps
- Collaboration: Contact [your email] for multi-site studies
- Questions: See FAQ in data_ingestion/README.md
