"""
bearing_physics.py - bearing fault frequencies from geometry.

A damaged spot on a bearing produces a small impact every time a ball rolls
over it. How often that happens depends only on the bearing's geometry and
the shaft speed, so we can predict the "fault frequencies" with a pencil.
These are the textbook formulas. They assume the outer race is stationary,
the inner race turns with the shaft, and the balls roll without slipping.

Symbols:
    n   = number of balls
    d   = ball diameter
    D   = pitch diameter (diameter of the circle through the ball centres)
    phi = contact angle
    fr  = shaft speed in revolutions per second (Hz) = rpm / 60

    FTF  (cage speed)              = fr/2       * (1 - d/D * cos(phi))
    BPFO (ball pass, outer race)   = n * fr/2   * (1 - d/D * cos(phi))
    BPFI (ball pass, inner race)   = n * fr/2   * (1 + d/D * cos(phi))
    BSF  (ball spin)               = D/(2d) * fr * (1 - (d/D * cos(phi))**2)

Each function below returns a MULTIPLIER: the fault frequency divided by the
shaft speed. Multiply by rpm/60 to get Hz. Multipliers are handy because
they do not change with speed.

Run this file on its own to print a table:
    python -m src.bearing_physics
"""

import math

from src import config


def _ratio(ball_d, pitch_d, contact_angle_deg):
    """The quantity d/D * cos(phi), which appears in every formula."""
    return ball_d / pitch_d * math.cos(math.radians(contact_angle_deg))


def ftf_multiplier(n_balls=config.N_BALLS, ball_d=config.BALL_DIAMETER_MM,
                   pitch_d=config.PITCH_DIAMETER_MM,
                   contact_angle_deg=config.CONTACT_ANGLE_DEG):
    """Fundamental train frequency: how fast the cage (ball holder) turns."""
    r = _ratio(ball_d, pitch_d, contact_angle_deg)
    return 0.5 * (1 - r)


def bpfo_multiplier(n_balls=config.N_BALLS, ball_d=config.BALL_DIAMETER_MM,
                    pitch_d=config.PITCH_DIAMETER_MM,
                    contact_angle_deg=config.CONTACT_ANGLE_DEG):
    """Ball pass frequency, outer race: impacts per second on an outer-race defect."""
    r = _ratio(ball_d, pitch_d, contact_angle_deg)
    return n_balls / 2 * (1 - r)


def bpfi_multiplier(n_balls=config.N_BALLS, ball_d=config.BALL_DIAMETER_MM,
                    pitch_d=config.PITCH_DIAMETER_MM,
                    contact_angle_deg=config.CONTACT_ANGLE_DEG):
    """Ball pass frequency, inner race: impacts per second on an inner-race defect."""
    r = _ratio(ball_d, pitch_d, contact_angle_deg)
    return n_balls / 2 * (1 + r)


def bsf_multiplier(n_balls=config.N_BALLS, ball_d=config.BALL_DIAMETER_MM,
                   pitch_d=config.PITCH_DIAMETER_MM,
                   contact_angle_deg=config.CONTACT_ANGLE_DEG):
    """
    Ball spin frequency: how many times a ball spins about its own axis per
    shaft revolution.

    Note: a spot on a ball touches BOTH races once per spin, so a ball
    defect often shows up at 2 x BSF. CWRU's published "rolling element"
    number (4.7135) is 2 x BSF - see docs/VALIDATION.md.
    """
    r = _ratio(ball_d, pitch_d, contact_angle_deg)
    return pitch_d / (2 * ball_d) * (1 - r ** 2)


def fault_frequencies_hz(rpm):
    """
    All the characteristic frequencies, in Hz, for one shaft speed.

    Example:
        fault_frequencies_hz(1797)["BPFO"]  ->  about 107.4 Hz
    """
    shaft_hz = rpm / 60.0
    return {
        "shaft_1x": shaft_hz,
        "FTF": ftf_multiplier() * shaft_hz,
        "BPFO": bpfo_multiplier() * shaft_hz,
        "BPFI": bpfi_multiplier() * shaft_hz,
        "BSF": bsf_multiplier() * shaft_hz,
        "2xBSF": 2 * bsf_multiplier() * shaft_hz,
    }


def main():
    """Print the multipliers, compare them with CWRU, and save a table in Hz."""
    import pandas as pd

    ours = {
        "BPFI": bpfi_multiplier(),
        "BPFO": bpfo_multiplier(),
        "FTF": ftf_multiplier(),
        "BSF": bsf_multiplier(),
        "2xBSF": 2 * bsf_multiplier(),
    }
    published = config.CWRU_PUBLISHED_MULTIPLIERS
    compare_to = {"BPFI": "BPFI", "BPFO": "BPFO", "FTF": "FTF",
                  "2xBSF": "rolling_element"}

    print("Multipliers (fault frequency / shaft frequency):")
    for name, value in ours.items():
        line = f"  {name:6s} ours = {value:.5f}"
        if name in compare_to:
            cwru = published[compare_to[name]]
            line += f"   CWRU = {cwru:.4f}   difference = {value - cwru:+.5f}"
        print(line)

    # One row per motor load, frequencies in Hz at the nominal speed.
    rows = []
    for load_hp, rpm in config.NOMINAL_RPM.items():
        row = {"load_hp": load_hp, "rpm": rpm}
        row.update({k + "_hz": round(v, 3)
                    for k, v in fault_frequencies_hz(rpm).items()})
        rows.append(row)
    table = pd.DataFrame(rows)
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = config.RESULTS_DIR / "fault_frequencies.csv"
    table.to_csv(out, index=False)
    print("\nFault frequencies in Hz at nominal speeds:")
    print(table.to_string(index=False))
    print(f"\nSaved {out.relative_to(config.REPO_ROOT)}")


if __name__ == "__main__":
    main()
