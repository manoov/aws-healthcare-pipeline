# Enhancement Guide: Implementing Missing Clinical Features

## Overview
This guide provides step-by-step implementation instructions for the 3 main gaps identified in the clinical requirements analysis:

1. **Longitudinal Trajectory Modeling** (GBTM upgrade)
2. **Pulse Pressure Variation (PPV)** (mechanically ventilated patients)
3. **Pulse Transit Time (PTT)** (ECG-PPG synchronization)

---

## 1. LONGITUDINAL TRAJECTORY MODELING UPGRADE

### Current Problem
The existing implementation uses **static clustering** on aggregated features. The doctor requires **Group-Based Trajectory Modeling (GBTM)** which:
- Models feature trajectories **over time** (not just aggregates)
- Fits growth curves per trajectory class
- Optimizes number of classes via BIC/AIC/entropy

### Solution: Implement Longitudinal Mixed-Effects Modeling

#### Step 1: Install Required Libraries

```bash
pip install statsmodels  # For linear mixed-effects models
# OR for advanced features:
pip install scikit-learn scikit-optimize  # Bayesian optimization for K selection
```

#### Step 2: Create Enhanced Trajectory Modeler

File: `data_ingestion/trajectory_modeler_longitudinal.py`

```python
"""
Longitudinal Trajectory Modeling using Mixed-Effects Models

This module implements Group-Based Trajectory Modeling (GBTM) using
linear mixed-effects models to identify distinct patient trajectory patterns
over the 72-hour study period.
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple, List, Optional
from scipy.stats import chi2_contingency, norm
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
import warnings


class LongitudinalTrajectoryData:
    """Prepare data in person-time format for trajectory modeling."""
    
    @staticmethod
    def reshape_for_mixed_effects(
        patient_features_dict: Dict[int, List[Dict]],
        feature_name: str,
        max_days: int = 3
    ) -> pd.DataFrame:
        """
        Reshape window-based features into person-time format.
        
        Parameters
        ----------
        patient_features_dict : dict
            {subject_id: [window_dict_1, window_dict_2, ...]}
            Each window dict has 'feature_value' and 'time_hours'
        
        feature_name : str
            Which feature to extract (e.g., 'mean_rr', 'sdnn')
        
        max_days : int
            Truncate to this many days
        
        Returns
        -------
        pd.DataFrame
            Person-time format suitable for mixed-effects modeling
            Columns: subject_id, time_hours, feature_value
        """
        
        rows = []
        
        for subject_id, windows in patient_features_dict.items():
            for i, window_dict in enumerate(windows):
                
                # Skip if feature not present
                if feature_name not in window_dict:
                    continue
                
                # Calculate time from ICU admission
                time_hours = window_dict.get('time_hours', i * 5 / 60)  # Assume 5-min windows
                
                # Truncate to max study period
                if time_hours > max_days * 24:
                    continue
                
                value = window_dict[feature_name]
                
                # Skip invalid values
                if pd.isna(value) or not np.isfinite(value):
                    continue
                
                rows.append({
                    'subject_id': subject_id,
                    'time_hours': time_hours,
                    'time_days': time_hours / 24,
                    feature_name: value,
                })
        
        return pd.DataFrame(rows)


class TrajectoryParameterExtractor:
    """Extract trajectory parameters (intercept, slope) from mixed-effects models."""
    
    @staticmethod
    def fit_trajectory_model(
        df: pd.DataFrame,
        feature_name: str,
        use_quadratic: bool = False
    ) -> Dict[int, Dict]:
        """
        Fit linear (or quadratic) mixed-effects model.
        
        Model:
            feature_i(t) = (β0 + bi0) + (β1 + bi1)*time + ε
        
        Parameters
        ----------
        df : pd.DataFrame
            Person-time format data
        
        feature_name : str
            Feature being modeled
        
        use_quadratic : bool
            If True, add quadratic term: β2*time^2
        
        Returns
        -------
        dict
            {subject_id: {'intercept': ..., 'slope': ..., 'residual_sd': ...}}
        """
        
        try:
            import statsmodels.api as sm
            import statsmodels.formula.api as smf
        except ImportError:
            raise ImportError("pip install statsmodels")
        
        # Fit random intercept + random slope model
        if use_quadratic:
            formula = f"{feature_name} ~ time_hours + I(time_hours**2)"
        else:
            formula = f"{feature_name} ~ time_hours"
        
        # Random effects for subject
        try:
            model = smf.mixedlm(
                formula,
                df,
                groups=df['subject_id'],
                re_formula=f"~time_hours"  # Random slope
            )
            
            result = model.fit(method='powell')
            
        except Exception as e:
            warnings.warn(f"Mixed-effects fit failed ({e}), using fixed-effects only")
            # Fallback: fit separately per patient
            result = None
        
        # Extract random effects (trajectory parameters)
        trajectories = {}
        
        if result is not None:
            # Random effects per subject
            random_effects = result.random_effects
            
            for subject_id, effects in random_effects.items():
                # Estimate intercept & slope for this subject
                intercept = result.fe_params['Intercept'] + effects.get('Group', 0)
                slope = result.fe_params['time_hours'] + effects.get('time_hours', 0)
                
                trajectories[subject_id] = {
                    'intercept': intercept,
                    'slope': slope,
                }
        
        else:
            # Fallback: fit each patient separately
            for subject_id in df['subject_id'].unique():
                subject_data = df[df['subject_id'] == subject_id]
                
                if len(subject_data) < 2:
                    continue
                
                X = subject_data[['time_hours']].values
                y = subject_data[feature_name].values
                
                # Add intercept column
                X = np.column_stack([np.ones(len(X)), X])
                
                # Least squares
                try:
                    coeffs = np.linalg.lstsq(X, y, rcond=None)[0]
                    trajectories[subject_id] = {
                        'intercept': float(coeffs[0]),
                        'slope': float(coeffs[1]),
                    }
                except:
                    pass
        
        return trajectories


class LongitudinalTrajectoryModeler:
    """Implement Group-Based Trajectory Modeling (GBTM)."""
    
    def __init__(self, n_classes: int = 3, random_state: int = 42):
        """
        Parameters
        ----------
        n_classes : int
            Number of trajectory classes to identify
        random_state : int
            For reproducibility
        """
        self.n_classes = n_classes
        self.random_state = random_state
        self.scaler = StandardScaler()
        self.kmeans = None
        self.class_assignments = None
        self.trajectory_params = None  # (intercept, slope) for each patient
        
    def fit(
        self,
        patient_features_dict: Dict[int, List[Dict]],
        feature_names: List[str],
        use_quadratic: bool = False
    ) -> 'LongitudinalTrajectoryModeler':
        """
        Fit trajectory model on multiple features.
        
        Procedure:
        1. For each feature, fit mixed-effects model → (intercept, slope) per patient
        2. Stack all trajectory parameters → feature matrix
        3. Cluster on trajectory parameters using K-means
        4. Assign patients to trajectory classes
        
        Parameters
        ----------
        patient_features_dict : dict
            {subject_id: [window_dict_1, ...]}
        
        feature_names : list
            Which features to model as trajectories
        
        use_quadratic : bool
            Include quadratic time term
        
        Returns
        -------
        self
        """
        
        # Extract trajectory parameters for each feature
        all_trajectories = {}
        
        for feature_name in feature_names:
            print(f"Fitting trajectory model for {feature_name}...")
            
            # Prepare person-time data
            df = LongitudinalTrajectoryData.reshape_for_mixed_effects(
                patient_features_dict,
                feature_name
            )
            
            if len(df) < 10:
                warnings.warn(f"Insufficient data for {feature_name}, skipping")
                continue
            
            # Fit mixed-effects model
            trajectories = TrajectoryParameterExtractor.fit_trajectory_model(
                df,
                feature_name,
                use_quadratic=use_quadratic
            )
            
            all_trajectories[feature_name] = trajectories
        
        # Build feature matrix from trajectory parameters
        # Rows: patients, Columns: feature_intercept, feature_slope
        subject_ids = set()
        for feature_trajs in all_trajectories.values():
            subject_ids.update(feature_trajs.keys())
        
        subject_ids = sorted(list(subject_ids))
        
        trajectory_matrix = []
        valid_subject_ids = []
        
        for subject_id in subject_ids:
            row = []
            has_all_features = True
            
            for feature_name in feature_names:
                if subject_id not in all_trajectories[feature_name]:
                    has_all_features = False
                    break
                
                traj = all_trajectories[feature_name][subject_id]
                row.append(traj['intercept'])
                row.append(traj['slope'])
            
            if has_all_features:
                trajectory_matrix.append(row)
                valid_subject_ids.append(subject_id)
        
        if len(trajectory_matrix) < self.n_classes:
            raise ValueError(
                f"Only {len(trajectory_matrix)} patients with complete data, "
                f"but {self.n_classes} classes requested"
            )
        
        X = np.array(trajectory_matrix)
        
        # Standardize
        X_scaled = self.scaler.fit_transform(X)
        
        # Cluster using K-means
        self.kmeans = KMeans(
            n_clusters=self.n_classes,
            random_state=self.random_state,
            n_init=10
        )
        
        self.class_assignments = {}
        assignments = self.kmeans.fit_predict(X_scaled)
        
        for subject_id, class_id in zip(valid_subject_ids, assignments):
            self.class_assignments[subject_id] = int(class_id)
        
        self.trajectory_params = {
            'subjects': valid_subject_ids,
            'parameters': trajectory_matrix,
            'feature_names': feature_names,
        }
        
        print(f"✓ Fitted {len(self.class_assignments)} patients into {self.n_classes} classes")
        return self
    
    def optimize_n_classes(
        self,
        patient_features_dict: Dict[int, List[Dict]],
        feature_names: List[str],
        k_range: List[int] = [2, 3, 4, 5]
    ) -> Dict:
        """
        Find optimal number of classes using BIC, AIC, and silhouette score.
        
        Parameters
        ----------
        patient_features_dict : dict
            Training data
        
        feature_names : list
            Features to model
        
        k_range : list
            Range of K values to test
        
        Returns
        -------
        dict
            {K: {'bic': ..., 'aic': ..., 'silhouette': ...}}
        """
        
        from sklearn.metrics import silhouette_score
        
        # Same setup as fit()
        all_trajectories = {}
        
        for feature_name in feature_names:
            df = LongitudinalTrajectoryData.reshape_for_mixed_effects(
                patient_features_dict,
                feature_name
            )
            
            if len(df) < 10:
                continue
            
            trajectories = TrajectoryParameterExtractor.fit_trajectory_model(
                df,
                feature_name
            )
            
            all_trajectories[feature_name] = trajectories
        
        # Build trajectory matrix
        subject_ids = sorted(list(set(
            s for trajs in all_trajectories.values() for s in trajs.keys()
        )))
        
        trajectory_matrix = []
        
        for subject_id in subject_ids:
            row = []
            skip = False
            
            for feature_name in feature_names:
                if subject_id not in all_trajectories[feature_name]:
                    skip = True
                    break
                traj = all_trajectories[feature_name][subject_id]
                row.append(traj['intercept'])
                row.append(traj['slope'])
            
            if not skip:
                trajectory_matrix.append(row)
        
        X = np.array(trajectory_matrix)
        X_scaled = self.scaler.fit_transform(X)
        
        # Test each K
        results = {}
        
        for k in k_range:
            if k >= len(X):
                continue
            
            kmeans = KMeans(n_clusters=k, random_state=self.random_state, n_init=10)
            assignments = kmeans.fit_predict(X_scaled)
            
            # BIC: 2*p*log(n) - 2*log(L)
            # AIC: 2*p - 2*log(L)
            # Using within-cluster sum of squares as proxy for likelihood
            inertia = kmeans.inertia_
            n_params = k * (X_scaled.shape[1] + 1)  # k centers + k weights
            n_samples = len(X)
            
            bic = 2 * n_params * np.log(n_samples) - 2 * (-inertia)
            aic = 2 * n_params - 2 * (-inertia)
            silhouette = silhouette_score(X_scaled, assignments)
            
            results[k] = {
                'bic': float(bic),
                'aic': float(aic),
                'silhouette': float(silhouette),
                'inertia': float(inertia),
            }
            
            print(f"K={k}: BIC={bic:.2f}, AIC={aic:.2f}, Silhouette={silhouette:.3f}")
        
        return results
    
    def get_class_assignment(self, subject_id: int) -> int:
        """Get trajectory class for a patient."""
        return self.class_assignments.get(subject_id, -1)
    
    def trajectory_class_comparison(
        self,
        responders: List[int],
        non_responders: List[int]
    ) -> Dict:
        """
        Compare trajectory class distribution (identical to existing method).
        """
        
        contingency = np.zeros((self.n_classes, 2))
        
        for subject_id in responders:
            if subject_id in self.class_assignments:
                cls = self.class_assignments[subject_id]
                contingency[cls, 0] += 1
        
        for subject_id in non_responders:
            if subject_id in self.class_assignments:
                cls = self.class_assignments[subject_id]
                contingency[cls, 1] += 1
        
        # Chi-square test
        chi2, pval, dof, expected = chi2_contingency(contingency)
        
        return {
            'chi2': chi2,
            'pvalue': pval,
            'dof': dof,
            'contingency': contingency,
        }


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    
    # 1. Prepare data (person-time format)
    # patient_features_dict = {
    #     subject_id: [
    #         {'time_hours': 0, 'mean_rr': 900, 'sdnn': 95, ...},
    #         {'time_hours': 5, 'mean_rr': 895, 'sdnn': 92, ...},
    #         ...
    #     ]
    # }
    
    # 2. Fit longitudinal trajectory model
    # features_for_trajectories = ['mean_rr', 'sdnn', 'systolic_mean']
    #
    # modeler = LongitudinalTrajectoryModeler(n_classes=3)
    # modeler.fit(
    #     patient_features_dict,
    #     feature_names=features_for_trajectories
    # )
    
    # 3. Optimize number of classes
    # cv_results = modeler.optimize_n_classes(
    #     patient_features_dict,
    #     features_for_trajectories,
    #     k_range=[2, 3, 4, 5]
    # )
    
    # 4. Compare responder/non-responder distribution
    # comparison = modeler.trajectory_class_comparison(
    #     responders=[sid for sid in responders],
    #     non_responders=[sid for sid in non_responders]
    # )
    
    pass
```

