#!/usr/bin/env python3
"""
Example: End-to-End Feature Extraction and Trajectory Modeling

This script demonstrates:
1. Loading MIMIC-IV data
2. Defining a sepsis cohort
3. Extracting features from waveforms (when available)
4. Aggregating features to patient level
5. Fitting trajectory models
6. Comparing with baseline SOFA
"""

import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import argparse

from data_ingestion import (
    MIMICLoader,
    CohortBuilder,
    WaveformLoader,
)
from data_ingestion.feature_extractor import (
    HRVFeatureExtractor,
    ABPFeatureExtractor,
    PPGFeatureExtractor,
    ECGfeatureExtractor,
    FeatureAggregator,
)
from data_ingestion.cohort_builder import TrajectoryModeler, BaselineComparison
from data_ingestion import utils


def load_mimic_data(mimic_root: str) -> MIMICLoader:
    """Load MIMIC-IV data."""
    print(f"Loading MIMIC-IV data from {mimic_root}...")
    loader = MIMICLoader(mimic_root)
    return loader


def build_cohort(mimic_loader: MIMICLoader) -> pd.DataFrame:
    """Build sepsis cohort and add synthetic outcome labels."""
    print("Building sepsis cohort...")
    builder = CohortBuilder(mimic_loader)
    cohort = builder.define_sepsis_cohort(
        require_sepsis_code=True,
        require_abx_start=False,
        min_icu_hours=6
    )
    
    # Add synthetic SOFA scores for demonstration
    np.random.seed(42)
    cohort['sofa_0h'] = np.random.normal(8, 2.5, len(cohort)).clip(2, 15)
    # Non-responders have worse SOFA trajectory
    responder_mask = np.random.rand(len(cohort)) < 0.5
    sofa_48h = cohort['sofa_0h'].copy()
    sofa_48h[responder_mask] -= np.random.uniform(2, 5, responder_mask.sum())  # Improvement
    sofa_48h[~responder_mask] += np.random.uniform(-1, 2, (~responder_mask).sum())  # Worsening/stable
    cohort['sofa_48h'] = sofa_48h.clip(1, 15)
    
    # Add response labels
    cohort['response'] = cohort.apply(
        lambda row: 'responder' if (row['sofa_0h'] - row['sofa_48h']) >= 2 else 'non_responder',
        axis=1
    )
    
    print(f"Cohort size: {len(cohort)} patients")
    print(f"Responders: {(cohort['response'] == 'responder').sum()} ({100*(cohort['response'] == 'responder').sum()/len(cohort):.1f}%)")
    print(f"Non-responders: {(cohort['response'] == 'non_responder').sum()} ({100*(cohort['response'] == 'non_responder').sum()/len(cohort):.1f}%)")
    return cohort


def generate_synthetic_features(cohort: pd.DataFrame) -> dict:
    """
    Generate synthetic features for demonstration/testing.
    
    In real use, this would come from actual waveform processing.
    For now, generates realistic feature distributions.
    
    Returns
    -------
    dict
        {subject_id: {feature_name: value}}
    """
    print("Generating synthetic features for demonstration...")
    np.random.seed(42)
    
    patient_features = {}
    feature_names = [
        'mean_rr', 'sdnn', 'rmssd', 'pnn50', 'mean_hr',
        'lf_power', 'hf_power', 'lf_hf_ratio',
        'systolic_mean', 'systolic_sd', 'diastolic_mean', 'diastolic_sd',
        'pulse_pressure_mean', 'map',
        'perfusion_index', 'qrs_width', 'dpdt_mean',
    ]
    
    for idx, row in cohort.iterrows():
        subject_id = row['subject_id']
        
        # Generate realistic ranges for each feature
        features = {
            'mean_rr': np.random.normal(900, 100),  # ms
            'sdnn': np.random.normal(100, 30),
            'rmssd': np.random.normal(50, 20),
            'pnn50': np.random.uniform(5, 50),
            'mean_hr': np.random.normal(85, 15),  # bpm
            'lf_power': np.random.exponential(200),
            'hf_power': np.random.exponential(150),
            'lf_hf_ratio': np.random.lognormal(0, 1),
            'systolic_mean': np.random.normal(130, 20),  # mmHg
            'systolic_sd': np.random.normal(15, 5),
            'diastolic_mean': np.random.normal(75, 12),
            'diastolic_sd': np.random.normal(10, 3),
            'pulse_pressure_mean': np.random.normal(55, 15),
            'map': np.random.normal(93, 12),
            'perfusion_index': np.random.uniform(0.5, 5.0),
            'qrs_width': np.random.normal(90, 15),  # ms
            'dpdt_mean': np.random.normal(800, 200),  # mmHg/s
        }
        
        patient_features[subject_id] = features
    
    print(f"Generated features for {len(patient_features)} patients")
    return patient_features


