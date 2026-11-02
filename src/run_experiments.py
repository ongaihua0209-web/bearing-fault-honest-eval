"""
run_experiments.py - train three classifiers under the three split
protocols and measure how much leakage inflates the scores.

Setup (all fixed before looking at any result):
  windows   2048 samples, non-overlapping (segment.py)
  features  set F1: 7 generic statistics per window (features.py)
  label     fault location: normal / inner_race / ball / outer_race
  protocols A random (leaky), B unseen load, C unseen fault size (splits.py)
  models    logistic regression, random forest, gradient boosting -
            scikit-learn defaults except where noted below; no tuning
  seeds     0-4. Protocol A gets a new random split per seed; B and C
            keep their fixed splits and the seed only changes the models'
            own randomness (logistic regression has none, so its spread
            under B and C is zero).

Rule 1 (never fit on test data) is enforced by the Pipeline: the scaler
learns its mean and spread from the training windows only, then applies
them unchanged to the test windows. Class weights come from the training
labels only.

Class weights: the healthy class has about 3.4 times fewer windows than
each fault class. Every model weights each training window by
1 / (its class's share), so all four classes count equally - matching the
scores we report (macro-F1 and balanced accuracy treat classes equally).

Scores:
  macro-F1           F1 (balance of precision and recall) per class,
                     averaged with equal weight per class
  balanced accuracy  recall per class, averaged with equal weight
Both are 1.0 for perfect, about 0.25 for guessing among 4 classes.
Reported as mean +/- standard deviation over the 5 seeds. For protocol C,
each seed's score is first averaged over its 3 folds.

Run:
    python -m src.run_experiments          (about 1-2 minutes on a laptop CPU)

Outputs (results/):
    results_f1.csv               headline table: protocol x model
    results_f1_runs.csv          every single run (protocol, fold, seed, model)
    results_f1_by_group.csv      share correct per fault type AND size
    results_f1_by_fold.csv       protocol C per held-out fault size
    confusion_matrices_f1.csv    counts summed over all runs
    figures/f1_macro_f1_by_protocol.png
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

# Groups to flag in every report (CLAUDE.md, docs/VALIDATION.md 4.3): the
# envelope check found no matching fault signature in these.
FLAGGED_GROUPS = {("ball", 0.007), ("ball", 0.014), ("ball", 0.021), ("outer_race", 0.014)}

# Chart colours (colour-blind-checked palette) and neutral inks.
COLOUR_BY_MODEL = {"logistic_regression": "#2a78d6", "random_forest": "#eb6834",
                   "gradient_boosting": "#1baf7a"}
INK, INK_SECONDARY, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3de", "#fcfcfb"


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


def scores(y_true, y_pred):
    """Macro-F1, balanced accuracy and per-class F1 for one run."""
    result = {"macro_f1": f1_score(y_true, y_pred, labels=splits.CLASSES, average="macro"),
              "balanced_accuracy": balanced_accuracy_score(y_true, y_pred)}
    per_class = f1_score(y_true, y_pred, labels=splits.CLASSES, average=None)
    for cls, value in zip(splits.CLASSES, per_class):
        result[f"f1_{cls}"] = value
    return result


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------

def summarise(runs):
    """
    Headline table: one row per protocol x model, mean +/- std over seeds.
    For protocol C each seed is first averaged over its 3 folds.
    """
    per_seed = (runs.groupby(["protocol", "model", "seed"])
                [["macro_f1", "balanced_accuracy"]].mean().reset_index())
    table = per_seed.groupby(["protocol", "model"]).agg(
        macro_f1_mean=("macro_f1", "mean"), macro_f1_std=("macro_f1", "std"),
        balanced_accuracy_mean=("balanced_accuracy", "mean"),
        balanced_accuracy_std=("balanced_accuracy", "std"),
        n_seeds=("seed", "nunique")).reset_index()
    table["protocol_name"] = table["protocol"].map(splits.PROTOCOLS)
    return table.round(4)


def plot_bars(table, path):
    """Grouped bar chart: macro-F1 by protocol, one bar per model."""
    fig, ax = plt.subplots(figsize=(8.5, 4.6), facecolor=SURFACE)
    protocols = list(splits.PROTOCOLS)
    width = 0.26
    for i, model in enumerate(MODEL_NAMES):
        rows = table.set_index(["protocol", "model"])
        means = [rows.loc[(p, model), "macro_f1_mean"] for p in protocols]
        stds = [rows.loc[(p, model), "macro_f1_std"] for p in protocols]
        x = np.arange(len(protocols)) + (i - 1) * width
        ax.bar(x, means, width * 0.92, color=COLOUR_BY_MODEL[model],
               label=MODEL_LABELS[model], zorder=2)
        ax.errorbar(x, means, yerr=stds, fmt="none", ecolor=INK_SECONDARY,
                    elinewidth=1, capsize=3, zorder=3)
        for xi, m in zip(x, means):
            ax.text(xi, m + 0.02, f"{m:.2f}", ha="center", va="bottom",
                    fontsize=8, color=INK)
    ax.axhline(0.25, color=INK_SECONDARY, linestyle=":", linewidth=1, zorder=1,
               label="Guessing among 4 classes (≈ 0.25)")
    ax.set_xticks(range(len(protocols)))
    ax.set_xlim(-0.5, len(protocols) - 0.5)
    ax.set_xticklabels([f"{p}: {splits.PROTOCOLS[p]}" for p in protocols], fontsize=9)
    ax.set_ylabel("Macro-F1 (mean ± std over 5 seeds)", color=INK)
    ax.set_ylim(0, 1.12)
    ax.set_title("Feature set F1: the same models, three ways of testing",
                 loc="left", fontsize=11, color=INK)
    ax.set_facecolor(SURFACE)
    ax.grid(True, axis="y", color=GRID, linewidth=0.6, zorder=0)
    ax.tick_params(colors=INK_SECONDARY)
    for spine in ax.spines.values():
        spine.set_color(GRID)
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
    windows, meta = segment.make_windows()
    X = features.features_f1(windows).to_numpy()
    y = meta[splits.LABEL_COLUMN].to_numpy()
    print(f"{len(windows)} windows, {X.shape[1]} features "
          f"({time.time() - start:.0f} s to load and compute)")

    runs, group_rows, confusion = [], [], {}
    for split in splits.all_splits(meta, SEEDS):
        train, test = split["train"], split["test"]
        for model_name in MODEL_NAMES:
            _, predicted = train_and_test(model_name, split["seed"],
                                          X[train], y[train], X[test], y[test])
            key = {"protocol": split["protocol"], "fold": split["fold"],
                   "seed": split["seed"], "model": model_name}
            runs.append({**key, "n_train": len(train), "n_test": len(test),
                         **scores(y[test], predicted)})

            # Share correct per (fault type, fault size), for per-group reporting.
            test_meta = meta.iloc[test].assign(correct=(predicted == y[test]))
            for (location, size), group in test_meta.groupby(["fault_location", "fault_size_in"]):
                group_rows.append({**key, "fault_location": location, "fault_size_in": size,
                                   "n_test": len(group), "share_correct": group["correct"].mean()})

            counts = confusion_matrix(y[test], predicted, labels=splits.CLASSES)
            confusion_key = (split["protocol"], model_name)
            confusion[confusion_key] = confusion.get(confusion_key, 0) + counts

    runs = pd.DataFrame(runs)
    table = summarise(runs)

    groups = (pd.DataFrame(group_rows)
              .groupby(["protocol", "model", "fault_location", "fault_size_in"])
              .agg(share_correct_mean=("share_correct", "mean"),
                   share_correct_std=("share_correct", "std"),
                   n_test_windows=("n_test", "mean")).reset_index())
    groups["flagged"] = [(loc, round(size, 3)) in FLAGGED_GROUPS
                         for loc, size in zip(groups["fault_location"], groups["fault_size_in"])]

    by_fold = (runs[runs["protocol"] == "C"].groupby(["fold", "model"])
               [["macro_f1", "balanced_accuracy"]].agg(["mean", "std"]).round(4))
    by_fold.columns = ["_".join(c) for c in by_fold.columns]

    confusion_rows = [{"protocol": p, "model": m, "true": t, "predicted": pr,
                       "count": int(counts[i, j])}
                      for (p, m), counts in confusion.items()
                      for i, t in enumerate(splits.CLASSES)
                      for j, pr in enumerate(splits.CLASSES)]

    out = config.RESULTS_DIR
    table.to_csv(out / "results_f1.csv", index=False)
    runs.round(4).to_csv(out / "results_f1_runs.csv", index=False)
    groups.round(4).to_csv(out / "results_f1_by_group.csv", index=False)
    by_fold.reset_index().to_csv(out / "results_f1_by_fold.csv", index=False)
    pd.DataFrame(confusion_rows).to_csv(out / "confusion_matrices_f1.csv", index=False)

    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plot_bars(table, config.FIGURES_DIR / "f1_macro_f1_by_protocol.png")
    # "Best" = highest mean macro-F1 within the protocol. Chosen on test
    # scores, so it is for display only - the headline table shows all models.
    for protocol in ("A", "C"):
        best = (table[table["protocol"] == protocol]
                .sort_values("macro_f1_mean", ascending=False).iloc[0]["model"])
        plot_confusion(confusion[(protocol, best)],
                       f"Protocol {protocol}: {splits.PROTOCOLS[protocol]}\n"
                       f"{MODEL_LABELS[best]}, all seeds{' and folds' if protocol == 'C' else ''}",
                       config.FIGURES_DIR / f"f1_confusion_{protocol}_{best}.png")

    print("\nHeadline (feature set F1):")
    print(table[["protocol", "model", "macro_f1_mean", "macro_f1_std",
                 "balanced_accuracy_mean", "balanced_accuracy_std"]].to_string(index=False))
    print("\nProtocol C by held-out fault size (macro-F1, mean over seeds):")
    print(by_fold["macro_f1_mean"].unstack().to_string())
    print(f"\nTotal time: {time.time() - start:.0f} s. Results in results/.")


if __name__ == "__main__":
    main()