#### Step 3: Update Main Pipeline

File: `examples_feature_extraction.py` - Add section:

```python
# After fitting basic model, also fit longitudinal model
from data_ingestion.trajectory_modeler_longitudinal import LongitudinalTrajectoryModeler

# Prepare longitudinal data (requires window timestamps)
longitudinal_modeler = LongitudinalTrajectoryModeler(n_classes=3)

# Fit on key clinical features
key_features = ['mean_rr', 'sdnn', 'lf_power', 'hf_power', 
                'systolic_mean', 'diastolic_mean', 'map']

longitudinal_modeler.fit(
    patient_features_by_window,
    feature_names=key_features
)

# Optimize K
cv_results = longitudinal_modeler.optimize_n_classes(
    patient_features_by_window,
    feature_names=key_features
)

# Compare trajectory classes
traj_comparison = longitudinal_modeler.trajectory_class_comparison(
    responders=list(responder_ids),
    non_responders=list(non_responder_ids)
)
```

---

## 2. PULSE PRESSURE VARIATION (PPV)

### When to Use
- **Only for mechanically ventilated patients**
- Requires respiratory signal (ventilator waveform or capnography)
- Computed breath-by-breath

### Implementation

File: `data_ingestion/feature_extractor.py` - Add class:

```python
class MechanicalVentilationFeatures:
    """Features specific to mechanically ventilated patients."""
    
    @staticmethod
    def detect_breathing_cycles(
        respiratory_signal: np.ndarray,
        sampling_rate: int,
        method: str = 'peaks'
    ) -> List[Tuple[int, int]]:
        """
        Detect breathing cycle start/end from respiratory signal.
        
        Parameters
        ----------
        respiratory_signal : np.ndarray
            Respiratory impedance or capnography
        sampling_rate : int
            Sampling rate in Hz
        method : str
            'peaks' or 'zero_crossing'
        
        Returns
        -------
        list of (start_idx, end_idx)
            Indices marking start and end of each breath
        """
        
        if method == 'peaks':
            # Find peaks (inhalation) and troughs (exhalation)
            inhalation_peaks, _ = scipy_signal.find_peaks(
                respiratory_signal,
                distance=int(0.3 * sampling_rate)  # Min 300ms between breaths
            )
            
            exhalation_peaks, _ = scipy_signal.find_peaks(
                -respiratory_signal,
                distance=int(0.3 * sampling_rate)
            )
            
            # Interleave: sort all peaks
            all_peaks = np.sort(np.concatenate([inhalation_peaks, exhalation_peaks]))
            
            # Pair them
            breathing_cycles = []
            for i in range(0, len(all_peaks) - 1, 2):
                breathing_cycles.append((all_peaks[i], all_peaks[i+1]))
            
            return breathing_cycles
        
        else:  # zero_crossing
            # Count zero crossings as breath indicators
            zero_crossings = np.where(
                np.diff(np.sign(respiratory_signal - np.mean(respiratory_signal)))
            )[0]
            
            breathing_cycles = []
            for i in range(0, len(zero_crossings) - 1, 2):
                breathing_cycles.append((zero_crossings[i], zero_crossings[i+1]))
            
            return breathing_cycles
    
    @staticmethod
    def compute_ppv(
        abp_signal: np.ndarray,
        respiratory_signal: np.ndarray,
        sampling_rate_abp: int,
        sampling_rate_resp: int
    ) -> Dict[str, float]:
        """
        Compute Pulse Pressure Variation (PPV).
        
        PPV = ((PPmax - PPmin) / PPmean) * 100
        
        Indicates fluid responsiveness in mechanically ventilated patients:
        - PPV > 13% → fluid responders
        - PPV < 10% → unlikely to respond to fluids
        
        Parameters
        ----------
        abp_signal : np.ndarray
            Arterial blood pressure waveform
        respiratory_signal : np.ndarray
            Respiratory signal (capnography or impedance)
        sampling_rate_abp : int
            ABP sampling rate (Hz)
        sampling_rate_resp : int
            Respiratory signal sampling rate (Hz)
        
        Returns
        -------
        dict
            ppv_percent, ppmax, ppmin, ppmean
        """
        
        # Detect breathing cycles
        breathing_cycles = MechanicalVentilationFeatures.detect_breathing_cycles(
            respiratory_signal,
            sampling_rate_resp
        )
        
        if len(breathing_cycles) < 3:
            return {
                'ppv_percent': np.nan,
                'ppmax': np.nan,
                'ppmin': np.nan,
                'ppmean': np.nan,
            }
        
        # For each breathing cycle, find pulse pressure
        pulse_pressures = []
        
        for breath_start, breath_end in breathing_cycles:
            # Map breath indices to ABP indices (account for different sampling rates)
            abp_start = int(breath_start * sampling_rate_abp / sampling_rate_resp)
            abp_end = int(breath_end * sampling_rate_abp / sampling_rate_resp)
            
            if abp_end > len(abp_signal):
                continue
            
            abp_segment = abp_signal[abp_start:abp_end]
            
            # Find systolic and diastolic in this segment
            systolic = np.max(abp_segment)
            diastolic = np.min(abp_segment)
            
            pp = systolic - diastolic
            pulse_pressures.append(pp)
        
        if not pulse_pressures:
            return {
                'ppv_percent': np.nan,
                'ppmax': np.nan,
                'ppmin': np.nan,
                'ppmean': np.nan,
            }
        
        pp_array = np.array(pulse_pressures)
        ppmax = float(np.max(pp_array))
        ppmin = float(np.min(pp_array))
        ppmean = float(np.mean(pp_array))
        
        ppv = ((ppmax - ppmin) / ppmean * 100) if ppmean > 0 else np.nan
        
        return {
            'ppv_percent': float(ppv),
            'ppmax': ppmax,
            'ppmin': ppmin,
            'ppmean': ppmean,
        }
```