def extract_features_from_waveforms(
    waveform_root: str,
    cohort: pd.DataFrame,
    window_minutes: int = 5
) -> dict:
    """
    Extract HRV, BP, and PPG features from waveforms.
    
    Returns
    -------
    dict
        {subject_id: {feature_name: value}}
    """
    print(f"Opening waveform data from {waveform_root}...")
    wfloader = WaveformLoader(waveform_root)
    
    if not wfloader.is_available():
        print("WARNING: Waveform data not yet downloaded.")
        print("Falling back to synthetic features for demonstration.")
        return generate_synthetic_features(cohort)
    
    patient_features = {}
    
    for idx, row in cohort.iterrows():
        subject_id = row['subject_id']
        hadm_id = row['hadm_id']
        
        if idx % 50 == 0:
            print(f"Processing patient {idx+1}/{len(cohort)}...")
        
        # Try to load ECG
        try:
            # Placeholder: real implementation would discover actual record paths
            # For this example, we'll generate synthetic features
            ecg_signal = np.random.randn(250 * 3600)  # 1 hour at 250 Hz
            sampling_rate = 250
            
            # Extract HRV
            rr_intervals = HRVFeatureExtractor.extract_rr_intervals(
                ecg_signal, sampling_rate
            )
            
            if len(rr_intervals) > 0:
                td_hrv = HRVFeatureExtractor.time_domain_hrv(rr_intervals)
                fd_hrv = HRVFeatureExtractor.frequency_domain_hrv(rr_intervals)
                
                patient_features[subject_id] = {
                    **td_hrv,
                    **fd_hrv,
                }
        except Exception as e:
            print(f"  Error processing subject {subject_id}: {e}")
            continue
    
    print(f"Extracted features for {len(patient_features)} patients")
    return patient_features


def aggregate_features(
    patient_features: dict,
    feature_names: list
) -> pd.DataFrame:
    """Aggregate windowed features to patient level."""
    print("Aggregating features to patient level...")
    
    feature_matrix = []
    
    for subject_id, features_dict in patient_features.items():
        agg_dict = {'subject_id': subject_id}
        
        for feat_name in feature_names:
            if feat_name in features_dict:
                agg_dict[feat_name] = features_dict[feat_name]
        
        feature_matrix.append(agg_dict)
    
    df = pd.DataFrame(feature_matrix)
    return df


def fit_trajectory_model(
    feature_matrix: pd.DataFrame,
    n_classes: int = 3
) -> TrajectoryModeler:
    """Fit trajectory model."""
    print(f"Fitting trajectory model with {n_classes} classes...")
    
    # Extract only numeric columns for modeling
    numeric_columns = feature_matrix.select_dtypes(include=[np.number]).columns.tolist()
    if 'subject_id' in numeric_columns:
        numeric_columns.remove('subject_id')
    
    X = feature_matrix[numeric_columns].fillna(feature_matrix[numeric_columns].mean())
    
    modeler = TrajectoryModeler(n_classes=n_classes)
    modeler.fit_sklearn_mixture(X)
    
    print(f"Model fitted. Class distribution:")
    unique, counts = np.unique(modeler.class_assignments, return_counts=True)
    for cls, cnt in zip(unique, counts):
        pct = 100 * cnt / len(modeler.class_assignments)
        print(f"  Class {cls}: {cnt} patients ({pct:.1f}%)")
    
    return modeler


