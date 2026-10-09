# Open-source model validation plan

Date: 2026-10-09

## Purpose

Evaluate external football-prediction projects as research baselines for this repository. Do not promote a model into live recommendations based only on its README or reported accuracy.

## Candidates

- FootWork: https://github.com/lrivals/FootWork
  - Multi-class 1X2 model, probability calibration, and seven historical betting simulations.
  - Its README describes six leagues and a test period beginning in 2022. Its reported setup does not establish Turkish-league or Nesine compatibility.
- Football Value Model: https://github.com/janpruzinec/football-value-model
  - Walk-forward evaluation of 1X2 and over/under 2.5, including a comparison against de-vigged bookmaker prices.
  - Its README reports that the market baseline outperformed its tested models. Treat this as a useful caution, not a claim that the model is profitable.

## Validation gates

1. Verify the license and dependency requirements before copying or importing code.
2. Use chronological train/calibration/test splits; never let future results leak into features.
3. Require actual historical odds for any return-on-investment calculation. Never infer or fabricate missing odds.
4. Report log-loss, Brier score, calibration, hit rate, number of bets, ROI, drawdown, and closing-line value when closing odds are available.
5. Compare every model with a bookmaker-implied, margin-adjusted baseline on the same matches.
6. Separate leagues and markets; do not assume performance transfers to Turkish leagues, Nesine, HT/FT, corners, or cards.
7. Keep the live system in NO BET mode when source coverage, odds, or sample size is inadequate.

## Current status

Source code and project documentation have been inspected, but these external models have not yet been executed in this repository. No independent profitability claim is made. The existing analyzer remains the operational project; this document records the criteria for evaluating external baselines before integration.
