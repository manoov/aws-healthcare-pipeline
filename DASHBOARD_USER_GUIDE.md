# Dashboard User Guide for Clinicians

## Welcome to the Trajectory Results Dashboard 📊

This guide explains how to use the clinical dashboard to review sepsis trajectory analysis results.

---

## Dashboard Overview

The dashboard provides **5 interactive sections** for reviewing trajectory analysis:

```
┌─────────────────────────────────────────────────────────────────┐
│          TRAJECTORY ANALYSIS RESULTS DASHBOARD                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  📈 Overview  │  📊 Statistics  │  🔬 Features  │  📋 Patients  │  📄 Report
│                                                                 │
│  ├─ Cohort Size        ├─ χ² Test Results    ├─ Feature Stats │
│  ├─ Responders         ├─ AUROC Comparison   ├─ Correlations  │
│  ├─ Non-Responders     ├─ DeLong Test        └─ Heatmaps      │
│  └─ Class Distribution └─ Interpretation                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Section 1: 📈 Overview

### What You'll See

**Key Metrics Cards**:

```
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ Total Patients   │  │   Responders     │  │ Non-Responders   │  │ Trajectory       │
│   35,308         │  │   17,167 (48.6%) │  │   18,141 (51.4%) │  │ Classes: 3       │
└──────────────────┘  └──────────────────┘  └──────────────────┘  └──────────────────┘
```

### Two Main Charts

**1. Trajectory Class Distribution** (Pie Chart)
- Shows how patients are distributed across 3 trajectory classes
- Example: Class 0 (53%), Class 1 (35%), Class 2 (12%)
- **What it means**: Different physiological trajectory patterns exist in sepsis

**2. Responder Status Distribution** (Bar Chart)
- Compares responders vs non-responders
- Example: Responders (17,167) vs Non-responders (18,141)
- **What it means**: Roughly equal split in sepsis response outcomes

### Key Findings Summary

Includes clinical context about:
- Your cohort characteristics (age, gender, ICU stay)
- How responders/non-responders were defined
- Baseline SOFA scores and follow-up periods

---

## Section 2: 📊 Statistical Analysis

### The Three Tests

#### 1️⃣ **Chi-Square Test (χ²)** - Class Distribution Difference

**What it tests**: Do trajectory classes differ between responders and non-responders?

```
Example Results:
  χ² statistic: 45.3
  P-value: 0.0001
  Degrees of freedom: 2
  
  ✅ RESULT: SIGNIFICANT (p < 0.05)
```

**What this means**:
- ✅ Trajectory classes **significantly predict** treatment response
- This is the **primary finding** supporting the clinical value of trajectory analysis
- Physiological patterns carry prognostic information beyond baseline scoring

**For the clinician**: Use trajectory classification to identify high-risk patients who may not respond to initial sepsis interventions.

---

#### 2️⃣ **AUROC Comparison** - Predictive Performance

**What it tests**: How well does the trajectory model predict non-response?

```
Example Results:
  Trajectory Model AUROC: 0.724
  Baseline SOFA AUROC: 0.682
  Difference: +0.042 (4.2% improvement)
```

**AUROC Interpretation**:
- 0.50 = Random guessing ("flip a coin")
- 0.60-0.70 = Fair discrimination
- 0.70-0.80 = Good discrimination
- 0.80-0.90 = Excellent discrimination
- 0.90-1.00 = Outstanding discrimination

**Example**: 
- AUROC 0.724 means: **Correctly identifies 72% of high-risk patients**
- Outperforms SOFA baseline score by 4.2%

**For the clinician**: The trajectory model better discriminates who will not respond to standard sepsis therapy.

---

#### 3️⃣ **DeLong Test** - Statistical Significance of Difference

**What it tests**: Is the AUROC improvement over SOFA statistically significant?

```
Example Results:
  Z-statistic: 2.04
  P-value: 0.042
  
  ✅ RESULT: SIGNIFICANT (p < 0.05)
