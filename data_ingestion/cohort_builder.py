"""
Cohort Definition and Trajectory Modeling

Defines patient cohorts, outcome classification, and prepares data for
Group-Based Trajectory Modeling (GBTM) and latent class analysis.
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class SOFA:
    """SOFA score components and total score."""
    respiratory: float  # PaO2/FiO2
    coagulation: float  # Platelets
    liver: float        # Bilirubin
    cardiovascular: float  # MAP + vasopressor
    cns: float          # GCS
    renal: float        # Creatinine or UO
    
    @property
    def total(self) -> float:
        """Total SOFA score (sum of components, each 0-4)."""
        return sum([self.respiratory, self.coagulation, self.liver,
                   self.cardiovascular, self.cns, self.renal])


class CohortBuilder:
    """Build and filter patient cohorts for trajectory analysis."""
    
    def __init__(self, mimic_loader=None):
        """
        Parameters
        ----------
        mimic_loader : MIMICLoader, optional
            MIMIC data loader for cohort definition
        """
        self.mimic_loader = mimic_loader
        self.cohort = None
        self.outcomes = None
    
    def define_sepsis_cohort(
        self,
        require_sepsis_code: bool = True,
        require_abx_start: bool = True,
        min_icu_hours: int = 6,
        max_age: int = 120,
        exclusion_diagnoses: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Define patient cohort: ICU sepsis patients.
        
        Inclusion:
        - Age >= 18 years
        - ICU admission
        - Sepsis diagnosis (ICD-10) OR antibiotics + suspected infection
        
        Exclusion:
        - Specific diagnoses (e.g., pregnancy, terminal illness)
        - Very short ICU stays
        
        Parameters
        ----------
        require_sepsis_code : bool
            Require ICD-10 sepsis code
        require_abx_start : bool
            Require antibiotic administration
        min_icu_hours : int
            Minimum ICU stay
        max_age : int
            Maximum age filter
        exclusion_diagnoses : list, optional
            ICD codes to exclude patients
        
        Returns
        -------
        pd.DataFrame
            Filtered cohort
        """
        if self.mimic_loader is None:
            raise ValueError("MIMICLoader not provided")
        
        # Start with ICU admissions
        cohort = self.mimic_loader.get_icu_admissions(min_icu_hours)
        
        if require_sepsis_code:
            # Filter for sepsis diagnosis
            diagnoses = self.mimic_loader.load_diagnoses()
            sepsis_patients = diagnoses[
                diagnoses['icd_code'].isin(
                    self.mimic_loader.SEPSIS_CODES
                )
            ]['subject_id'].unique()
            cohort = cohort[cohort['subject_id'].isin(sepsis_patients)]
        
        self.cohort = cohort.reset_index(drop=True)
        return self.cohort
    
    @staticmethod
    def classify_response(
        baseline_sofa: float,
        followup_sofa: float,
        improvement_threshold: int = 2
    ) -> str:
        """
        Classify patient response status.
        
        Parameters
        ----------
        baseline_sofa : float
            SOFA score at ICU admission (or day 0-1)
        followup_sofa : float
            SOFA score at 48-72 hours
        improvement_threshold : int
            SOFA point decrease to define responder
        
        Returns
        -------
        str
            'responder', 'non_responder', or 'unknown'
        """
        if np.isnan(baseline_sofa) or np.isnan(followup_sofa):
            return 'unknown'
        
        improvement = baseline_sofa - followup_sofa
        
        if improvement >= improvement_threshold:
            return 'responder'
        else:
            return 'non_responder'
    
    def add_outcome_labels(
        self,
        sofa_baseline_col: str = 'sofa_0h',
        sofa_followup_col: str = 'sofa_48h',
        improvement_threshold: int = 2
    ) -> pd.DataFrame:
        """
        Add responder/non-responder labels to cohort.
        
        Parameters
        ----------
        sofa_baseline_col : str
            Column name for baseline SOFA
        sofa_followup_col : str
            Column name for followup SOFA
        improvement_threshold : int
            SOFA improvement threshold for responder definition
        
        Returns
        -------
        pd.DataFrame
            Cohort with added 'response' column
        """
        if self.cohort is None:
            raise ValueError("Cohort not defined; call define_sepsis_cohort first")
        
        responses = []
        for idx, row in self.cohort.iterrows():
            response = self.classify_response(
                row.get(sofa_baseline_col, np.nan),
                row.get(sofa_followup_col, np.nan),
                improvement_threshold
            )
            responses.append(response)
        
        self.cohort['response'] = responses
        return self.cohort
    
    @staticmethod
    def prepare_trajectory_data(
        cohort: pd.DataFrame,
        patient_features: Dict[int, Dict],
        feature_names: List[str],
        outcome_col: str = 'response'
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Prepare data for trajectory modeling.
        
        Formats feature matrix and outcomes for GBTM/latent class analysis.
        
        Parameters
        ----------
        cohort : pd.DataFrame
            Patient cohort with subject_id and outcome
        patient_features : dict
            {subject_id: {feature_name: value}}
        feature_names : list
            Names of features to use
        outcome_col : str
            Column name for outcome variable
        
        Returns
        -------
        X : pd.DataFrame
            Feature matrix (n_patients, n_features)
        y : pd.Series
            Outcome vector (n_patients,)
        """
        rows = []
        outcomes = []
        valid_subjects = []
        
        for subject_id, row in cohort.iterrows():
            subj_id = row.get('subject_id')
            
            if subj_id not in patient_features:
                continue
            
            features = patient_features[subj_id]
            feat_dict = {f: features.get(f, np.nan) for f in feature_names}
            
            rows.append(feat_dict)
            outcomes.append(row[outcome_col])
            valid_subjects.append(subj_id)
        
        X = pd.DataFrame(rows)
        y = pd.Series(outcomes)
        
        return X, y, valid_subjects
    
    @staticmethod
    def summary_statistics(
        cohort: pd.DataFrame,
        features_df: pd.DataFrame,
        outcome_col: str = 'response'
    ) -> Dict:
        """
        Compute cohort summary statistics (Table 1 of manuscripts).
        
        Parameters
        ----------
        cohort : pd.DataFrame
            Patient demographics and outcomes
        features_df : pd.DataFrame
            Aggregated features
        outcome_col : str
            Column for outcome variable
        
        Returns
        -------
        dict
            Summary statistics by response group
        """
        summary = {}
        
        # Cohort size
        summary['total_n'] = len(cohort)
        
        if outcome_col in cohort.columns:
            for response in cohort[outcome_col].unique():
                subset = cohort[cohort[outcome_col] == response]
                summary[f'{response}_n'] = len(subset)
                summary[f'{response}_pct'] = 100 * len(subset) / len(cohort)
        
        # Demographic characteristics
        if 'age' in cohort.columns:
            summary['age_mean'] = cohort['age'].mean()
            summary['age_sd'] = cohort['age'].std()
        
        if 'gender' in cohort.columns or 'sex' in cohort.columns:
            sex_col = 'gender' if 'gender' in cohort.columns else 'sex'
            if cohort[sex_col].dtype == 'object':
                # String values (M/F), count males
                male_count = (cohort[sex_col].str.upper() == 'M').sum()
                summary['male_n'] = male_count
                summary['male_pct'] = 100 * male_count / len(cohort)
        
        # Feature summaries
        for col in features_df.columns:
            if features_df[col].dtype in ['float64', 'float32']:
                summary[f'{col}_mean'] = features_df[col].mean()
                summary[f'{col}_sd'] = features_df[col].std()
        
        return summary


class TrajectoryModeler:
    """Group-Based Trajectory Modeling (GBTM) support."""
    
    def __init__(self, n_classes: int = 3):
        """
        Parameters
        ----------
        n_classes : int
            Number of trajectory classes to identify
        """
        self.n_classes = n_classes
        self.model = None
        self.class_assignments = None
        self.weights = None
    
    def fit_sklearn_mixture(
        self,
        X: pd.DataFrame,
        y: Optional[pd.Series] = None,
        time_windows: Optional[np.ndarray] = None
    ):
        """
        Fit Gaussian Mixture Model or Bayesian GMM for trajectory classes.
        
        Simple approach: cluster patients on their trajectory features.
        More sophisticated: use longitudinal mixed-effects models.
        
        Parameters
        ----------
        X : pd.DataFrame
            Feature matrix (n_patients, n_features)
        y : pd.Series, optional
            Outcome labels
        time_windows : np.ndarray, optional
            Time points for trajectory
        """
        try:
            from sklearn.mixture import GaussianMixture
        except ImportError:
            raise ImportError("pip install scikit-learn")
        
        # Standardize features
        X_scaled = (X - X.mean()) / X.std()
        
        # Fit GMM
        self.model = GaussianMixture(n_components=self.n_classes)
        self.class_assignments = self.model.fit_predict(X_scaled)
        self.weights = self.model.weights_
        
        return self
    
    def get_class_assignment(self, subject_id: int) -> int:
        """Get trajectory class for a patient."""
        return self.class_assignments[subject_id]
    
    def trajectory_comparison(
        self,
        responders: List[int],
        non_responders: List[int]
    ) -> Dict:
        """
        Compare trajectory class distribution between response groups.
        
        Parameters
        ----------
        responders : list
            Subject IDs of responders
        non_responders : list
            Subject IDs of non-responders
        
        Returns
        -------
        dict
            Chi-square test results, class distributions, etc.
        """
        try:
            from scipy.stats import chi2_contingency
        except ImportError:
            raise ImportError("pip install scipy")
        
        # Build contingency table
        contingency = np.zeros((self.n_classes, 2))
        
        for sid in responders:
            cls = self.class_assignments[sid]
            contingency[cls, 0] += 1
        
        for sid in non_responders:
            cls = self.class_assignments[sid]
            contingency[cls, 1] += 1
        
        # Chi-square test
        chi2, pval, dof, expected = chi2_contingency(contingency)
        
        # Distribution percentages
        responder_dist = contingency[:, 0] / contingency[:, 0].sum() * 100
        nonresponder_dist = contingency[:, 1] / contingency[:, 1].sum() * 100
        
        return {
            'chi2': chi2,
            'pvalue': pval,
            'dof': dof,
            'contingency_table': contingency,
            'responder_distribution': responder_dist,
            'nonresponder_distribution': nonresponder_dist,
        }
    
    def roc_analysis(
        self,
        trajectory_class: int,
        outcomes: np.ndarray
    ) -> Dict:
        """
        Compute ROC and AUROC for trajectory class predicting outcome.
        
        Parameters
        ----------
        trajectory_class : int
            Which class to use as positive label
        outcomes : np.ndarray
            Binary outcome (0=responder, 1=non-responder)
        
        Returns
        -------
        dict
            AUROC, sensitivity, specificity, etc.
        """
        try:
            from sklearn.metrics import roc_curve, auc
        except ImportError:
            raise ImportError("pip install scikit-learn")
        
        # Class membership as predictor
        y_pred = (self.class_assignments == trajectory_class).astype(int)
        
        fpr, tpr, thresholds = roc_curve(outcomes, y_pred)
        auroc = auc(fpr, tpr)
        
        return {
            'auroc': auroc,
            'fpr': fpr,
            'tpr': tpr,
            'thresholds': thresholds,
            'sensitivity': tpr,
            'specificity': 1 - fpr,
        }


class BaselineComparison:
    """Compare trajectory-based predictions with baseline (SOFA score)."""
    
    @staticmethod
    def delong_test(
        auc1: float,
        se1: float,
        auc2: float,
        se2: float,
        n_samples: int
    ) -> Tuple[float, float]:
        """
        DeLong test for comparing two AUC scores.
        
        Tests if AUROC from trajectory model is significantly different
        from AUROC of baseline SOFA score.
        
        Parameters
        ----------
        auc1 : float
            AUROC from method 1 (trajectory model)
        se1 : float
            Standard error of AUC1
        auc2 : float
            AUROC from method 2 (baseline SOFA)
        se2 : float
            Standard error of AUC2
        n_samples : int
            Number of samples
        
        Returns
        -------
        z_statistic : float
        p_value : float
        """
        try:
            from scipy.stats import norm
        except ImportError:
            raise ImportError("pip install scipy")
        
        # DeLong test
        diff = auc1 - auc2
        se_diff = np.sqrt(se1 ** 2 + se2 ** 2)
        z = diff / se_diff
        p_value = 2 * (1 - norm.cdf(np.abs(z)))
        
        return z, p_value
    
    @staticmethod
    def create_comparison_table(
        trajectory_results: Dict,
        sofa_results: Dict,
        method_names: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Create a summary table comparing model performance.
        
        Returns
        -------
        pd.DataFrame
            Comparison table with AUROCs, sensitivity, specificity
        """
        if method_names is None:
            method_names = ['Trajectory Model', 'Baseline SOFA']
        
        comparison = {
            'Method': method_names,
            'AUROC': [
                trajectory_results.get('auroc', np.nan),
                sofa_results.get('auroc', np.nan)
            ],
            'Sensitivity': [
                trajectory_results.get('sensitivity', np.nan),
                sofa_results.get('sensitivity', np.nan)
            ],
            'Specificity': [
                trajectory_results.get('specificity', np.nan),
                sofa_results.get('specificity', np.nan)
            ],
        }
        
        return pd.DataFrame(comparison)