### Usage in Feature Extraction

```python
def extract_features_with_ventilation(
    ecg_signal, abp_signal,ppg_signal, respiratory_signal,
    sampling_rates, is_mechanically_ventilated=False
):
    """Extract all features, including PPV if available."""
    
    features = {}
    
    # Standard features (HRV, ABP, PPG)
    features.update(extract_standard_features(...))
    
    # Ventilation-specific features
    if is_mechanically_ventilated and respiratory_signal is not None:
        vent_features = MechanicalVentilationFeatures.compute_ppv(
            abp_signal,
            respiratory_signal,
            sampling_rates['abp'],
            sampling_rates['respiratory']
        )
        features.update(vent_features)
    
    return features
```

---

## 3. PULSE TRANSIT TIME (PTT)

### What is PTT
- Time delay from ECG R-wave to PPG peak
- Indicates vascular stiffness/compliance
- Useful for noninvasive BP estimation

### Implementation

File: `data_ingestion/feature_extractor.py` - Add method to `PPGFeatureExtractor`:

```python
class PPGFeatureExtractor:
    # ... existing methods ...
    
    @staticmethod
    def compute_pulse_transit_time(
        ecg_signal: np.ndarray,
        ppg_signal: np.ndarray,
        ecg_sampling_rate: int,
        ppg_sampling_rate: int
    ) -> Dict[str, float]:
        """
        Compute Pulse Transit Time (PTT) - delay from ECG R-wave to PPG peak.
        
        Clinical interpretation:
        - Lower PTT → stiffer arteries (higher BP, aging)
        - Higher PTT → more compliant arteries (lower BP, shock)
        
        Parameters
        ----------
        ecg_signal : np.ndarray
            ECG waveform
        ppg_signal : np.ndarray
            PPG waveform (finger or foot probe)
        ecg_sampling_rate : int
            ECG sampling rate (Hz)
        ppg_sampling_rate : int
            PPG sampling rate (Hz)
        
        Returns
        -------
        dict
            ptt_ms_mean, ptt_ms_sd, n_beats_analyzed
        """
        
        # 1. Detect R-waves in ECG
        r_peaks, _ = scipy_signal.find_peaks(
            ecg_signal,
            distance=int(0.3 * ecg_sampling_rate),  # 300ms minimum
            height=np.max(ecg_signal) * 0.5
        )
        
        if len(r_peaks) < 2:
            return {
                'ptt_ms_mean': np.nan,
                'ptt_ms_sd': np.nan,
                'n_beats_analyzed': 0,
            }
        
        # 2. Detect PPG pulse peaks
        ppg_peaks, _ = scipy_signal.find_peaks(
            ppg_signal,
            distance=int(0.3 * ppg_sampling_rate),
            height=np.max(ppg_signal) * 0.5
        )
        
        if len(ppg_peaks) < 2:
            return {
                'ptt_ms_mean': np.nan,
                'ptt_ms_sd': np.nan,
                'n_beats_analyzed': 0,
            }
        
        # 3. Synchronize: match ECG R-waves to subsequent PPG peaks
        ptt_values = []
        
        for r_peak in r_peaks[:-1]:  # All but last (might not have corresponding PPG peak)
            
            # Find PPG peaks occurring after this R-wave
            subsequent_ppg = ppg_peaks[ppg_peaks > r_peak]
            
            if len(subsequent_ppg) == 0:
                continue
            
            # Take the first PPG peak after this R-wave
            ppg_peak = subsequent_ppg[0]
            
            # Compute time delay
            # Adjust for different sampling rates
            ecg_time_sec = r_peak / ecg_sampling_rate
            ppg_time_sec = ppg_peak / ppg_sampling_rate
            
            ptt_sec = ppg_time_sec - ecg_time_sec
            ptt_ms = ptt_sec * 1000
            
            # Reasonable range: 10-1000 ms
            if 10 < ptt_ms < 1000:
                ptt_values.append(ptt_ms)
        
        if not ptt_values:
            return {
                'ptt_ms_mean': np.nan,
                'ptt_ms_sd': np.nan,
                'n_beats_analyzed': 0,
            }
        
        ptt_array = np.array(ptt_values)
        
        return {
            'ptt_ms_mean': float(np.mean(ptt_array)),
            'ptt_ms_sd': float(np.std(ptt_array)),
            'ptt_ms_median': float(np.median(ptt_array)),
            'ptt_ms_min': float(np.min(ptt_array)),
            'ptt_ms_max': float(np.max(ptt_array)),
            'n_beats_analyzed': len(ptt_values),
        }
```