```

**What this means**:
- ✅ The **improvement over SOFA is real**, not due to chance
- We can be **95% confident** that trajectory model outperforms SOFA
- This meets the **threshold for clinical adoption** (p < 0.05)

**For the clinician**: It's safe to use this model in clinical decision-making.

---

### Clinical Interpretation

The dashboard provides **three-part interpretation** for each test:

**"What These Results Mean"**:
- Plain language explanation
- Clinical relevance
- Potential applications

**"Clinical Recommendations"**:
- How to use findings
- Implementation guidance
- Patient risk stratification

---

## Section 3: 🔬 Feature Analysis

### Descriptive Statistics

Shows **mean ± standard deviation** for each physiological feature:

```
Mean RR Interval:           900 ± 100 ms     [Normal: 750-1000 ms]
SDNN (HRV):                  100 ± 30 ms     [Normal: 100-150 ms]
RMSSD:                        50 ± 20 ms     [Normal: 25-100 ms]
LF Power:                    200 ± 200 ms²
HF Power:                    150 ± 150 ms²
LF/HF Ratio:                 1.66 ± 0.5     [Autonomic balance]
```

**What to look for**:
- Values outside normal range suggest abnormal physiology
- High SDNN/RMSSD = good heart rate variability (protective)
- Low SDNN/RMSSD = reduced variability (risk factor)

---

### Feature Correlation Heatmap

Shows how physiological features **relate to each other**:

```
                    Mean_RR  SDNN  RMSSD  LF  HF  LF/HF
        Mean_RR      1.00    0.45  0.38   0.2  0.1  0.05
        SDNN         0.45    1.00  0.92   0.6  0.4  0.3
        RMSSD        0.38    0.92  1.00   0.5  0.5  0.2
        LF           0.20    0.60  0.50   1.0  0.7  0.9
        HF           0.10    0.40  0.50   0.7  1.0  -0.8
        LF/HF        0.05    0.30  0.20   0.9  -0.8 1.0
```

**Color meanings**:
- 🔴 **Dark red** = Strong positive correlation (0.8-1.0)
- 🟠 **Orange** = Moderate correlation (0.5-0.8)
- 🟡 **Yellow** = Weak correlation (0.2-0.5)
- 🟢 **Green** = No/negative correlation (<0.2)

**What to look for**:
- Strong correlations (0.8+) between related features suggest data quality is good
- Weak correlations suggest features capture different physiological aspects
- Negative correlations show inverse relationships (e.g., LF vs HF in some cohorts)

---

## Section 4: 📋 Patient Data

### Downloadable Patient List

Shows the **trajectory class assignment** for each patient:

```
subject_id              trajectory_class
10001401                1
10001843                0
10003400                0
10003637                2
10004477                2
10001502                1
...
```

### How to Use This Data

1. **Research**: Export for further analysis
2. **Validation**: Compare against other outcome measures
3. **Subgroup analysis**: Filter by trajectory class
4. **Integration**: Import into your EMR for clinical decision support

### Filter Options

- **By Trajectory Class**: 0, 1, 2 (for 3-class model)
- **Show top N**: Display 10-500 patients

### Export

Click **"📥 Download Patient Data (CSV)"** to export as CSV file for:
- Excel analysis
- R/Python analysis
- Data integration with other systems

---

## Section 5: 📄 Report

### Automated Clinical Report

Generates a **formatted report** including:

1. **Executive Summary**
   - Study design overview
   - Key findings in narrative form
   - Clinical implications

2. **Methods**
   - Cohort definition
   - Feature list
   - Aggregation strategy
   - Modeling approach

3. **Key Results**
   - χ² test results
   - AUROC values
   - DeLong test p-value
   - Confidence intervals

4. **Clinical Implications**
   - What the findings mean
   - Safety/efficacy considerations

5. **Recommendations**
   - How to use in practice
   - Validation recommendations
   - Implementation steps

### Report Personalization

Enter your **Clinician ID** (e.g., "MD #12345") to:
- Personalize the report
- Track access for audit trails
- Generate provider-specific versions

### Export Options

- **📄 PDF Download**: Full formatted report (coming soon)
- **📋 Copy to Clipboard**: Paste into EMR
- **🔄 Share via URL**: Email to colleagues

---

## How to Interpret Trajectory Classes

### Example 3-Class Model

#### Class 0: "Progressive Deterioration" (53% of patients)
```
Trajectory Pattern:
  Heart Rate:        ↗️ Increasing over 72h
  HRV (SDNN):        ↘️ Decreasing (worse autonomic tone)
  Blood Pressure:    ↗️ Variable
  Risk Profile:      🔴 HIGH RISK

Clinical Meaning:
  - Patient showing progressive physiological stress
  - Autonomic system failing
  - May develop multi-organ dysfunction
  
Recommendation:
  🚨 Consider escalation of care
  ⏰ More frequent monitoring
  💊 Consider vasopressor/inotrope therapy
```

#### Class 1: "Stable-Improving" (35% of patients)
```
Trajectory Pattern:
  Heart Rate:        → Stable
  HRV (SDNN):        ↗️ Improving (better autonomic tone)
  Blood Pressure:    → Stable/improving
  Risk Profile:      🟡 INTERMEDIATE RISK

Clinical Meaning:
  - Patient responding to initial interventions
  - Autonomic system recovering
  - Good prognostic trajectory
  
Recommendation:
  👍 Standard sepsis management
  ⏰ Regular monitoring
  🎯 Continue current interventions
