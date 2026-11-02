"""
run_experiments.py - the full experiment grid:
    3 protocols x 6 feature-set configurations x 3 models x 5 seeds.

Feature-set configurations (features.py explains each set):
    F1    on 2048-sample windows   generic statistics      (as in session 4)
    F2    on 2048-sample windows   spectral band energies
    F3    on 8192-sample windows   physics-informed envelope features
    F1+F3 on 8192-sample windows   both
  plus two CONTROLS, so that F3 is not credited for what longer windows
  alone would give:
    F1    on 8192-sample windows
    F2    on 8192-sample windows

Setup (all fixed before looking at any result):
  label     fault location: normal / inner_race / ball / outer_race
  protocols A random (leaky), B unseen load, C unseen fault size (splits.py)
  models    logistic regression, random forest (300 trees), gradient
            boosting - scikit-learn defaults otherwise; no tuning
  seeds     0-4. Protocol A gets a new random split per seed; B and C keep
            their fixed splits and the seed only changes the models' own
            randomness (logistic regression has none: its spread is zero).

Rule 1 (never fit on test data):
  - the scaler sits inside a Pipeline, so it learns only from training
    windows;
  - class weights come from the training labels only;
  - the F3 band is chosen from the training windows only, separately for
    every split (features.choose_band).

Class weights: every model weights each training window by
1 / (its class's share), so all four classes count equally - matching the
scores (macro-F1 and balanced accuracy treat classes equally).

Scores: macro-F1 and balanced accuracy, mean +/- standard deviation over
the 5 seeds; for protocol C each seed is first averaged over its 3 folds.
Both are 1.0 for perfect and about 0.25 for guessing among 4 classes.

Run:
    python -m src.run_experiments          (about 6-8 minutes on a 4-core CPU)

Outputs (results/):
    results_all.csv              headline: feature set x protocol x model
    results_all_runs.csv         every single run
    results_all_by_group.csv     share correct per fault type AND size
    results_all_by_fold.csv      protocol C per held-out fault size
    confusion_matrices_all.csv   counts summed over seeds (and folds)
    feature_importance_C.csv     importances under protocol C, every model
    f3_bands_chosen.csv          which F3 band each training set picked
    results_f1.csv               the F1 (2048) subset, same format as session 4
    figures/leakage_gap_by_feature_set.png   headline chart
    figures/feature_importance_best_C.png
    figures/f1_macro_f1_by_protocol.png      (F1 only, as in session 4)
    figures/f1_confusion_A_<model>.png, f1_confusion_C_<model>.png
"""

import time

import matplotlib
matplotlib.use("Agg")            # draw to files, no screen needed
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_sample_weight

from src import config, features, segment, splits

SEEDS = (0, 1, 2, 3, 4)
MODEL_NAMES = ("logistic_regression", "random_forest", "gradient_boosting")
MODEL_LABELS = {"logistic_regression": "Logistic regression",
                "random_forest": "Random forest",
                "gradient_boosting": "Gradient boosting"}

SHORT = config.WINDOW_LENGTH_SAMPLES          # 2048
LONG = config.F3_WINDOW_LENGTH_SAMPLES        # 8192
# (feature set, window length). The order is the order in tables and charts.
FEATURE_SETS = [("F1", SHORT), ("F2", SHORT), ("F1", LONG), ("F2", LONG),
                ("F3", LONG), ("F1+F3", LONG)]

# Groups to flag in every report (CLAUDE.md, docs/VALIDATION.md 4.3).
FLAGGED_GROUPS = {("ball", 0.007), ("ball", 0.014), ("ball", 0.021), ("outer_race", 0.014)}

COLOUR_BY_MODEL = {"logistic_regression": "#2a78d6", "random_forest": "#eb6834",
                   "gradient_boosting": "#1baf7a"}
COLOUR_A, COLOUR_C = "#eb6834", "#2a78d6"
COLOUR_GENERIC, COLOUR_PHYSICS = "#8a8984", "#2a78d6"
INK, INK_SECONDARY, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3de", "#fcfcfb"


def label(feature_set, window_length):
    return f"{feature_set} ({window_length})"


# ---------------------------------------------------------------------------
# Models and one training run
# ---------------------------------------------------------------------------

