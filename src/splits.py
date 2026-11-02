"""
splits.py - three ways of choosing training and test windows.

The label to predict is the fault location: normal, inner_race, ball or
outer_race. (Fault size is not predicted.)

What "leakage" means here: if the test set contains windows from a
recording - or a physical bearing - that the model has already seen in
training, the test no longer measures what we care about (recognising a
fault on a machine the model has never seen). Each protocol below leaks
less than the one before:

  A. Random      Shuffle all windows, 80% train / 20% test.
                 Every recording is cut up and scattered over both sides,
                 so the model is tested on recordings it trained on.
                 DELIBERATELY LEAKY - this is how many published CWRU
                 results are produced.

  B. Load        Train on 0-2 HP, test on 3 HP.
                 No recording is on both sides. BUT each CWRU fault is one
                 physical bearing recorded at all four loads, so every
                 test bearing (healthy or faulty) was also seen in
                 training, just at another load.

  C. Fault size  Three folds. Each holds out one fault size (0.007, 0.014
                 or 0.021 in) for every fault type as the test set.
                 Faulty test bearings are therefore truly unseen.
                 The healthy class has no fault size, so each fold holds
                 out one load of it instead. CAVEAT: all four healthy
                 recordings come from the same physical bearing, so the
                 healthy class still shares one bearing between train and
                 test (like protocol B).

All three are fixed before looking at any result (CLAUDE.md rule 1).
Each function returns (train_positions, test_positions): row positions
into the window table from segment.make_windows().
"""

import numpy as np
from sklearn.model_selection import train_test_split

LABEL_COLUMN = "fault_location"
CLASSES = ["normal", "inner_race", "ball", "outer_race"]

TEST_FRACTION = 0.2                   # protocol A
B_TEST_LOAD_HP = 3                    # protocol B
C_FAULT_SIZES = (0.007, 0.014, 0.021)  # protocol C, one fold each

# Protocol C: which healthy load is held out with each fault size.
# Loads 1-3 rather than 0-2 because file 97 (0 HP) is only 5 s long; keeping
# it in training gives every fold a healthy test set of the same size.
C_NORMAL_TEST_LOAD = {0.007: 1, 0.014: 2, 0.021: 3}

PROTOCOLS = {"A": "Random windows (leaky)",
             "B": "Unseen load (train 0-2 HP, test 3 HP)",
             "C": "Unseen fault size (3 folds)"}


def _positions(mask):
    """True/False per window -> the row positions where it is True."""
    return np.flatnonzero(np.asarray(mask))


def split_random(meta, seed):
    """
    Protocol A. Shuffle all windows and keep 20% for testing.
    'stratify' keeps the same class mix on both sides, so a small class
    (normal) is not left out of the test set by bad luck.
    """
    positions = np.arange(len(meta))
    train, test = train_test_split(positions, test_size=TEST_FRACTION,
                                   random_state=seed, shuffle=True,
                                   stratify=meta[LABEL_COLUMN])
    return np.sort(train), np.sort(test)


def split_by_load(meta):
    """Protocol B. Train on every window at 0-2 HP, test on 3 HP."""
    is_test = meta["load_hp"] == B_TEST_LOAD_HP
    return _positions(~is_test), _positions(is_test)


def split_by_fault_size(meta, fault_size):
    """
    Protocol C, one fold. Test = every faulty window of this fault size,
    plus the healthy windows at the matching held-out load.
    """
    is_normal = meta["fault_location"] == "normal"
    faulty_test = ~is_normal & np.isclose(meta["fault_size_in"], fault_size)
    normal_test = is_normal & (meta["load_hp"] == C_NORMAL_TEST_LOAD[fault_size])
    is_test = faulty_test | normal_test
    return _positions(~is_test), _positions(is_test)


def all_splits(meta, seeds):
    """
    Every train/test split the experiment needs, as a list of dictionaries:
      {"protocol": "A", "fold": "-", "seed": 0, "train": [...], "test": [...]}

    A: a different random split for every seed.
    B: one fixed split; seeds change only the models' own randomness.
    C: three fixed folds; seeds change only the models' own randomness.
    """
    splits = []
    for seed in seeds:
        train, test = split_random(meta, seed)
        splits.append({"protocol": "A", "fold": "-", "seed": seed,
                       "train": train, "test": test})
        train, test = split_by_load(meta)
        splits.append({"protocol": "B", "fold": "-", "seed": seed,
                       "train": train, "test": test})
        for size in C_FAULT_SIZES:
            train, test = split_by_fault_size(meta, size)
            splits.append({"protocol": "C", "fold": f"{size:.3f}", "seed": seed,
                           "train": train, "test": test})
    return splits
