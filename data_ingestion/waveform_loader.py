"""
Waveform Data Loader

Loads continuous physiological waveforms (ECG, ABP, PPG, respiratory signals)
from MIMIC-IV and other sources. Handles WFDB format parsing and signal quality checks.
"""

import os
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional, Tuple, List, Dict
from datetime import datetime, timedelta
import warnings


class WaveformLoader:
    """Load and manage continuous physiological waveform data."""
    
    # Standard sampling rates (Hz) for different signal types
    STANDARD_SAMPLING_RATES = {
        'ecg': 250,
        'abp': 100,
        'ppg': 100,
        'respiratory': 20,
        'spo2': 1,
    }
    
    # Quality thresholds
    MIN_SIGNAL_DURATION_SEC = 300  # 5 minutes minimum
    MAX_MISSING_FRACTION = 0.2  # Allow up to 20% missing data
    
    def __init__(self, waveform_root: Optional[str] = None, verbose: bool = True):
        """
        Parameters
        ----------
        waveform_root : str, optional
            Path to MIMIC-IV waveforms directory
            (e.g., '/data/physionet.org/files/mimiciv/3.1/icu/waveforms')
        verbose : bool
            Print progress information
        """
        self.waveform_root = Path(waveform_root) if waveform_root else None
        self.verbose = verbose
        
        if self.waveform_root and not self.waveform_root.exists():
            warnings.warn(f"Waveform root not found: {waveform_root}. "
                         "Waveform data will not be available until downloaded.")
    
    def is_available(self) -> bool:
        """Check if waveform data has been downloaded."""
        return self.waveform_root is not None and self.waveform_root.exists()
    
    def load_wfdb_record(
        self,
        record_path: str,
        signal_name: Optional[str] = None,
        start_sec: float = 0,
        duration_sec: Optional[float] = None,
        resample_hz: Optional[int] = None
    ) -> Tuple[np.ndarray, int, Dict]:
        """
        Load a WFDB record and optionally extract a specific signal.
        
        Parameters
        ----------
        record_path : str
            Path to WFDB record (without extension)
        signal_name : str, optional
            Specific signal to extract (e.g., 'ECG', 'ABP', 'PPG')
        start_sec : float
            Start time in seconds for extraction window
        duration_sec : float, optional
            Duration in seconds (None = entire record)
        resample_hz : int, optional
            Resample to this frequency
        
        Returns
        -------
        signal : np.ndarray
            Extracted signal
        sampling_rate : int
            Sampling rate in Hz
        metadata : dict
            Record metadata
        """
        try:
            import wfdb
        except ImportError:
            raise ImportError("pip install wfdb")
        
        # Read header
        header = wfdb.rdheader(record_path)
        metadata = {
            'num_signals': header.n_sig,
            'sampling_rate': header.fs,
            'signal_length': header.sig_len,
            'duration_sec': header.sig_len / header.fs if header.fs else None,
            'signal_names': header.sig_name or [],
        }
        
        # Load full record or segment
        sample_start = int(start_sec * header.fs)
        sample_end = None
        if duration_sec is not None:
            sample_end = int((start_sec + duration_sec) * header.fs)
        
        record = wfdb.rdrecord(
            record_path,
            sampfrom=sample_start,
            sampto=sample_end,
            physical=True  # Get physical units, not raw
        )
        
        # Extract specific signal if requested
        if signal_name:
            sig_idx = None
            for i, name in enumerate(record.sig_name):
                if name.upper() == signal_name.upper():
                    sig_idx = i
                    break
            
            if sig_idx is None:
                raise ValueError(
                    f"Signal '{signal_name}' not found. "
                    f"Available: {record.sig_name}"
                )
            signal = record.p_signal[:, sig_idx]
        else:
            signal = record.p_signal
        
        # Resample if requested
        if resample_hz and resample_hz != header.fs:
            from scipy import signal as scipy_signal
            num_samples = int(len(signal) * resample_hz / header.fs)
            signal = scipy_signal.resample(signal, num_samples)
            metadata['resampled_from_hz'] = header.fs
            header.fs = resample_hz
        
        return signal, header.fs, metadata
    
    def assess_signal_quality(
        self,
        signal: np.ndarray,
        sampling_rate: int,
        signal_type: str = 'ecg'
    ) -> Dict:
        """
        Assess quality of a physiological signal.
        
        Checks for:
        - Signal length >= MIN_SIGNAL_DURATION_SEC
        - Missing/NaN fraction <= MAX_MISSING_FRACTION
        - Variance (dead signal detection)
        - Extreme value check
        
        Parameters
        ----------
        signal : np.ndarray
            1D signal array
        sampling_rate : int
            Sampling rate in Hz
        signal_type : str
            Type of signal ('ecg', 'abp', 'ppg', 'respiratory')
        
        Returns
        -------
        dict
            Quality metrics and pass/fail status
        """
        quality = {
            'signal_type': signal_type,
            'length_samples': len(signal),
            'duration_sec': len(signal) / sampling_rate,
            'sampling_rate_hz': sampling_rate,
        }
        
        # Check minimum length
        if quality['duration_sec'] < self.MIN_SIGNAL_DURATION_SEC:
            quality['passes_length_check'] = False
            return quality
        
        quality['passes_length_check'] = True
        
        # Check for NaN/missing
        nan_count = np.isnan(signal).sum()
        missing_frac = nan_count / len(signal)
        quality['missing_fraction'] = float(missing_frac)
        quality['passes_missing_check'] = missing_frac <= self.MAX_MISSING_FRACTION
        
        # Check variance (dead signal)
        valid_signal = signal[~np.isnan(signal)]
        if len(valid_signal) > 0:
            quality['std_dev'] = float(np.std(valid_signal))
            quality['passes_variance_check'] = quality['std_dev'] > 0.01
        else:
            quality['passes_variance_check'] = False
        
        # Summary
        quality['is_valid'] = all([
            quality.get('passes_length_check', False),
            quality.get('passes_missing_check', False),
            quality.get('passes_variance_check', False),
        ])
        
        return quality
    
    def segment_into_windows(
        self,
        signal: np.ndarray,
        sampling_rate: int,
        window_minutes: int = 5,
        overlap_minutes: int = 0,
        assess_quality: bool = True,
        signal_type: str = 'ecg'
    ) -> List[Dict]:
        """
        Segment a signal into time windows.
        
        Parameters
        ----------
        signal : np.ndarray
            1D signal array
        sampling_rate : int
            Sampling rate in Hz
        window_minutes : int
            Window length in minutes
        overlap_minutes : int
            Overlap between windows in minutes
        assess_quality : bool
            Assess quality of each window
        signal_type : str
            Type of signal for quality assessment
        
        Returns
        -------
        list of dict
            Each dict contains 'signal', 'start_sec', 'end_sec', 'quality'
        """
        window_samples = int(window_minutes * 60 * sampling_rate)
        overlap_samples = int(overlap_minutes * 60 * sampling_rate)
        stride = window_samples - overlap_samples
        
        windows = []
        start_idx = 0
        
        while start_idx + window_samples <= len(signal):
            end_idx = start_idx + window_samples
            window_signal = signal[start_idx:end_idx]
            
            window_dict = {
                'signal': window_signal,
                'start_sec': start_idx / sampling_rate,
                'end_sec': end_idx / sampling_rate,
                'start_sample': start_idx,
                'end_sample': end_idx,
                'sampling_rate': sampling_rate,
            }
            
            if assess_quality:
                window_dict['quality'] = self.assess_signal_quality(
                    window_signal, sampling_rate, signal_type
                )
            
            windows.append(window_dict)
            start_idx += stride
        
        return windows
    
    def synchronize_signals(
        self,
        signals_dict: Dict[str, Tuple[np.ndarray, int]],
        target_sampling_rate: Optional[int] = None,
        align_start_time: bool = True
    ) -> Dict[str, np.ndarray]:
        """
        Synchronize multiple signals to common sampling rate and length.
        
        Useful for computing pulse transit time (ECG→PPG) and other
        cross-signal features.
        
        Parameters
        ----------
        signals_dict : dict
            {signal_name: (signal_array, sampling_rate_hz)}
        target_sampling_rate : int, optional
            Resample all to this rate (default: highest input rate)
        align_start_time : bool
            Trim to same start time
        
        Returns
        -------
        dict
            Synchronized signals, each as np.ndarray
        """
        if target_sampling_rate is None:
            target_sampling_rate = max(sr for _, sr in signals_dict.values())
        
        try:
            from scipy import signal as scipy_signal
        except ImportError:
            raise ImportError("pip install scipy")
        
        synchronized = {}
        min_length_sec = float('inf')
        
        # Resample to target rate and find min duration
        for name, (sig, sr) in signals_dict.items():
            if sr != target_sampling_rate:
                num_samples = int(len(sig) * target_sampling_rate / sr)
                resampled = scipy_signal.resample(sig, num_samples)
            else:
                resampled = sig.copy()
            
            synchronized[name] = resampled
            duration_sec = len(resampled) / target_sampling_rate
            min_length_sec = min(min_length_sec, duration_sec)
        
        # Trim to common length
        if align_start_time:
            common_samples = int(min_length_sec * target_sampling_rate)
            for name in synchronized:
                synchronized[name] = synchronized[name][:common_samples]
        
        return synchronized
    
    def compute_pulse_transit_time(
        self,
        ecg_signal: np.ndarray,
        ppg_signal: np.ndarray,
        sampling_rate: int
    ) -> Tuple[float, Dict]:
        """
        Compute Pulse Transit Time (PTT) from ECG and PPG.
        
        PTT is the time delay between R-wave detection (ECG) and 
        PPG pulse arrival.
        
        Parameters
        ----------
        ecg_signal : np.ndarray
            ECG waveform
        ppg_signal : np.ndarray
            PPG waveform (must be same length and sampling rate)
        sampling_rate : int
            Sampling rate in Hz
        
        Returns
        -------
        ptt_ms : float
            Pulse transit time in milliseconds
        details : dict
            Additional metrics
        """
        try:
            from scipy import signal as scipy_signal
        except ImportError:
            raise ImportError("pip install scipy")
        
        # Simple R-wave detection via QRS complex (derivative + threshold)
        ecg_diff = np.diff(ecg_signal)
        ecg_squared = ecg_diff ** 2
        
        # Apply moving average filter for smoothing
        window = int(0.05 * sampling_rate)  # 50ms window
        if window < 1:
            window = 1
        ecg_filtered = np.convolve(
            ecg_squared, 
            np.ones(window) / window, 
            mode='same'
        )
        
        # Detect peaks (R-waves)
        threshold = np.mean(ecg_filtered) + np.std(ecg_filtered)
        r_peaks, _ = scipy_signal.find_peaks(ecg_filtered, height=threshold)
        
        # For each R-peak, find corresponding PPG peak
        ptts = []
        for r_idx in r_peaks:
            # Look for PPG peak within ±500ms
            search_window = int(0.5 * sampling_rate)
            search_start = max(0, r_idx - search_window)
            search_end = min(len(ppg_signal), r_idx + search_window)
            
            ppg_segment = ppg_signal[search_start:search_end]
            if len(ppg_segment) > 0:
                ppg_peaks, _ = scipy_signal.find_peaks(ppg_segment)
                # Find first PPG peak after R-wave
                for ppg_peak_rel in ppg_peaks:
                    ppg_peak_abs = search_start + ppg_peak_rel
                    if ppg_peak_abs > r_idx:
                        delay_samples = ppg_peak_abs - r_idx
                        delay_ms = 1000 * delay_samples / sampling_rate
                        ptts.append(delay_ms)
                        break
        
        if ptts:
            mean_ptt = float(np.mean(ptts))
            std_ptt = float(np.std(ptts))
        else:
            mean_ptt = np.nan
            std_ptt = np.nan
        
        return mean_ptt, {
            'mean_ms': mean_ptt,
            'std_ms': std_ptt,
            'count': len(ptts),
            'r_peaks_detected': len(r_peaks),
        }


class WaveformMetadata:
    """Manage metadata for waveform records and availability."""
    
    def __init__(self, metadata_csv: Optional[str] = None):
        """
        Parameters
        ----------
        metadata_csv : str, optional
            Path to CSV with waveform availability metadata
        """
        self.metadata_df = None
        if metadata_csv and Path(metadata_csv).exists():
            self.metadata_df = pd.read_csv(metadata_csv)
    
    def get_available_signals(self, record_id: str) -> List[str]:
        """Get list of signals available for a specific record."""
        if self.metadata_df is not None:
            record = self.metadata_df[
                self.metadata_df['record_id'] == record_id
            ]
            if not record.empty:
                if 'signals' in record.columns:
                    return record['signals'].iloc[0].split(',')
        return []
    
    def get_signal_duration(self, record_id: str, signal_name: str) -> float:
        """Get duration (seconds) of a signal."""
        if self.metadata_df is not None:
            record = self.metadata_df[
                (self.metadata_df['record_id'] == record_id) &
                (self.metadata_df['signal'] == signal_name)
            ]
            if not record.empty:
                return record['duration_sec'].iloc[0]
        return None