def make_model(name, seed):
    """
    A scaler followed by a classifier, bundled in a Pipeline so the scaler
    can only ever be fitted on whatever data the pipeline is trained on.
    """
    if name == "logistic_regression":
        classifier = LogisticRegression(max_iter=5000)
    elif name == "random_forest":
        classifier = RandomForestClassifier(n_estimators=300, random_state=seed, n_jobs=-1)
    elif name == "gradient_boosting":
        classifier = GradientBoostingClassifier(random_state=seed)
    else:
        raise ValueError(name)
    return Pipeline([("scaler", StandardScaler()), ("model", classifier)])


def train_and_test(model_name, seed, X_train, y_train, X_test, y_test):
    """
    Fit on the training data only, predict the test data.
    Returns (fitted_pipeline, predictions).
    """
    pipeline = make_model(model_name, seed)
    weights = compute_sample_weight("balanced", y_train)   # from TRAIN labels only
    pipeline.fit(X_train, y_train, model__sample_weight=weights)
    return pipeline, pipeline.predict(X_test)


def importance(pipeline):
    """
    How much the fitted model leans on each feature.
      trees:               scikit-learn's built-in importance (sums to 1)
      logistic regression: mean absolute coefficient over the 4 classes;
                           comparable across features because the inputs
                           are standardised; rescaled to sum to 1
    """
    model = pipeline.named_steps["model"]
    if hasattr(model, "feature_importances_"):
        values = model.feature_importances_
    else:
        values = np.abs(model.coef_).mean(axis=0)
    return values / values.sum()


def scores(y_true, y_pred):
    """Macro-F1, balanced accuracy and per-class F1 for one run."""
    result = {"macro_f1": f1_score(y_true, y_pred, labels=splits.CLASSES, average="macro"),
              "balanced_accuracy": balanced_accuracy_score(y_true, y_pred)}
    per_class = f1_score(y_true, y_pred, labels=splits.CLASSES, average=None)
    for cls, value in zip(splits.CLASSES, per_class):
        result[f"f1_{cls}"] = value
    return result


# ---------------------------------------------------------------------------
# Features for each split
# ---------------------------------------------------------------------------

def build_feature_tables():
    """
    Cut the windows and compute every feature that does not depend on the
    split. F3 depends on the split (its band is chosen from training data),
    so here we compute it for EVERY candidate band; each split then picks
    its slice.
    Returns {window_length: {"meta", "F1", "F2", "f3_kurtosis", "f3_by_band"}}.
    """
    tables = {}
    for length in (SHORT, LONG):
        windows, meta = segment.make_windows(length)
        tables[length] = {"meta": meta,
                          "F1": features.features_f1(windows).to_numpy(),
                          "F2": features.features_f2(windows).to_numpy()}
        if length == LONG:
            kurtosis, f3 = features.f3_for_every_band(windows, meta["rpm"].to_numpy())
            tables[length]["f3_kurtosis"] = kurtosis
            tables[length]["f3_by_band"] = f3
    return tables


def features_for_split(feature_set, table, train_positions):
    """
    The feature matrix for one split, plus the feature names and (for sets
    containing F3) the band chosen from this split's TRAINING windows.
    """
    if feature_set in ("F1", "F2"):
        names = features.FEATURE_NAMES_F1 if feature_set == "F1" else features.FEATURE_NAMES_F2
        return table[feature_set], names, None
    band = features.choose_band(table["f3_kurtosis"], train_positions)
    f3 = table["f3_by_band"][band]
    if feature_set == "F3":
        return f3, features.FEATURE_NAMES_F3, band
    return (np.hstack([table["F1"], f3]),
            features.FEATURE_NAMES_F1 + features.FEATURE_NAMES_F3, band)


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------

def summarise(runs):
    """
    Headline table: one row per (feature set, window length,) protocol and
    model, mean +/- std over seeds. For protocol C each seed is first
    averaged over its 3 folds.
    """
    keys = [k for k in ("feature_set", "window_length", "protocol", "model") if k in runs]
    per_seed = runs.groupby(keys + ["seed"])[["macro_f1", "balanced_accuracy"]].mean().reset_index()
    table = per_seed.groupby(keys).agg(
        macro_f1_mean=("macro_f1", "mean"), macro_f1_std=("macro_f1", "std"),
        balanced_accuracy_mean=("balanced_accuracy", "mean"),
        balanced_accuracy_std=("balanced_accuracy", "std"),
        n_seeds=("seed", "nunique")).reset_index()
    table["protocol_name"] = table["protocol"].map(splits.PROTOCOLS)
    return table.round(4)


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def _style(ax):
    ax.set_facecolor(SURFACE)
    ax.grid(True, axis="y", color=GRID, linewidth=0.6, zorder=0)
    ax.tick_params(colors=INK_SECONDARY, labelsize=9)
    for spine in ax.spines.values():
        spine.set_color(GRID)