### Usage

```python
def extract_multimodal_features(ecg, abp, ppg, sampling_rates):
    """Extract all features including cross-modal (PTT)."""
    
    features = {}
    
    # Individual signal features
    features['hrv'] = HRVFeatureExtractor.extract_all(ecg, sampling_rates['ecg'])
    features['abp'] = ABPFeatureExtractor.extract_all(abp, sampling_rates['abp'])
    features['ppg'] = PPGFeatureExtractor.compute_perfusion_index(ppg)
    
    # Cross-signal features
    features['ptt'] = PPGFeatureExtractor.compute_pulse_transit_time(
        ecg, ppg,
        sampling_rates['ecg'],
        sampling_rates['ppg']
    )
    
    return features
```

---

## Implementation Priority & Timeline

| Feature | Priority | Est. Time | Impact |
|---------|----------|-----------|--------|
| Longitudinal Trajectory Modeling | 🔴 HIGH | 2-3 days | Critical for GBTM |
| PPV (mechanical ventilation) | 🟡 MEDIUM | 1 day | Cohort-specific |
| PTT (ECG-PPG) | 🟡 MEDIUM | 1 day | Complexity feature |

**Recommended sequence:**
1. **Week 1 Day 1-2**: Longitudinal trajectory modeling
2. **Week 1 Day 3**: PPV (if ventilated cohort exists)
3. **Week 1 Day 4**: PTT (if PPG data available)
4. **Week 2**: Validation & testing

