"""
MIMIC-IV Hospital Module Data Loader

Loads and parses MIMIC-IV hospital data (admissions, diagnoses, ICU info, labs).
Handles decompression and caching for efficient repeated access.
"""

import os
import gzip
import pandas as pd
from pathlib import Path
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta


class MIMICLoader:
    """Load MIMIC-IV hospital data from compressed CSV files."""
    
    # MIMIC-IV hosp module relative paths
    HOSP_FILES = {
        'admissions': 'hosp/admissions.csv.gz',
        'diagnoses_icd': 'hosp/diagnoses_icd.csv.gz',
        'd_icd_diagnoses': 'hosp/d_icd_diagnoses.csv.gz',
        'labevents': 'hosp/labevents.csv.gz',
        'd_labitems': 'hosp/d_labitems.csv.gz',
    }
    
    # Critical care relevant ICD-10 codes (sepsis, organ dysfunction)
    SEPSIS_CODES = [
        'R6520',  # Sepsis with acute organ dysfunction
        'R6521',  # Sepsis with septic shock
        'A40',    # Group A Streptococcal sepsis
        'A41',    # Other sepsis
    ]
    
    ORGAN_DYSFUNCTION_CODES = [
        'N17',    # Acute kidney injury
        'I50',    # Heart failure
        'I63',    # Cerebral infarction
        'J96',    # Respiratory failure
    ]
    
    def __init__(self, data_root: str, cache_dir: Optional[str] = None):
        """
        Parameters
        ----------
        data_root : str
            Path to MIMIC-IV root (e.g., '/data/physionet.org/files/mimiciv/3.1')
        cache_dir : str, optional
            Directory to cache decompressed data (default: data_root/.cache)
        """
        self.data_root = Path(data_root)
        self.cache_dir = Path(cache_dir or self.data_root / '.cache')
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache = {}
        
    def _load_file(self, key: str, nrows: Optional[int] = None) -> pd.DataFrame:
        """Load a CSV.gz file with caching."""
        if key in self._cache and nrows is None:
            return self._cache[key].copy()
        
        file_path = self.data_root / self.HOSP_FILES[key]
        if not file_path.exists():
            raise FileNotFoundError(f"Missing MIMIC file: {file_path}")
        
        print(f"Loading {key}...")
        df = pd.read_csv(file_path, nrows=nrows)
        
        if nrows is None:
            self._cache[key] = df.copy()
        
        return df
    
    def load_admissions(self, nrows: Optional[int] = None) -> pd.DataFrame:
        """
        Load patient admissions.
        
        Returns columns:
        - subject_id, hadm_id, admittime, dischtime, admission_type, 
          insurance, ethnicity, diagnosis
        """
        return self._load_file('admissions', nrows)
    
    def load_diagnoses(self, nrows: Optional[int] = None) -> pd.DataFrame:
        """Load diagnosis codes (ICD-10) for each admission."""
        return self._load_file('diagnoses_icd', nrows)
    
    def load_d_icd_diagnoses(self) -> pd.DataFrame:
        """Load ICD-10 diagnosis reference table."""
        return self._load_file('d_icd_diagnoses')
    
    def load_labevents(self, nrows: Optional[int] = None) -> pd.DataFrame:
        """
        Load laboratory events.
        
        Returns columns:
        - subject_id, hadm_id, itemid, charttime, value, valueuom
        """
        return self._load_file('labevents', nrows)
    
    def load_d_labitems(self) -> pd.DataFrame:
        """Load lab item reference table (itemid -> label)."""
        return self._load_file('d_labitems')
    
    def get_icu_admissions(self, min_icu_duration_hours: int = 6) -> pd.DataFrame:
        """
        Extract ICU admissions from MIMIC.
        
        Parameters
        ----------
        min_icu_duration_hours : int
            Filter out ICU stays shorter than this duration
        
        Returns
        -------
        pd.DataFrame
            Subset of admissions with ICU stay info
        """
        # Note: In MIMIC-IV, you'd typically load icu/icustays.csv.gz
        # For now, we identify ICU admissions by presence of waveform data
        # This will be enhanced when waveform module is active
        
        admissions = self.load_admissions()
        admissions['admittime'] = pd.to_datetime(admissions['admittime'])
        admissions['dischtime'] = pd.to_datetime(admissions['dischtime'])
        admissions['icu_duration_hours'] = (
            (admissions['dischtime'] - admissions['admittime']).dt.total_seconds() / 3600
        )
        
        icu_admits = admissions[
            admissions['icu_duration_hours'] >= min_icu_duration_hours
        ].copy()
        
        return icu_admits.reset_index(drop=True)
    
    def get_patient_sepsis_diagnosis(self, subject_id: int) -> Dict:
        """
        Check if patient has sepsis diagnosis.
        
        Parameters
        ----------
        subject_id : int
            MIMIC subject ID
        
        Returns
        -------
        dict
            {'has_sepsis': bool, 'icd_codes': list, 'admission_ids': list}
        """
        diagnoses = self.load_diagnoses()
        icd_ref = self.load_d_icd_diagnoses()
        
        patient_diags = diagnoses[diagnoses['subject_id'] == subject_id]
        
        # Map to ICD codes
        patient_icd_codes = patient_diags['icd_code'].unique().tolist()
        sepsis_codes_found = [c for c in patient_icd_codes if c in self.SEPSIS_CODES]
        
        return {
            'has_sepsis': len(sepsis_codes_found) > 0,
            'sepsis_codes': sepsis_codes_found,
            'icd_codes': patient_icd_codes,
            'admission_ids': patient_diags['hadm_id'].unique().tolist()
        }
    
    def get_sofa_components_from_labs(
        self, 
        hadm_id: int, 
        start_time: datetime,
        end_time: Optional[datetime] = None,
        window_hours: int = 24
    ) -> Dict:
        """
        Extract SOFA score components from laboratory values.
        
        SOFA components:
        - Respiratory: PaO2/FiO2 ratio (requires ABG + ventilator data)
        - Coagulation: Platelet count
        - Liver: Bilirubin
        - Cardiovascular: MAP + vasopressor use
        - CNS: Glasgow Coma Scale
        - Renal: Creatinine, UO
        
        Parameters
        ----------
        hadm_id : int
            Hospital admission ID
        start_time : datetime
            Start of assessment window
        end_time : datetime, optional
            End of assessment window (default: start_time + window_hours)
        window_hours : int
            Default window duration if end_time not provided
        
        Returns
        -------
        dict
            SOFA component values and scores
        """
        if end_time is None:
            end_time = start_time + timedelta(hours=window_hours)
        
        labevents = self.load_labevents()
        d_labitems = self.load_d_labitems()
        
        # Get labs for this admission in time window
        labs = labevents[
            (labevents['hadm_id'] == hadm_id) &
            (pd.to_datetime(labevents['charttime']) >= start_time) &
            (pd.to_datetime(labevents['charttime']) <= end_time)
        ].copy()
        
        # Map itemid to label
        labs = labs.merge(d_labitems[['itemid', 'label']], on='itemid', how='left')
        
        sofa_labs = {}
        
        # Extract key SOFA-relevant labs
        for label in ['Platelets', 'Bilirubin', 'Creatinine']:
            subset = labs[labs['label'].str.contains(label, case=False, na=False)]
            if not subset.empty:
                values = pd.to_numeric(subset['value'], errors='coerce').dropna()
                if not values.empty:
                    sofa_labs[label.lower()] = {
                        'mean': values.mean(),
                        'min': values.min(),
                        'max': values.max(),
                        'count': len(values)
                    }
        
        return sofa_labs
    
    def filter_cohort(
        self,
        min_age: int = 18,
        max_age: int = 120,
        min_icu_hours: int = 6,
        require_sepsis: bool = False,
        ethnicity_filter: Optional[list] = None
    ) -> pd.DataFrame:
        """
        Define and filter patient cohort based on criteria.
        
        Parameters
        ----------
        min_age : int
            Minimum age at admission (computed from DOB)
        max_age : int
            Maximum age
        min_icu_hours : int
            Minimum ICU stay duration
        require_sepsis : bool
            Only include patients with sepsis diagnosis
        ethnicity_filter : list, optional
            Include only specific ethnicities
        
        Returns
        -------
        pd.DataFrame
            Filtered cohort (subject_id, hadm_id, age, gender, etc.)
        """
        admissions = self.get_icu_admissions(min_icu_duration_hours=min_icu_hours)
        
        # Filter by ethnicity if specified
        if ethnicity_filter:
            admissions = admissions[
                admissions['ethnicity'].isin(ethnicity_filter)
            ]
        
        # Filter by sepsis if required
        if require_sepsis:
            diagnoses = self.load_diagnoses()
            sepsis_patients = diagnoses[
                diagnoses['icd_code'].isin(self.SEPSIS_CODES)
            ]['subject_id'].unique()
            admissions = admissions[admissions['subject_id'].isin(sepsis_patients)]
        
        cohort = admissions[[
            'subject_id', 'hadm_id', 'admittime', 'dischtime', 
            'admission_type', 'ethnicity'
        ]].copy()
        
        cohort['icu_duration_hours'] = admissions['icu_duration_hours'].values
        
        return cohort.reset_index(drop=True)