def plot_leakage_gap(table, path):
    """
    Headline chart: macro-F1 for every feature set under protocol A (leaky)
    and protocol C (unseen fault size), one panel per model.
    """
    rows = table.set_index(["feature_set", "window_length", "protocol", "model"])
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.2), sharey=True, facecolor=SURFACE)
    x = np.arange(len(FEATURE_SETS))
    for ax, model in zip(axes, MODEL_NAMES):
        for offset, protocol, colour, name in ((-0.2, "A", COLOUR_A, "A: random windows (leaky)"),
                                               (0.2, "C", COLOUR_C, "C: unseen fault size (honest)")):
            means = [rows.loc[(fs, n, protocol, model), "macro_f1_mean"] for fs, n in FEATURE_SETS]
            stds = [rows.loc[(fs, n, protocol, model), "macro_f1_std"] for fs, n in FEATURE_SETS]
            ax.bar(x + offset, means, 0.38, color=colour, label=name, zorder=2)
            ax.errorbar(x + offset, means, yerr=stds, fmt="none", ecolor=INK_SECONDARY,
                        elinewidth=1, capsize=2, zorder=3)
            for xi, m, sd in zip(x + offset, means, stds):
                ax.text(xi, m + sd + 0.012, f"{m:.2f}", ha="center", va="bottom",
                        fontsize=7.5, color=INK)
        ax.axhline(0.25, color=INK_SECONDARY, linestyle=":", linewidth=1, zorder=1,
                   label="Guessing among 4 classes (≈ 0.25)")
        ax.axvspan(1.5, 3.5, color=GRID, alpha=0.45, zorder=0)       # the controls
        ax.set_xticks(x)
        ax.set_xticklabels([f"{fs}\n{n}" + ("\n(control)" if fs in ("F1", "F2") and n == LONG
                                              else "") for fs, n in FEATURE_SETS], fontsize=8.5)
        ax.set_xlabel("Feature set and window length (samples)", fontsize=9, color=INK)
        ax.set_title(MODEL_LABELS[model], loc="left", fontsize=11, color=INK)
        ax.set_ylim(0, 1.12)
        _style(ax)
    axes[0].set_ylabel("Macro-F1 (mean ± std over 5 seeds)", color=INK, fontsize=10)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.suptitle("The leakage gap for every feature set: random split (A) vs unseen fault size (C)",
                 x=0.01, ha="left", y=0.99, fontsize=12, color=INK)
    fig.legend(handles, labels, loc="upper left", bbox_to_anchor=(0.01, 0.94), ncol=3,
               fontsize=9, frameon=False, labelcolor=INK_SECONDARY)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_importance(names, values, title, path):
    """Horizontal bars, most important feature on top; physics features in blue."""
    order = np.argsort(values)
    fig, ax = plt.subplots(figsize=(7.5, 0.32 * len(names) + 1.6), facecolor=SURFACE)
    colours = [COLOUR_PHYSICS if names[i] in features.FEATURE_NAMES_F3 else COLOUR_GENERIC
               for i in order]
    ax.barh(np.arange(len(names)), np.asarray(values)[order], color=colours, zorder=2)
    ax.set_yticks(np.arange(len(names)))
    ax.set_yticklabels([names[i] for i in order], fontsize=9)
    ax.set_xlabel("Share of the model's total importance (sums to 1)", color=INK, fontsize=10)
    ax.set_title(title, loc="left", fontsize=10, color=INK)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=COLOUR_PHYSICS, label="physics-informed (F3)"),
                       Patch(color=COLOUR_GENERIC, label="generic (F1 / F2)")],
              loc="lower right", fontsize=8, frameon=False, labelcolor=INK_SECONDARY)
    _style(ax)
    ax.grid(True, axis="x", color=GRID, linewidth=0.6, zorder=0)
    ax.grid(False, axis="y")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_bars(table, path):
    """F1-only chart from session 4: macro-F1 by protocol, one bar per model."""
    fig, ax = plt.subplots(figsize=(8.5, 4.6), facecolor=SURFACE)
    protocols = list(splits.PROTOCOLS)
    width = 0.26
    rows = table.set_index(["protocol", "model"])
    for i, model in enumerate(MODEL_NAMES):
        means = [rows.loc[(p, model), "macro_f1_mean"] for p in protocols]
        stds = [rows.loc[(p, model), "macro_f1_std"] for p in protocols]
        x = np.arange(len(protocols)) + (i - 1) * width
        ax.bar(x, means, width * 0.92, color=COLOUR_BY_MODEL[model],
               label=MODEL_LABELS[model], zorder=2)
        ax.errorbar(x, means, yerr=stds, fmt="none", ecolor=INK_SECONDARY,
                    elinewidth=1, capsize=3, zorder=3)
        for xi, m in zip(x, means):
            ax.text(xi, m + 0.02, f"{m:.2f}", ha="center", va="bottom", fontsize=8, color=INK)
    ax.axhline(0.25, color=INK_SECONDARY, linestyle=":", linewidth=1, zorder=1,
               label="Guessing among 4 classes (≈ 0.25)")
    ax.set_xticks(range(len(protocols)))
    ax.set_xlim(-0.5, len(protocols) - 0.5)
    ax.set_xticklabels([f"{p}: {splits.PROTOCOLS[p]}" for p in protocols], fontsize=9)
    ax.set_ylabel("Macro-F1 (mean ± std over 5 seeds)", color=INK)
    ax.set_ylim(0, 1.12)
    ax.set_title("Feature set F1: the same models, three ways of testing",
                 loc="left", fontsize=11, color=INK)
    _style(ax)
    ax.legend(loc="upper right", fontsize=8, frameon=False, labelcolor=INK_SECONDARY)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_confusion(counts, title, path):
    """Confusion matrix as shares of each TRUE class (rows add up to 100%)."""
    shares = counts / counts.sum(axis=1, keepdims=True)
    fig, ax = plt.subplots(figsize=(5.4, 4.6), facecolor=SURFACE)
    ax.imshow(shares, cmap="Blues", vmin=0, vmax=1)
    names = ["normal", "inner race", "ball", "outer race"]
    ax.set_xticks(range(4))
    ax.set_xticklabels(names, fontsize=9)
    ax.set_yticks(range(4))
    ax.set_yticklabels(names, fontsize=9)
    ax.set_xlabel("Predicted", color=INK)
    ax.set_ylabel("True", color=INK)
    for i in range(4):
        for j in range(4):
            ax.text(j, i, f"{shares[i, j]:.0%}", ha="center", va="center", fontsize=10,
                    color="white" if shares[i, j] > 0.55 else INK)
    ax.set_title(title, loc="left", fontsize=10, color=INK)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    start = time.time()
    tables = build_feature_tables()
    print(f"Windows and features ready ({time.time() - start:.0f} s)")

    runs, group_rows, confusion, importances, bands = [], [], {}, {}, []
    for feature_set, length in FEATURE_SETS:
        table = tables[length]
        meta = table["meta"]
        y = meta[splits.LABEL_COLUMN].to_numpy()
        for split in splits.all_splits(meta, SEEDS):
            train, test = split["train"], split["test"]
            X, names, band = features_for_split(feature_set, table, train)
            if band is not None and feature_set == "F3":
                bands.append({"protocol": split["protocol"], "fold": split["fold"],
                              "seed": split["seed"], "band_hz": "%d-%d" % features.F3_BANDS[band]})
            for model_name in MODEL_NAMES:
                pipeline, predicted = train_and_test(model_name, split["seed"],
                                                     X[train], y[train], X[test], y[test])
                key = {"feature_set": feature_set, "window_length": length,
                       "protocol": split["protocol"], "fold": split["fold"],
                       "seed": split["seed"], "model": model_name}
                runs.append({**key, "n_train": len(train), "n_test": len(test),
                             **scores(y[test], predicted)})

                test_meta = meta.iloc[test].assign(correct=(predicted == y[test]))
                for (loc, size), group in test_meta.groupby(["fault_location", "fault_size_in"]):
                    group_rows.append({**key, "fault_location": loc, "fault_size_in": size,
                                       "n_test": len(group),
                                       "share_correct": group["correct"].mean()})

                ckey = (feature_set, length, split["protocol"], model_name)
                counts = confusion_matrix(y[test], predicted, labels=splits.CLASSES)
                confusion[ckey] = confusion.get(ckey, 0) + counts
                if split["protocol"] == "C":
                    importances.setdefault(ckey, (names, []))[1].append(importance(pipeline))
        print(f"  {label(feature_set, length)} done ({time.time() - start:.0f} s)")

    runs = pd.DataFrame(runs)
    table = summarise(runs)

    groups = (pd.DataFrame(group_rows)
              .groupby(["feature_set", "window_length", "protocol", "model",
                        "fault_location", "fault_size_in"])
              .agg(share_correct_mean=("share_correct", "mean"),
                   share_correct_std=("share_correct", "std"),
                   n_test_windows=("n_test", "mean")).reset_index())
    groups["flagged"] = [(loc, round(size, 3)) in FLAGGED_GROUPS
                         for loc, size in zip(groups["fault_location"], groups["fault_size_in"])]

    by_fold = (runs[runs["protocol"] == "C"]
               .groupby(["feature_set", "window_length", "fold", "model"])
               [["macro_f1", "balanced_accuracy"]].agg(["mean", "std"]).round(4))
    by_fold.columns = ["_".join(c) for c in by_fold.columns]

    confusion_rows = [{"feature_set": fs, "window_length": n, "protocol": p, "model": m,
                       "true": t, "predicted": pr, "count": int(c[i, j])}
                      for (fs, n, p, m), c in confusion.items()
                      for i, t in enumerate(splits.CLASSES)
                      for j, pr in enumerate(splits.CLASSES)]
    importance_rows = [{"feature_set": fs, "window_length": n, "model": m,
                        "feature": name, "importance": value}
                       for (fs, n, p, m), (names, values) in importances.items()
                       for name, value in zip(names, np.mean(values, axis=0))]

    out = config.RESULTS_DIR
    table.to_csv(out / "results_all.csv", index=False)
    runs.round(4).to_csv(out / "results_all_runs.csv", index=False)
    groups.round(4).to_csv(out / "results_all_by_group.csv", index=False)
    by_fold.reset_index().to_csv(out / "results_all_by_fold.csv", index=False)
    pd.DataFrame(confusion_rows).to_csv(out / "confusion_matrices_all.csv", index=False)
    pd.DataFrame(importance_rows).round(4).to_csv(out / "feature_importance_C.csv", index=False)
    pd.DataFrame(bands).to_csv(out / "f3_bands_chosen.csv", index=False)

    # The session-4 F1 outputs, regenerated from the same runs.
    f1 = table[(table["feature_set"] == "F1") & (table["window_length"] == SHORT)]
    f1.drop(columns=["feature_set", "window_length"]).to_csv(out / "results_f1.csv", index=False)

    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plot_leakage_gap(table, config.FIGURES_DIR / "leakage_gap_by_feature_set.png")
    plot_bars(f1, config.FIGURES_DIR / "f1_macro_f1_by_protocol.png")
    # "Best" = highest mean macro-F1. Chosen on test scores, so for display
    # only - the tables report every model.
    for protocol in ("A", "C"):
        best = f1[f1["protocol"] == protocol].sort_values("macro_f1_mean").iloc[-1]["model"]
        plot_confusion(confusion[("F1", SHORT, protocol, best)],
                       f"Protocol {protocol}: {splits.PROTOCOLS[protocol]}\n"
                       f"F1 features, {MODEL_LABELS[best]}, all seeds"
                       f"{' and folds' if protocol == 'C' else ''}",
                       config.FIGURES_DIR / f"f1_confusion_{protocol}_{best}.png")
    best_c = table[table["protocol"] == "C"].sort_values("macro_f1_mean").iloc[-1]
    ckey = (best_c["feature_set"], best_c["window_length"], "C", best_c["model"])
    names, values = importances[ckey]
    plot_importance(names, np.mean(values, axis=0),
                    f"Best protocol-C model: {MODEL_LABELS[best_c['model']]} on "
                    f"{label(best_c['feature_set'], best_c['window_length'])}\n"
                    f"(macro-F1 {best_c['macro_f1_mean']:.2f}; importance averaged over "
                    f"3 folds x 5 seeds)",
                    config.FIGURES_DIR / "feature_importance_best_C.png")

    pivot = table.pivot_table(index=["feature_set", "window_length"], columns=["protocol", "model"],
                              values="macro_f1_mean", sort=False)
    print("\nMacro-F1 (mean over seeds):")
    print(pivot.round(3).to_string())
    print(f"\nBest protocol-C model: {label(best_c['feature_set'], best_c['window_length'])}, "
          f"{best_c['model']} ({best_c['macro_f1_mean']:.3f})")
    print(f"Total time: {time.time() - start:.0f} s. Results in results/.")


if __name__ == "__main__":
    main()