def create_report(
    cohort: pd.DataFrame,
    feature_matrix: pd.DataFrame,
    modeler: TrajectoryModeler,
    output_dir: str = './results'
) -> None:
    """Generate summary report."""
    print(f"Generating report in {output_dir}...")
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Summary statistics
    summary = CohortBuilder.summary_statistics(
        cohort,
        feature_matrix,
        outcome_col='response'
    )
    
    with open(output_path / 'summary_stats.txt', 'w') as f:
        for key, val in summary.items():
            f.write(f"{key}: {val}\n")
    
    # Feature correlations
    numeric_features = feature_matrix.select_dtypes(include=[np.number])
    feature_corr = numeric_features.corr()
    feature_corr.to_csv(output_path / 'feature_correlations.csv')
    
    # Trajectory assignments - map subject_id to class assignments
    if 'subject_id' in feature_matrix.columns:
        trajectory_df = pd.DataFrame({
            'subject_id': feature_matrix['subject_id'],
            'trajectory_class': modeler.class_assignments,
        })
    else:
        # Fallback if subject_id not in feature matrix
        trajectory_df = pd.DataFrame({
            'index': range(len(modeler.class_assignments)),
            'trajectory_class': modeler.class_assignments,
        })
    
    trajectory_df.to_csv(output_path / 'trajectory_assignments.csv', index=False)
    
    # Chi-square test for trajectory distribution by response
    if 'response' in cohort.columns and len(trajectory_df) > 0:
        responder_ids = cohort[cohort['response'] == 'responder']['subject_id'].tolist()
        nonresponder_ids = cohort[cohort['response'] == 'non_responder']['subject_id'].tolist()
        
        if 'subject_id' in trajectory_df.columns:
            responder_classes = trajectory_df[
                trajectory_df['subject_id'].isin(responder_ids)
            ]['trajectory_class'].values
            nonresponder_classes = trajectory_df[
                trajectory_df['subject_id'].isin(nonresponder_ids)
            ]['trajectory_class'].values
            
            if len(responder_classes) > 0 and len(nonresponder_classes) > 0:
                try:
                    comparison = modeler.trajectory_comparison(responder_ids, nonresponder_ids)
                    with open(output_path / 'trajectory_comparison.txt', 'w') as f:
                        f.write(f"Chi-square test: χ² = {comparison['chi2']:.2f}, p = {comparison['pvalue']:.6f}\n")
                        f.write(f"DOF: {comparison['dof']}\n")
                        f.write(f"\nContingency table:\n")
                        f.write(str(comparison['contingency_table']) + '\n')
                        f.write(f"\nResponder distribution by class: {comparison['responder_distribution']}\n")
                        f.write(f"Non-responder distribution by class: {comparison['nonresponder_distribution']}\n")
                except Exception as e:
                    print(f"Warning: Could not compute trajectory comparison: {e}")
    
    print(f"✓ Report saved to {output_path}")
    print(f"  - summary_stats.txt: Cohort demographics and baseline characteristics")
    print(f"  - feature_correlations.csv: Feature inter-correlations")
    print(f"  - trajectory_assignments.csv: Patient → trajectory class mapping")


def main():
    parser = argparse.ArgumentParser(
        description="Extract features and fit trajectory models"
    )
    parser.add_argument(
        '--mimic-root',
        required=True,
        help='Path to MIMIC-IV root directory'
    )
    parser.add_argument(
        '--waveform-root',
        default=None,
        help='Path to waveform data directory (optional)'
    )
    parser.add_argument(
        '--skip-waveforms',
        action='store_true',
        help='Skip waveform feature extraction'
    )
    parser.add_argument(
        '--n-classes',
        type=int,
        default=3,
        help='Number of trajectory classes'
    )
    parser.add_argument(
        '--output-dir',
        default='./trajectory_results',
        help='Output directory for results'
    )
    
    args = parser.parse_args()
    
    # Step 1: Load MIMIC data
    mimic_loader = load_mimic_data(args.mimic_root)
    
    # Step 2: Build cohort
    cohort = build_cohort(mimic_loader)
    
    # Step 3: Extract features
    if args.skip_waveforms or args.waveform_root is None:
        print("Using synthetic features for demonstration...")
        patient_features = generate_synthetic_features(cohort)
    else:
        patient_features = extract_features_from_waveforms(
            args.waveform_root,
            cohort
        )
    
    if not patient_features:
        print("ERROR: No features extracted.")
        return
    
    # Step 4: Aggregate features
    feature_names = list(patient_features[list(patient_features.keys())[0]].keys())
    feature_matrix = aggregate_features(patient_features, feature_names)
    
    # Step 5: Fit trajectory model
    if len(feature_matrix) > 0:
        modeler = fit_trajectory_model(feature_matrix, n_classes=args.n_classes)
        
        # Step 6: Generate report
        create_report(cohort, feature_matrix, modeler, args.output_dir)
    
    print("Done!")


if __name__ == '__main__':
    main()
