"""
Feature Extraction from Continuous Waveform Data

Computes clinical features required for trajectory modeling:
- HRV (time/freq domain)
- Arterial pressure variability
- Waveform morphology (ECG, ABP, PPG)
- Feature aggregation (mean, median, SD, slope, CV)
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional, List
from scipy import signal as scipy_signal
from scipy.stats import skew, kurtosis
from datetime import datetime, timedelta
import warnings


class HRVFeatureExtractor:
    """Extract Heart Rate Variability features from ECG."""
    
    @staticmethod
    def extract_rr_intervals(
        ecg_signal: np.ndarray,
        sampling_rate: int,
        method: str = 'derivative'
    ) -> np.ndarray:
        """
        Extract RR intervals (inter-beat intervals) from ECG.
        
        Parameters
        ----------
        ecg_signal : np.ndarray
            ECG waveform
        sampling_rate : int
            Sampling rate in Hz
        method : str
            Peak detection method ('derivative' or 'scipy')
        
        Returns
        -------
        rr_intervals : np.ndarray
            RR intervals in milliseconds
        """
        if method == 'scipy':
            # Use scipy's find_peaks for R-wave detection
            # Derivative to enhance QRS
            ecg_diff = np.diff(ecg_signal)
            ecg_squared = ecg_diff ** 2
            
            # Moving average filter
            window = int(0.05 * sampling_rate)
            if window < 1:
                window = 1
            ecg_filtered = np.convolve(
                ecg_squared,
                np.ones(window) / window,
                mode='same'
            )
            
            threshold = np.mean(ecg_filtered) + np.std(ecg_filtered)
            r_peaks, _ = scipy_signal.find_peaks(
                ecg_filtered,
                height=threshold * 0.5,
                distance=int(0.3 * sampling_rate)  # Min 300ms between beats
            )
        else:  # derivative method
            # Pan-Tompkins-like algorithm
            # Differentiate to detect slopes
            diff = np.diff(ecg_signal)
            diff_squared = diff ** 2
            
            # Integration window (moving average)
            window_size = int(0.15 * sampling_rate)
            integrated = np.convolve(
                diff_squared,
                np.ones(window_size) / window_size,
                mode='same'
            )
            
            # Find peaks
            threshold = np.mean(integrated) + 2 * np.std(integrated)
            r_peaks, _ = scipy_signal.find_peaks(
                integrated,
                height=threshold,
                distance=int(0.3 * sampling_rate)
            )
        
        if len(r_peaks) < 2:
            warnings.warn("Insufficient R-peaks detected for RR interval computation")
            return np.array([])
        
        # Compute RR intervals in ms
        rr_intervals = np.diff(r_peaks) * 1000 / sampling_rate
        
        return rr_intervals
    
    @staticmethod
    def time_domain_hrv(rr_intervals: np.ndarray) -> Dict[str, float]:
        """
        Compute time-domain HRV features.
        
        Features:
        - mean_rr: Average RR interval (ms)
        - sdnn: Standard deviation of NN intervals
        - rmssd: Root mean square of successive RR differences
        - pnn50: Percentage of successive RR intervals > 50ms
        - mean_hr: Mean heart rate (bpm)
        
        Parameters
        ----------
        rr_intervals : np.ndarray
            RR intervals in milliseconds
        
        Returns
        -------
        dict
            Time-domain HRV features
        """
        if len(rr_intervals) < 2:
            return {
                'mean_rr': np.nan,
                'sdnn': np.nan,
                'rmssd': np.nan,
                'pnn50': np.nan,
                'mean_hr': np.nan,
            }
        
        rr = rr_intervals[~np.isnan(rr_intervals)]
        
        if len(rr) < 2:
            return {
                'mean_rr': np.nan,
                'sdnn': np.nan,
                'rmssd': np.nan,
                'pnn50': np.nan,
                'mean_hr': np.nan,
            }
        
        # Basic statistics
        mean_rr = float(np.mean(rr))
        sdnn = float(np.std(rr))
        
        # RMSSD: root mean square of successive differences
        successive_diffs = np.diff(rr)
        rmssd = float(np.sqrt(np.mean(successive_diffs ** 2)))
        
        # pNN50: percentage of intervals differing > 50ms
        pnn50 = float(100 * np.sum(np.abs(successive_diffs) > 50) / len(successive_diffs))
        
        # Mean heart rate
        mean_hr = float(60000 / mean_rr)
        
        return {
            'mean_rr': mean_rr,
            'sdnn': sdnn,
            'rmssd': rmssd,
            'pnn50': pnn50,
            'mean_hr': mean_hr,
        }
    
    @staticmethod
    def frequency_domain_hrv(
        rr_intervals: np.ndarray,
        sampling_rate_hz: float = 4.0,
        method: str = 'fft'
    ) -> Dict[str, float]:
        """
        Compute frequency-domain HRV features.
        
        Features:
        - lf_power: Low frequency power (0.04-0.15 Hz)
        - hf_power: High frequency power (0.15-0.4 Hz)
        - lf_hf_ratio: LF/HF ratio
        - total_power: Total spectral power
        
        Parameters
        ----------
        rr_intervals : np.ndarray
            RR intervals in milliseconds
        sampling_rate_hz : float
            Effective sampling rate for RR series (default 4 Hz)
        method : str
            'fft' or 'welch' (Welch's method)
        
        Returns
        -------
        dict
            Frequency-domain HRV features
        """
        if len(rr_intervals) < 10:
            return {
                'lf_power': np.nan,
                'hf_power': np.nan,
                'lf_hf_ratio': np.nan,
                'total_power': np.nan,
            }
        
        rr = rr_intervals[~np.isnan(rr_intervals)]
        
        # Detrend
        rr_detrended = scipy_signal.detrend(rr)
        
        if method == 'fft':
            # FFT
            n = len(rr_detrended)
            freqs = np.fft.rfftfreq(n, d=1/sampling_rate_hz)
            psd = np.abs(np.fft.rfft(rr_detrended)) ** 2 / (n * sampling_rate_hz)
        else:  # welch
            freqs, psd = scipy_signal.welch(
                rr_detrended,
                fs=sampling_rate_hz,
                nperseg=min(256, len(rr_detrended))
            )
        
        # Integrate in frequency bands
        vlf_mask = (freqs >= 0.003) & (freqs < 0.04)
        lf_mask = (freqs >= 0.04) & (freqs < 0.15)
        hf_mask = (freqs >= 0.15) & (freqs < 0.4)
        
        vlf_power = float(np.trapz(psd[vlf_mask], freqs[vlf_mask])) if np.any(vlf_mask) else 0
        lf_power = float(np.trapz(psd[lf_mask], freqs[lf_mask])) if np.any(lf_mask) else 0
        hf_power = float(np.trapz(psd[hf_mask], freqs[hf_mask])) if np.any(hf_mask) else 0
        
        total_power = vlf_power + lf_power + hf_power
        lf_hf_ratio = float(lf_power / hf_power) if hf_power > 0 else np.nan
        
        return {
            'lf_power': lf_power,
            'hf_power': hf_power,
            'lf_hf_ratio': lf_hf_ratio,
            'total_power': total_power,
            'vlf_power': vlf_power,
        }


class ABPFeatureExtractor:
    """Extract features from Arterial Blood Pressure waveform."""
    
    @staticmethod
    def detect_systolic_diastolic(
        abp_signal: np.ndarray,
        sampling_rate: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Detect systolic and diastolic points in ABP waveform.
        
        Returns
        -------
        systolic_values : np.ndarray
            Systolic BP values (mmHg)
        diastolic_values : np.ndarray
            Diastolic BP values (mmHg)
        """
        # Expected beat period (assuming HR ~60-120 bpm)
        min_period_samples = int(0.3 * sampling_rate)  # 300ms
        
        # Find systolic peaks
        systolic_indices, _ = scipy_signal.find_peaks(
            abp_signal,
            distance=min_period_samples
        )
        
        # Find diastolic troughs
        diastolic_indices, _ = scipy_signal.find_peaks(
            -abp_signal,
            distance=min_period_samples
        )
        
        systolic_values = abp_signal[systolic_indices]
        diastolic_values = abp_signal[diastolic_indices]
        
        return systolic_values, diastolic_values
    
    @staticmethod
    def compute_bp_variability(
        abp_signal: np.ndarray,
        sampling_rate: int
    ) -> Dict[str, float]:
        """
        Compute BP variability metrics.
        
        Returns
        -------
        dict with keys:
        - systolic_mean, systolic_sd
        - diastolic_mean, diastolic_sd
        - pulse_pressure_mean, pulse_pressure_sd
        - map (mean arterial pressure)
        """
        systolic, diastolic = ABPFeatureExtractor.detect_systolic_diastolic(
            abp_signal, sampling_rate
        )
        
        if len(systolic) < 2 or len(diastolic) < 2:
            return {
                'systolic_mean': np.nan,
                'systolic_sd': np.nan,
                'diastolic_mean': np.nan,
                'diastolic_sd': np.nan,
                'pulse_pressure_mean': np.nan,
                'pulse_pressure_sd': np.nan,
                'map': np.nan,
            }
        
        systolic_mean = float(np.mean(systolic))
        systolic_sd = float(np.std(systolic))
        diastolic_mean = float(np.mean(diastolic))
        diastolic_sd = float(np.std(diastolic))
        
        pp = systolic - diastolic
        pp_mean = float(np.mean(pp))
        pp_sd = float(np.std(pp))
        
        # MAP = (Sys + 2*Dia) / 3
        map_val = float((systolic_mean + 2 * diastolic_mean) / 3)
        
        return {
            'systolic_mean': systolic_mean,
            'systolic_sd': systolic_sd,
            'diastolic_mean': diastolic_mean,
            'diastolic_sd': diastolic_sd,
            'pulse_pressure_mean': pp_mean,
            'pulse_pressure_sd': pp_sd,
            'map': map_val,
        }
    
    @staticmethod
    def compute_dpdt(
        abp_signal: np.ndarray,
        sampling_rate: int
    ) -> Tuple[float, float]:
        """
        Compute dP/dt (rate of pressure rise) during systolic upstroke.
        
        dP/dt is an indicator of contractility.
        
        Returns
        -------
        dpdt_mean : float
            Mean dP/dt across systolic upstrokes
        dpdt_sd : float
            Standard deviation of dP/dt
        """
        # Differentiate to get dP/dt
        dpdt = np.diff(abp_signal) * sampling_rate  # mmHg/sec
        
        # Find systolic upstroke regions (positive dP/dt)
        systolic_dpdt = dpdt[dpdt > 0]
        
        if len(systolic_dpdt) < 1:
            return np.nan, np.nan
        
        return float(np.mean(systolic_dpdt)), float(np.std(systolic_dpdt))
    
    @staticmethod
    def detect_dicrotic_notch(
        abp_signal: np.ndarray,
        sampling_rate: int
    ) -> float:
        """
        Detect presence and amplitude of dicrotic notch.
        
        The dicrotic notch is a small dip in the ABP waveform during
        diastole, indicating aortic valve closure.
        
        Returns
        -------
        fraction_with_notch : float
            Fraction of beats with detectable dicrotic notch (0-1)
        """
        # Find systolic peaks and subsequent troughs
        systolic_idx, _ = scipy_signal.find_peaks(abp_signal)
        
        notch_count = 0
        for sys_idx in systolic_idx[:-1]:
            next_sys = systolic_idx[systolic_idx > sys_idx].min() \
                if np.any(systolic_idx > sys_idx) else len(abp_signal)
            
            # Region between systolic peaks
            segment = abp_signal[sys_idx:next_sys]
            
            # Look for local minimum (dicrotic notch) in middle part
            if len(segment) > 20:
                mid_start = len(segment) // 3
                mid_end = 2 * len(segment) // 3
                mid_segment = segment[mid_start:mid_end]
                
                if len(mid_segment) > 0 and np.min(mid_segment) < segment[0]:
                    notch_count += 1
        
        if len(systolic_idx) > 1:
            return float(notch_count / (len(systolic_idx) - 1))
        return 0.0


class PPGFeatureExtractor:
    """Extract features from Photoplethysmogram (PPG)."""
    
    @staticmethod
    def compute_perfusion_index(
        ppg_signal: np.ndarray
    ) -> float:
        """
        Compute Perfusion Index (PI).
        
        PI = (AC amplitude) / (DC level) * 100
        where AC is the pulsatile component and DC is the baseline.
        
        Returns
        -------
        pi : float
            Perfusion index (0-100+)
        """
        # Detrend to separate AC (pulsatile) from DC (baseline)
        ppg_detrended = scipy_signal.detrend(ppg_signal)
        dc_level = np.mean(ppg_signal)
        ac_amplitude = np.std(ppg_detrended)
        
        if dc_level == 0:
            return 0.0
        
        pi = float((ac_amplitude / dc_level) * 100)
        return pi
    
    @staticmethod
    def compute_ppg_morphology(
        ppg_signal: np.ndarray
    ) -> Dict[str, float]:
        """
        Compute PPG waveform morphology features.
        
        Returns
        -------
        dict with keys:
        - skewness: Waveform skewness
        - kurtosis: Waveform kurtosis
        - crest_factor: Peak-to-RMS ratio
        """
        ppg_clean = ppg_signal[~np.isnan(ppg_signal)]
        
        if len(ppg_clean) < 3:
            return {
                'skewness': np.nan,
                'kurtosis': np.nan,
                'crest_factor': np.nan,
            }
        
        skewness_val = float(skew(ppg_clean))
        kurtosis_val = float(kurtosis(ppg_clean))
        
        # Crest factor = peak value / RMS
        rms = float(np.sqrt(np.mean(ppg_clean ** 2)))
        peak = float(np.max(np.abs(ppg_clean)))
        crest_factor = peak / rms if rms > 0 else np.nan
        
        return {
            'skewness': skewness_val,
            'kurtosis': kurtosis_val,
            'crest_factor': crest_factor,
        }


class ECGfeatureExtractor:
    """Extract morphological features from ECG."""
    
    @staticmethod
    def detect_qrs_complex(
        ecg_signal: np.ndarray,
        sampling_rate: int
    ) -> List[Tuple[int, int, int]]:
        """
        Detect QRS complexes and estimate Q, R, S positions.
        
        Returns
        -------
        list of (q_idx, r_idx, s_idx)
            Indices of Q, R, S peaks for each beat
        """
        # Differentiate and square for QRS detection
        diff = np.diff(ecg_signal)
        squared = diff ** 2
        
        # Moving average filter
        window = int(0.08 * sampling_rate)
        if window < 1:
            window = 1
        filtered = np.convolve(squared, np.ones(window) / window, mode='same')
        
        # Find R-waves (local maxima)
        r_peaks, _ = scipy_signal.find_peaks(
            filtered,
            distance=int(0.3 * sampling_rate)
        )
        
        qrs_complexes = []
        
        for r_idx in r_peaks:
            # Search for Q (negative) and S (negative) around R
            window_size = int(0.1 * sampling_rate)
            search_start = max(0, r_idx - window_size)
            search_end = min(len(ecg_signal), r_idx + window_size)
            
            segment = ecg_signal[search_start:search_end]
            
            # Q is minimum before R
            q_rel = np.argmin(segment[:r_idx - search_start])
            q_idx = search_start + q_rel
            
            # S is minimum after R
            s_rel = np.argmin(segment[r_idx - search_start:]) + (r_idx - search_start)
            s_idx = search_start + s_rel
            
            qrs_complexes.append((q_idx, r_idx, s_idx))
        
        return qrs_complexes
    
    @staticmethod
    def compute_qrs_width(
        ecg_signal: np.ndarray,
        sampling_rate: int
    ) -> float:
        """
        Compute QRS complex duration (width) in milliseconds.
        
        Normal: < 120ms. Widened QRS (>120ms) indicates conduction delays.
        """
        qrs_list = ECGfeatureExtractor.detect_qrs_complex(ecg_signal, sampling_rate)
        
        if not qrs_list:
            return np.nan
        
        widths_samples = [s - q for q, r, s in qrs_list]
        widths_ms = [w * 1000 / sampling_rate for w in widths_samples]
        
        return float(np.mean(widths_ms))
    
    @staticmethod
    def compute_qt_interval(
        ecg_signal: np.ndarray,
        sampling_rate: int,
        correct: bool = True,
        heart_rate: Optional[float] = None
    ) -> float:
        """
        Compute QT interval (time from Q to end of T wave).
        
        Parameters
        ----------
        ecg_signal : np.ndarray
            ECG waveform
        sampling_rate : int
            Sampling rate
        correct : bool
            If True, compute corrected QT (QTc)
        heart_rate : float, optional
            Heart rate in bpm (needed for QTc correction)
        
        Returns
        -------
        qt_ms : float
            QT interval in milliseconds (or QTc if correct=True)
        """
        # This is a simplified version; full QT measurement requires
        # detecting T-wave end, which is complex
        
        qrs_list = ECGfeatureExtractor.detect_qrs_complex(ecg_signal, sampling_rate)
        
        if not qrs_list or not heart_rate:
            return np.nan
        
        # Rough estimate: QT proportional to RR interval
        rr_ms = 60000 / heart_rate
        
        # Bazett's formula: QTc = QT / sqrt(RR)
        estimated_qt = rr_ms * 0.4  # Rough estimate
        qtc = estimated_qt / np.sqrt(rr_ms / 1000) if correct else estimated_qt
        
        return float(qtc)
    
    @staticmethod
    def compute_twave_amplitude(
        ecg_signal: np.ndarray,
        sampling_rate: int
    ) -> float:
        """Estimate T-wave amplitude (requires T-wave detection)."""
        qrs_list = ECGfeatureExtractor.detect_qrs_complex(ecg_signal, sampling_rate)
        
        if not qrs_list:
            return np.nan
        
        t_amplitudes = []
        
        for q_idx, r_idx, s_idx in qrs_list[:-1]:
            next_q = qrs_list[qrs_list > s_idx][0] if np.any(qrs_list > s_idx) \
                else len(ecg_signal)
            
            # T-wave region: after S, before next QRS
            t_region = ecg_signal[s_idx:int((s_idx + next_q) * 0.7)]
            
            # Find max amplitude in this region
            if len(t_region) > 1:
                t_amp = np.max(np.abs(t_region))
                t_amplitudes.append(t_amp)
        
        if t_amplitudes:
            return float(np.mean(t_amplitudes))
        return np.nan



class FeatureAggregator:
    """Aggregate features across multiple windows for patient-level trajectories."""
    
    @staticmethod
    def compute_trajectory_features(
        windowed_features: List[Dict],
        feature_name: str,
        window_times: Optional[List[datetime]] = None
    ) -> Dict[str, float]:
        """
        Aggregate a single feature across time windows.
        
        Parameters
        ----------
        windowed_features : list of dict
            Feature values for each window
        feature_name : str
            Name of feature to aggregate
        window_times : list of datetime, optional
            Timestamps for each window (for trend calculation)
        
        Returns
        -------
        dict
            Aggregated statistics (mean, median, sd, slope, cv)
        """
        values = []
        for w in windowed_features:
            if feature_name in w and not np.isnan(w[feature_name]):
                values.append(w[feature_name])
        
        if not values:
            return {
                'mean': np.nan,
                'median': np.nan,
                'sd': np.nan,
                'min': np.nan,
                'max': np.nan,
                'cv': np.nan,
                'slope': np.nan,
            }
        
        values = np.array(values)
        agg = {
            'mean': float(np.mean(values)),
            'median': float(np.median(values)),
            'sd': float(np.std(values)),
            'min': float(np.min(values)),
            'max': float(np.max(values)),
        }
        
        # Coefficient of variation
        if agg['mean'] != 0:
            agg['cv'] = float(agg['sd'] / agg['mean'])
        else:
            agg['cv'] = np.nan
        
        # Linear trend (slope) over time
        if window_times and len(window_times) == len(values):
            time_hours = np.array([
                (t - window_times[0]).total_seconds() / 3600
                for t in window_times
            ])
            slope = np.polyfit(time_hours, values, 1)[0]
            agg['slope'] = float(slope)
        else:
            # Slope based on window index
            x = np.arange(len(values))
            if len(x) > 1:
                slope = np.polyfit(x, values, 1)[0]
                agg['slope'] = float(slope)
            else:
                agg['slope'] = np.nan
        
        return agg
    
    @staticmethod
    def create_patient_feature_matrix(
        all_windowed_features: List[Dict],
        feature_list: Optional[List[str]] = None
    ) -> Tuple[pd.DataFrame, List[str]]:
        """
        Create a matrix of patient-level features for trajectory modeling.
        
        Parameters
        ----------
        all_windowed_features : list of dict
            Feature dicts from all windows for a patient
        feature_list : list, optional
             Features to extract (default: all keys from first dict)
        
        Returns
        -------
        feature_matrix : pd.DataFrame
            (n_features, n_aggregations) with aggregated stats
        feature_names : list
            Names of features in the matrix
        """
        if not all_windowed_features:
            return pd.DataFrame(), []
        
        if feature_list is None:
            feature_list = [k for k in all_windowed_features[0].keys()
                           if k not in ['quality', 'start_sec', 'end_sec']]
        
        matrix_data = {}
        
        for feat in feature_list:
            agg = FeatureAggregator.compute_trajectory_features(
                all_windowed_features,
                feat
            )
            for agg_type, value in agg.items():
                col_name = f"{feat}_{agg_type}"
                matrix_data[col_name] = value
        
        matrix_df = pd.DataFrame([matrix_data])
        feature_names = list(matrix_data.keys())
        
        return matrix_df, feature_names