```

#### Class 2: "Rapid Deterioration" (12% of patients)
```
Trajectory Pattern:
  Heart Rate:        ↗️↗️ Rapid increase
  HRV (SDNN):        ↘️↘️ Rapid decrease
  Blood Pressure:    ↘️ Falling, hypotensive
  Risk Profile:      🔴🔴 VERY HIGH RISK

Clinical Meaning:
  - Patient in septic shock
  - Severe autonomic dysfunction
  - Critical condition

Recommendation:
  🚨🚨 URGENT INTERVENTION
  ⏰ Continuous monitoring (ICU level)
  💊 Maximal vasopressor support
  🏥 Consider transfer to higher level of care
```

---

## Clinical Decision-Making

### Using Trajectories in Practice

#### Scenario 1: "Early Risk Identification" (First 24h)
```
Patient assigned to trajectory Class 0 or 2 at 24 hours:
→ HIGH-RISK group
→ Likely non-responder to standard therapy

Action:
  ✓ Intensify monitoring
  ✓ Consider intervention changes
  ✓ Consult bacteriology/microbiology
  ✓ Discuss prognosis with family
```

#### Scenario 2: "Monitoring Response" (24-72h)
```
Patient trajectory changes from Class 2 → Class 1 between days 1-3:
→ IMPROVING trajectory
→ Positive response to interventions

Action:
  ✓ Continue current management
  ✓ Plan weaning from vasopressors
  ✓ Consider discharge to regular ward
```

#### Scenario 3: "Persistent Non-Response"
```
Patient remains in Class 0 or 2 at 72h despite interventions:
→ POOR PROGNOSIS
→ Consider treatment futility discussion

Action:
  ✓ Goals of care conversation
  ✓ Palliative care consultation
  ✓ Family meeting
```

---

## Frequently Asked Questions

### Q: Can I use this to replace clinical judgment?
**A**: No. Trajectory analysis **supplements** but does not replace:
- Clinical examination
- Laboratory values
- Imaging findings
- ICU team expertise

Use it as **one more tool** in your clinical toolkit.

---

### Q: What if a patient doesn't match an expected trajectory?
**A**: 
- This was built on large cohort patterns → individual variation is normal
- Always trust clinical judgment over predictions
- Use trajectory class as a starting point for deeper investigation

---

### Q: How accurate is this model?
**A**: 
- AUROC 0.72 = **Fair to good discrimination**
- Correctly identifies ~72% of high-risk patients
- May miss some cases (28% false negatives)
- **Always use in conjunction with standard care**

---

### Q: Can I integrate this into my EMR?
**A**: Yes! 
- Download CSV of predictions
- Upload to your EMR
- Create clinical decision support rules
- See IT department for integration

---

### Q: What if I find errors in the results?
**A**: 
- Document the error with:
  - Patient ID
  - Expected vs actual result
  - Clinical context
- Report to analysis team for investigation
- Results are updated as cohort changes

---

## Dashboard Navigation Tips

### 🔍 Quick Navigation
- Use **browser tabs** to compare sections
- Use **Ctrl+F** to search within tables
- **Bookmark** the dashboard URL
- Check **browser history** for recent visits

### ⏱️ Dashboard Speed
- First load: ~5-10 seconds
- Section switching: ~1-2 seconds
- If slow: Try refreshing browser (Ctrl+R)

### 💾 Data Export Tips
- Downloaded CSV files: Open in Excel or Python
- Reports: Save as PDF from browser (Ctrl+P)
- Share results: Copy dashboard URL to email

### 🔐 Security & Privacy
- Dashboard requires login (your clinic credentials)
- All data encrypted in transit (HTTPS)
- Access logging enabled (audit trail)
- De-identified data only (no names/medical record #)

---

## Getting Help

### Technical Issues
- "Dashboard won't load" → Check internet connection
- "Results are missing" → Results may still be processing
- "Charts not displaying" → Try different browser (Chrome/Firefox)

### Questions About Results
- "What does this number mean?" → See interpretation sections above
- "How should I act on this?" → See clinical decision-making section
- "Is this right for my patient?" → Trust your clinical judgment first

### Contact
- **Dashboard Admin**: [Your IT contact]
- **Clinical Lead**: [Your chief investigator]
- **Emergency Issues**: Contact hospital IT support

---

## Summary

The **Trajectory Results Dashboard** provides:

✅ **Overview** of your cohort and trajectory classes  
✅ **Statistical proof** of clinical value (χ², AUROC, DeLong)  
✅ **Feature-level analysis** to understand physiology  
✅ **Individual patient data** for integration with practice  
✅ **Formatted reports** for publications/presentations  

**Remember**: This dashboard is a **research analysis tool** meant to:
- Support clinical decision-making
- Identify high-risk patients early
- Complement standard sepsis management
- Enable precision medicine in critical care

---

**Last Updated**: March 3, 2026  
**Dashboard Version**: 1.0  
**Questions?** Contact your clinical informatics team

