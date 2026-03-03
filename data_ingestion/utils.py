"""
Utility functions for data ingestion and processing.
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional, Tuple
import pickle
import json


def save_features(
    features: dict,
    output_path: str,
    format: str = 'pickle'
):
    """
    Save extracted features to disk.
    
    Parameters
    ----------
    features : dict
        Feature dictionary
    output_path : str
        Path to save file
    format : str
        'pickle', 'json', or 'csv'
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    if format == 'pickle':
        with open(output_path, 'wb') as f:
            pickle.dump(features, f)
    
    elif format == 'json':
        # Convert numpy types to native Python types
        def convert_types(obj):
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, (np.float32, np.float64)):
                return float(obj)
            elif isinstance(obj, (np.int32, np.int64)):
                return int(obj)
            elif isinstance(obj, dict):
                return {k: convert_types(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_types(item) for item in obj]
            return obj
        
        features_json = convert_types(features)
        with open(output_path, 'w') as f:
            json.dump(features_json, f, indent=2)
    
    elif format == 'csv':
        if isinstance(features, dict):
            df = pd.DataFrame([features])
        else:
            df = features
        df.to_csv(output_path, index=False)


def load_features(input_path: str) -> dict:
    """Load features from disk."""
    input_path = Path(input_path)
    
    if input_path.suffix == '.pkl':
        with open(input_path, 'rb') as f:
            return pickle.load(f)
    
    elif input_path.suffix == '.json':
        with open(input_path, 'r') as f:
            return json.load(f)
    
    elif input_path.suffix == '.csv':
        df = pd.read_csv(input_path)
        return df.to_dict('records')[0] if len(df) > 0 else {}
    
    else:
        raise ValueError(f"Unsupported format: {input_path.suffix}")


def deidentify_subject_id(subject_id: int, salt: str = "") -> str:
    """
    Deidentify subject ID using hash.
    
    Parameters
    ----------
    subject_id : int
        Original MIMIC subject ID
    salt : str
        Salt for hashing
    
    Returns
    -------
    str
        Hashed ID (e.g., 'SUBJ_a1b2c3d4')
    """
    import hashlib
    hash_input = f"{subject_id}_{salt}".encode()
    hash_digest = hashlib.sha256(hash_input).hexdigest()[:8]
    return f"SUBJ_{hash_digest.upper()}"


def standardize_features(
    X: pd.DataFrame,
    fit_on: Optional[pd.DataFrame] = None,
    remove_nan: bool = True
) -> Tuple[pd.DataFrame, dict]:
    """
    Standardize (z-score) feature matrix.
    
    Parameters
    ----------
    X : pd.DataFrame
        Feature matrix
    fit_on : pd.DataFrame, optional
        Use this data to compute mean/std (for test set standardization)
    remove_nan : bool
        Replace NaN with 0 after standardization
    
    Returns
    -------
    X_std : pd.DataFrame
        Standardized features
    params : dict
        Standardization parameters (mean, std) for later inverse transform
    """
    if fit_on is None:
        fit_on = X
    
    means = fit_on.mean()
    stds = fit_on.std()
    stds[stds == 0] = 1  # Avoid division by zero
    
    X_std = (X - means) / stds
    
    if remove_nan:
        X_std = X_std.fillna(0)
    
    return X_std, {'mean': means, 'std': stds}


def remove_outliers(
    X: pd.DataFrame,
    method: str = 'iqr',
    threshold: float = 1.5
) -> Tuple[pd.DataFrame, list]:
    """
    Remove outlier samples from feature matrix.
    
    Parameters
    ----------
    X : pd.DataFrame
        Feature matrix
    method : str
        'iqr' (interquartile range) or 'zscore'
    threshold : float
        Threshold for outlier detection
    
    Returns
    -------
    X_clean : pd.DataFrame
        Data with outliers removed
    outlier_indices : list
        Indices of removed rows
    """
    if method == 'iqr':
        Q1 = X.quantile(0.25)
        Q3 = X.quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - threshold * IQR
        upper_bound = Q3 + threshold * IQR
        
        outliers = ~((X >= lower_bound) & (X <= upper_bound)).all(axis=1)
    
    elif method == 'zscore':
        from scipy.stats import zscore
        outliers = (np.abs(zscore(X.fillna(0))) > threshold).any(axis=1)
    
    else:
        raise ValueError(f"Unknown method: {method}")
    
    outlier_indices = X[outliers].index.tolist()
    X_clean = X[~outliers].copy()
    
    return X_clean, outlier_indices


def impute_missing_values(
    X: pd.DataFrame,
    method: str = 'mean',
    fit_on: Optional[pd.DataFrame] = None
) -> Tuple[pd.DataFrame, dict]:
    """
    Impute missing values in feature matrix.
    
    Parameters
    ----------
    X : pd.DataFrame
        Feature matrix with NaN values
    method : str
        'mean', 'median', 'forward_fill', or 'drop'
    fit_on : pd.DataFrame, optional
        Use statistics from this data for imputation
    
    Returns
    -------
    X_imputed : pd.DataFrame
        Features with imputation applied
    params : dict
        Imputation parameters (for test set)
    """
    X_copy = X.copy()
    params = {}
    
    if fit_on is None:
        fit_on = X
    
    if method == 'mean':
        fill_values = fit_on.mean()
        X_imputed = X_copy.fillna(fill_values)
        params = {'fill_values': fill_values}
    
    elif method == 'median':
        fill_values = fit_on.median()
        X_imputed = X_copy.fillna(fill_values)
        params = {'fill_values': fill_values}
    
    elif method == 'drop':
        X_imputed = X_copy.dropna()
        params = {}
    
    else:
        raise ValueError(f"Unknown method: {method}")
    
    return X_imputed, params
