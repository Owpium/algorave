"""t2s_params — hand-tuned constants of the track2strudel pipeline, in one place (defaults = v2.4).

Values are injectable without touching the code:
  - env  T2S_PARAMS="CLAP_R_MID=1.3,SWING_MIN=0.05"     (inherited by the extract_samples / extract_loops subprocesses)
  - env  T2S_PARAM_CLAP_R_MID=1.3                        (one per variable; wins over T2S_PARAMS)
  - CLI  --param CLAP_R_MID=1.3   (track2strudel.py, t2s.py, check_golden.py: repeatable; written to T2S_PARAMS)
Bounds = sane search range for the future auto-tuning; a value outside them is refused (typo guard).
The T2S_NO_* switches (rumble, tile, stepfit...) stay separate env flags (see track2strudel_README.md).

    python tools\\t2s_params.py          # table of the parameters (default, bounds, module, meaning)
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Param:
    default: float
    lo: float
    hi: float
    module: str
    doc: str


PARAMS = {
    # --- track2strudel.py
    "MIN_CONF": Param(0.6, 0.3, 0.9, "track2strudel", "loop confidence under which a lane is emitted commented-out"),
    "CLAP_R_MID": Param(1.25, 1.05, 2.0, "track2strudel", "clap 2&4: 1-3 kHz flux ratio beats 2&4 vs 1&3"),
    "CLAP_R_HI": Param(1.5, 1.1, 2.5, "track2strudel", "clap 2&4: 3-7 kHz flux ratio (stricter, hats live there)"),
    "CLAP_MIN_LEVEL": Param(0.15, 0.05, 0.4, "track2strudel", "clap 2&4: band flux of the 16th >= this x the loudest 16th"),
    "PHASE_FLIP_R": Param(1.4, 1.1, 2.5, "track2strudel", "bar phase flipped by 1 beat if clap energy on 1&3 > this x 2&4"),
    "OPEN_HAT_RATIO": Param(0.35, 0.2, 0.6, "track2strudel", "hat = open if >7 kHz decay ratio above this"),
    "BANDPERC_DB": Param(10.0, 6.0, 16.0, "track2strudel", "band perc: 800-6000 Hz level of a 16th over its median (dB)"),
    "BANDPERC_RANGE_DB": Param(12.0, 6.0, 20.0, "track2strudel", "band perc: 16th level >= loudest median - this (dB)"),
    "BANDPERC_MIN_BARS": Param(4, 2, 8, "track2strudel", "band perc: consecutive bars needed"),
    "SWING_MIN": Param(0.06, 0.03, 0.12, "track2strudel", "swing: min odd-16th delay (step)"),
    "SWING_CONS": Param(0.6, 0.4, 0.9, "track2strudel", "swing: share of odd hits late"),
    "SWING_BARS_CONS": Param(0.7, 0.4, 0.95, "track2strudel", "swing: share of bars showing it"),
    "LANE_MIN_SHARE": Param(0.25, 0.1, 0.5, "track2strudel", "lane kept if active in >= this share of the main-groove bars"),
    "VARIANT_DB": Param(8.0, 4.0, 14.0, "track2strudel", "bar variant: lane band level vs that 16th's median (dB) to confirm a flip"),
    "VEL_MIN_RANGE_DB": Param(1.0, 0.5, 3.0, "track2strudel", ".velocity emitted when the p90-p10 per-bar range >= this (dB)"),
    "LEAD_MIN_CONF": Param(0.8, 0.5, 0.95, "track2strudel", "lead emitted if rhythm conf >= this"),
    "LEAD_MIN_PITCH_CONF": Param(0.6, 0.3, 0.9, "track2strudel", "lead emitted if pitch agreement >= this"),
    # --- extract_samples.py
    "RUMBLE_MIN_COH": Param(0.8, 0.6, 0.95, "extract_samples", "kick+rumble lane: bass stem per-beat coherence < 400 Hz"),
    "RUMBLE_MAX_BELOW_DB": Param(12.0, 6.0, 20.0, "extract_samples", "kick+rumble lane: bass at most this under the drums < 400 Hz (dB)"),
    "HF_LOSS_DB": Param(1.5, 0.5, 4.0, "extract_samples", "6-hit mean losing more than this > 4 kHz -> medoid / hybrid one-shot (dB)"),
    "SPLIT_RATIO": Param(2.2, 1.5, 4.0, "extract_samples", "timbre change point: between / within distance of per-bar spectra"),
    "ADD_THR": Param(0.15, 0.05, 0.4, "extract_samples", "NNLS: 16th added when its fitted gain >= this x the loudest 16th"),
    "MIN_STEP_GAIN": Param(0.01, 0.001, 0.05, "extract_samples", "NNLS: fitted 16ths under this are removed"),
    "ADD_MIN_EXPLAINED": Param(0.8, 0.5, 0.95, "extract_samples", "NNLS: adds only when the lane explains >= this of its band"),
    "MIN_EXPLAINED": Param(0.10, 0.02, 0.3, "extract_samples", "NNLS: lane explaining less of its band is left commented"),
    # --- extract_loops.py
    "LOOP_VOX_MIN_DB": Param(-24.0, -32.0, -18.0, "extract_loops", "vox bar active if stem RMS vs mix > this (dB)"),
    "LOOP_OTHER_MIN_DB": Param(-26.0, -34.0, -18.0, "extract_loops", "other bar active if stem RMS vs mix > this (dB)"),
    "LOOP_OTHER_QUIET_DB": Param(-36.0, -44.0, -28.0, "extract_loops", "same, when basic-pitch found a consistent pitched loop"),
}


class _P:
    """Attribute access to the current values (P.MIN_CONF). Mutable through apply()."""

    def __init__(self):
        self._v = {k: p.default for k, p in PARAMS.items()}
        self.overrides = {}

    def __getattr__(self, k):
        try:
            return self.__dict__["_v"][k]
        except KeyError:
            raise AttributeError(k) from None


def _cast(name, raw):
    if name not in PARAMS:
        raise SystemExit(f"t2s_params: unknown parameter {name!r} (python tools\\t2s_params.py lists them)")
    p = PARAMS[name]
    try:
        v = int(raw) if isinstance(p.default, int) else float(raw)
    except ValueError:
        raise SystemExit(f"t2s_params: {name}={raw!r} is not a number") from None
    if not (p.lo <= v <= p.hi):
        raise SystemExit(f"t2s_params: {name}={v} outside its bounds [{p.lo}, {p.hi}]")
    return v


def parse(items):
    """['A=1', 'B=2'] or 'A=1,B=2' -> {A: 1.0, B: 2.0} (validated)."""
    if isinstance(items, str):
        items = [x for x in items.split(",") if x.strip()]
    out = {}
    for it in items or []:
        if "=" not in it:
            raise SystemExit(f"t2s_params: expected NAME=VALUE, got {it!r}")
        k, v = it.split("=", 1)
        k = k.strip().upper()
        out[k] = _cast(k, v.strip())
    return out


def from_env():
    ov = parse(os.environ.get("T2S_PARAMS", ""))
    for k in PARAMS:
        if f"T2S_PARAM_{k}" in os.environ:
            ov[k] = _cast(k, os.environ[f"T2S_PARAM_{k}"])
    return ov


def apply(overrides):
    """Set values in P and in the environment (so subprocesses get them too)."""
    if not overrides:
        return
    P._v.update(overrides)
    P.overrides.update(overrides)
    os.environ["T2S_PARAMS"] = ",".join(f"{k}={v}" for k, v in sorted(P.overrides.items()))


def effective():
    """Only the values that differ from v2.4 (for cache keys / analysis.json)."""
    return {k: v for k, v in P._v.items() if v != PARAMS[k].default}


P = _P()
apply(from_env())


if __name__ == "__main__":
    print(f"{'name':22s} {'default':>8s} {'lo':>7s} {'hi':>7s}  module           meaning")
    for k, p in PARAMS.items():
        cur = P._v[k]
        mark = f"  (now {cur})" if cur != p.default else ""
        print(f"{k:22s} {p.default:>8g} {p.lo:>7g} {p.hi:>7g}  {p.module:16s} {p.doc}{mark}")