---

## Testing Recommendations

```python
# Test trajectory modeling
def test_longitudinal_modeler():
    # Generate synthetic longitudinal data
    n_patients = 100
    n_windows_per_patient = 15  # 5-minute windows = 75 hours
    
    synthetic_data = {}
    for pid in range(n_patients):
        windows = []
        for t in range(n_windows_per_patient):
            windows.append({
                'time_hours': t * 5 / 60,
                'mean_rr': 900 + np.random.randn() * 50 + t * 2,  # Increasing trend
                'sdnn': 95 + np.random.randn() * 10,
            })
        synthetic_data[pid] = windows
    
    # Fit model
    from data_ingestion.trajectory_modeler_longitudinal import LongitudinalTrajectoryModeler
    
    modeler = LongitudinalTrajectoryModeler(n_classes=3)
    modeler.fit(synthetic_data, feature_names=['mean_rr', 'sdnn'])
    
    # Test class assignment
    assigned_classes = [modeler.get_class_assignment(pid) for pid in range(n_patients)]
    assert len(set(assigned_classes)) == 3, "Should have 3 classes"
    print("✓ Longitudinal modeler test passed")
```

---

## Integration Checklist

- [ ] Create `trajectory_modeler_longitudinal.py`
- [ ] Add imports to `__init__.py`
- [ ] Test on synthetic data
- [ ] Test on MIMIC cohort (10,000 patients)
- [ ] Compare BIC/AIC to existing method
- [ ] Update `examples_feature_extraction.py`
- [ ] Add PPV module (if mechanically ventilated cohort)
- [ ] Add PTT module (if PPG data available)
- [ ] Validate clinical interpretability
- [ ] Generate final manuscript figures

---

This enhancement guide provides production-ready code for implementing all missing clinical features. Start with longitudinal trajectory modeling as the highest priority, then add ventilation-specific and cross-signal features as needed for your cohort.

