# Research Notebooks

This folder is for exploratory analysis of accumulated evidence. Notebooks are not production code and must not be imported by the scanner, automation jobs, CLI, dashboard, or provider layer.

## Purpose

Use notebooks to ask questions of the evidence collected by:

- `data/journal/decision_packets/`
- `data/journal/signal_rankings/`
- `research/prospective_validation_log.csv`
- `research/experiments/*.yaml`
- `backtesting/results/*`

## Initial Notebook Topics

- `h006_score_analysis.ipynb`: Check whether pre-entry scores predict realized trade quality.
- `score_bucket_analysis.ipynb`: Compare outcomes for score buckets such as `90+`, `80-89`, and `70-79`.
- `feature_importance.ipynb`: Compare features such as distance to long strike, IV rank, expected move, RSI, confirmation score, and market score.
- `semiconductor_review.ipynb`: Review rejected semiconductor hypotheses and search for structurally different explanations.

## Rules

1. Do not make production decisions directly inside notebooks.
2. Do not tune v4.2 based on partial forward evidence.
3. Treat notebook output as exploratory until promoted through the Strategy Registry and an Experiment Manifest.
4. Preserve rejected or inconclusive notebook findings when they materially change the research map.
5. If a notebook discovers a candidate rule, create a hypothesis before testing it as a strategy change.

## H-006 Prediction To Test

Prediction:

> Distance-to-long-strike will be more predictive than RSI.

This is not a rule. It is a measurable claim to test once enough prospective data exists.
