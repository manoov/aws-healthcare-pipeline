"""
MIMIC-IV Data Ingestion Pipeline
==================================

This module handles:
1. Loading MIMIC-IV structured data (admissions, diagnoses, labs)
2. Building patient cohorts for critical care research
3. Integrating continuous waveform data (ECG, ABP, PPG, respiratory)
4. Extracting clinical features for trajectory modeling

Key components:
- MIMICLoader: Read and parse MIMIC-IV hosp CSV files
- CohortBuilder: Define inclusion/exclusion criteria
- WaveformLoader: Parse waveform data and metadata
- FeatureExtractor: Compute HRV, BP variability, morphology features
"""

from .mimic_loader import MIMICLoader
from .cohort_builder import CohortBuilder
from .waveform_loader import WaveformLoader
from .feature_extractor import (
    HRVFeatureExtractor,
    ABPFeatureExtractor,
    PPGFeatureExtractor,
    ECGfeatureExtractor,
    FeatureAggregator,
)

__all__ = [
    'MIMICLoader',
    'CohortBuilder',
    'WaveformLoader',
    'HRVFeatureExtractor',
    'ABPFeatureExtractor',
    'PPGFeatureExtractor',
    'ECGfeatureExtractor',
    'FeatureAggregator',
]
