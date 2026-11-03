# v2 pilot: analysis plan

> **Summary:** The task is the unit. Each estimate is a paired drop per task (clean baseline rate minus cell rate, on the probability scale), averaged over admitted tasks, with a paired task bootstrap over envs with small strata merged as the primary interval, drawn jointly for all cells that share a clean baseline. Family F1 (names, two one-sided tests) is Holm-corrected; family F2 (landmarks and headings, four equivalence tests against a 10-point margin) is graded by 90% intervals; must-hold controls are tested at full alpha; everything else is exploratory. The rerun band is computed per cell and is descriptive. Variance components are fitted per kind for the main-study power simulation, which also respects the sealed pool's task caps. The analysis code is validated on simulated outcomes with each registered cell's exact env strata before any agent run.

Sources: DQ-analysis (`../../../ai-accessibility-paper/literature/syntheses/2026-10-29-DQ-analysis.md`) Options B and C and its "Common to every option" list; close-reads by key (`../../../ai-accessibility-paper/literature/papers/L_<key>.md`). Design terms (cells, M1-M10, stages) are defined in DESIGN.md.

## 1. Data and units

- Outcome: `success` from BreakingWeb's backend evaluator (`POST /api/env/<env>/evaluate`), 0 or 1 per run. No answer text is scored. Secondary outcomes: DESIGN.md §4.6.
- Unit of inference: the task. Repeats of a task in a cell are averaged into a per-task rate before anything else; pooling repeats as independent is inconsistent ([Miller2024](../../../ai-accessibility-paper/literature/papers/L_Miller2024.md), §3.1).
- Environments are a fixed, chosen set of seven apps; they are never resampled ([DOro2026](../../../ai-accessibility-paper/literature/papers/L_DOro2026.md), §4.3). BreakingWeb tasks are individually authored, so there is no template level above the task (ours, from the task YAMLs).
- Each (model, harness) pair is analysed separately; pooled results across models are descriptive. Contrasts between models or harnesses use the intersection of the admitted task sets (primary) and each set (sensitivity).

## 2. Estimands

For model m, harness h, cell c and exposure set E (on-path primary, on-path strict):

- **Drop.** Δ(m,h,c,E) = mean over tasks t in T(m,h,c,E) of [ȳ_clean(t) − ȳ_c(t)], where ȳ_clean is the mean of the baseline clean runs (c3-c6 in H1, c3-c5 in H2; screening runs c1-c2 are excluded) and ȳ_c the mean of the cell's valid runs. Positive = worse than clean. Points on the probability scale. The clean level of T and the relative drop Δ / ȳ_clean are reported beside every Δ.
  - Grounds: paired drop per task ([Miller2024](../../../ai-accessibility-paper/literature/papers/L_Miller2024.md), [Chen2026a](../../../ai-accessibility-paper/literature/papers/L_Chen2026a.md), [Yin2026](../../../ai-accessibility-paper/literature/papers/L_Yin2026.md), [Guan2026](../../../ai-accessibility-paper/literature/papers/L_Guan2026.md)); read against the clean level ([Taori2020](../../../ai-accessibility-paper/literature/papers/L_Taori2020.md), [Hendrycks2019](../../../ai-accessibility-paper/literature/papers/L_Hendrycks2019.md)).
- **Information effect (names).** I = mean over t of [ȳ_names+(t) − ȳ_names(t)] on names on-path tasks: the words restored with the variant's form held. **Form effect** F = mean over t of [ȳ_clean(t) − ȳ_names+(t)]. Δ_names = I + F per task. **Recovery** = I / Δ_names on strict tasks (E-N3), with a bootstrap interval of the ratio.
- **Dose (names).** On strict tasks, the drops of `names+` (0% of changed names lost), `names50` (half) and `names` (all) against clean; the linear trend in the lost share, by task bootstrap.
- **Label function effect.** Δ for `labels~`; the label information effect ȳ_labels~(t) − ȳ_labels(t) on labels on-path tasks.
- **Format effect.** Δ for `fmt_wrap` on all tasks; reported beside the landmarks Δ on the same tasks.
- **Harness contrast (names).** H = mean over tasks admitted in both harnesses of [Δ_H1(t) − Δ_H2(t)], each harness against its own clean baseline.
- **Weights.** Every task weighs equally. Reported beside it as sensitivity analyses: the env-weighted mean (each env equal; [Hendrycks2019](../../../ai-accessibility-paper/literature/papers/L_Hendrycks2019.md)), the env-matched subset (amazon, booking, gmail, reddit, robinhood), and for names strict the estimate without amazon. Per-env drops are reported for every cell.
- Interactions are never read from a logit coefficient alone: the probability-scale difference is the estimand ([McCabe2021](../../../ai-accessibility-paper/literature/papers/L_McCabe2021.md), [Chen2011](../../../ai-accessibility-paper/literature/papers/L_Chen2011.md)).

## 3. Noise: the rerun band

- **Clean-bundle runs.** In H1 each task has 4 baseline clean runs and 3 `none` runs. `none` is the clean bundle served through its own checkout, process and port, like a variant (DESIGN.md §3), so the 7 runs are the clean page under both serving paths. They are pooled into the band by design: a serving difference then widens the band, which is the noise every kind-vs-clean comparison carries. In H2: 3 baseline and 3 `none` runs.
- **Band, per cell.** For cell c with repeat count R_c and task set T(m,h,c,E): for each task, split its clean-bundle runs at random into a "baseline" of 4 and a "cell" of R_c (3, or 2 for `pos_info` and `pc_break`; in H2, 3 and 3), compute Δ over exactly T(m,h,c,E), and repeat with tasks resampled as in §4.1 (10,000 draws). The band is the central 95% of that distribution.
  - Grounds: "Treat a difference smaller than the rerun band as unresolved, not as small." ([Wei2026](../../../ai-accessibility-paper/literature/papers/L_Wei2026.md), §9, p. 8), who also say the band is not a significance test. Its width falls roughly with the square root of the task count, so one band per (model, harness) would be about 1.6 times too narrow at 24 tasks (`precision.json`, ours).
  - Use: descriptive. An estimate inside its cell's band is described as such. Grades come only from the tests of §5.
- **Also reported:** pairwise run disagreement within task, the number of tasks with any disagreement, and the half-vs-half aggregate difference (c3+c4 vs c5+c6) with its interval (E-R1, E-R2).

## 4. Models

### 4.1 Primary interval: paired task bootstrap

- **Strata.** Per cell: envs with at least 5 tasks in the cell are strata; the remaining envs are merged into one stratum; if that merged stratum has fewer than 5 tasks, it joins the smallest stratum. Example, names strict (amazon 10, robinhood 5, gmail 4, booking 2, patient portal 2, reddit 1): strata amazon (10), robinhood (5), other (9). Grounds: a stratum of 1 adds no bootstrap variance and a stratum of 2 adds about half its true variance, so unmerged small strata make the interval too narrow (ours).
- **Draws.** 10,000 draws; tasks resampled with replacement within strata. Draws are joint across all cells of a (model, harness): one draw picks one multiset of tasks, and every cell's Δ, every contrast between cells and every band uses it, because the cells share the clean baseline and their estimates are correlated.
- **Outputs.** Percentile 95% interval (90% for F2), and one-sided p-values for F1 (share of draws at or below 0). A t interval over tasks, t(G−1), is reported beside it.
- **Fallback, fixed now.** If the §7 coverage simulation on a registered cell's exact strata gives below 92%, the unstratified task bootstrap is primary for that cell; if that is also below 92%, the t interval is primary.
- Grounds: DQ-analysis Option B ([Miller2024](../../../ai-accessibility-paper/literature/papers/L_Miller2024.md), [Chen2026a](../../../ai-accessibility-paper/literature/papers/L_Chen2026a.md), [Yin2026](../../../ai-accessibility-paper/literature/papers/L_Yin2026.md), [Guan2026](../../../ai-accessibility-paper/literature/papers/L_Guan2026.md), [DOro2026](../../../ai-accessibility-paper/literature/papers/L_DOro2026.md)). The bootstrap is primary because the pilot's cells have 10 to 64 tasks and tier-A clean rates sit near the ceiling, where logistic fits are unstable; the synthesis's own switch rule makes B primary in that case (DQ-analysis, Recommendation).

### 4.2 Variance components: logistic mixed model, per kind

For each (model, harness) and each kind k, fitted on the baseline clean runs plus the runs of k's cells (the kind and its controls: names with `names+` and `names50`; labels with `labels~`; landmarks with `fmt_wrap`):

`success ~ cell + env + (1 | task) + (1 | task:cell)`

with clean as the reference level; `task:cell` carries effect heterogeneity across tasks for that kind only; the binomial residual carries run noise. A single model over all cells would fit one task-by-cell variance shared by `none` and the null-predicted cells, pulling it toward 0 for names and labels.

- Outputs per kind: σ_task (logit), τ_k, the within-task (run) variance on the probability scale, the ratio of task-by-cell to within-task variance, and the intraclass correlation. Intervals by parametric bootstrap (1,000 refits), not Wald.
- A crossed fit (`cell * model + env + (1 | task) + (1 | task:cell) + (1 | task:model)`) on H1 data uses the tasks admitted for both models; it is descriptive.
- A linear probability mixed model with the same terms is fitted as a check (MandujanoReyes2026's form): contrast standard errors close to unpaired ones mean the pairing term is missing.
- Implementation (lme4 `glmer` or an equivalent Laplace fit) is fixed in Stage 0 and validated in §7. A fit that does not converge is reported; its components are then taken from the linear fit.
- Grounds: condition fixed, item random, item term required ([MandujanoReyes2026](../../../ai-accessibility-paper/literature/papers/L_MandujanoReyes2026.md), §6); problem and problem-by-run terms ([AlvaradoGonzalez2025](../../../ai-accessibility-paper/literature/papers/L_AlvaradoGonzalez2025.md)); variance terms for power simulation ([Card2020](../../../ai-accessibility-paper/literature/papers/L_Card2020.md)). The mixed model gives no grade.

### 4.3 Between-task analyses (exploratory)

- **Dose within kind, names and labels.** Per-task drop d_t on the number of acted-on controls that lose their name on the path (0 to 34 for names), with env fixed effects and the task's screening clean rate (c1-c2) as the difficulty covariate. The baseline clean rate is not used as a covariate: it is part of d_t, so its sampling error would sit on both sides of the regression.
- **Observation-diff covariate.** d_t on the task-level lines and tokens changed between clean and variant H1 observations over the replay states (DESIGN.md §4.5), per kind, with env fixed effects.
- **Per-run descriptors.** Observation tokens per step, history-trim step and block date, reported per cell; the before/after-fix slot of any infrastructure fix enters as a covariate.
- **Realised exposure (M5).** The same models with the run-level realised flag; post-treatment, so descriptive only.
- No on-path versus off-path contrast: there are no off-path cells (DESIGN.md §4.2).

### 4.4 Single-task and single-cell rates

Wilson intervals for a task's rate in a cell (repeat counts of 2 to 6; [DOro2026](../../../ai-accessibility-paper/literature/papers/L_DOro2026.md) §6.1, [McGrath2021](../../../ai-accessibility-paper/literature/papers/L_McGrath2021.md)). Never used for cell-level inference.

## 5. Families and grades

- **F1 (directional):** PC1, PC2 (names strict, H1, Opus 5.5 and GPT-5.6-sol). Two one-sided bootstrap p-values for drop > 0, Holm at family-wise 0.05 (first step 0.025, second 0.05). Hit if Holm rejects; miss if the upper 95% bound is below 10; otherwise unresolved. Holm controls family-wise error under any dependence between the two tests; what §7 checks is whether the bootstrap p-values are calibrated at these strata and task counts.
- **F2 (equivalence):** PC3-PC6 (landmarks, headings; H1; both models), on tasks that passed M10. Each graded by its 90% bootstrap interval against the margin of 10 points: hit if the upper bound is below 10; miss if the lower bound is above 10; otherwise unresolved. No multiplicity adjustment: each is a separate claim, and the joint claim over the four is an intersection-union test (ours).
- **Must-hold controls:** MH1 (`none`, two-sided at 0.05, fails if it rejects), MH3 (`pos_info`, one-sided at 0.05, fails if it does not reject), MH2 and MH5 (counts and identity checks). Uncorrected, because a control that fails must be seen ([Gorgen2018](../../../ai-accessibility-paper/literature/papers/L_Gorgen2018.md), p. 15).
- **Exploratory:** every other contrast (kinds x exposure x model x harness, `names+`, `names50`, `labels~`, `fmt_wrap`, `pc_break`, contrasts, regressions) with unadjusted 95% intervals, the cell's band, and the label "exploratory". The number computed is reported, including those not shown ([Chandrahas2026](../../../ai-accessibility-paper/literature/papers/L_Chandrahas2026.md)).
- Grounds for small, fixed families: family-wise control for a few confirmatory contrasts against one baseline, family fixed in advance ([Chen2017](../../../ai-accessibility-paper/literature/papers/L_Chen2017.md); DQ-analysis finding 9). Power of every registered test: PREDICTIONS.md §1-2 and `power.json`.

## 6. Inclusion, exclusion and missing data

- **Admission (per model and harness):** at least 1 of 2 screening clean runs succeeds (DESIGN.md §5). Sensitivity: all tasks, admitted or not.
- **Run validity:** a run counts if M1 passes and it is neither infra-failed (M8) nor call-failed after retries (M7). Excluded runs are rerun up to twice; runs still missing are missing. Any cell with missing runs gets a bounds analysis: Δ with every missing run counted as failure, and as success.
- **Residuals (M4):** never a per-run exclusion. A residual in any run makes the (env, build) a delivery defect; the build is fixed, re-gated and all its runs rerun. The original runs are analysed as assigned in a sensitivity analysis.
- **Agent behaviour stays in:** refusals, empty or truncated outputs, wall-cap and step-cap hits are failures in the primary outcome, counted per cell, and excluded only in the secondary outcome "success without a step-cap or truncation failure".
- **Task-cell exclusion before any run:** M2, M3, M3a, M9; M10 for F2 only. Logged with reason.
- **Minimum data per task and cell:** at least 3 valid baseline runs and at least 2 valid cell runs; otherwise the task leaves that cell's estimate and is counted.
- **A cell is reported as "not tested"** if it keeps fewer than 8 tasks.
- No exclusion uses a variant outcome, and no exclusion is added after Stage 2 starts without a numbered deviation.

## 7. Validation on simulated outcomes (Stage 0, before any agent run)

Using the real run matrix (`cells_by_task.json`) with each registered cell's exact env strata, simulate outcomes from the model of `pilot_precision.py` on its grid (σ_task 1.0 to 3.0, τ 0 to 0.8, clean rate 0.6 to 0.9, ceiling share 0 and 0.3; admission simulated), 2,000 data sets per setting, and run the full analysis code on each.

| Scenario | Truth | Pass criterion |
|---|---|---|
| Null | every cell equals clean | F1 family-wise rejection 2-8%; MH1 rejection 2-8%; per-cell band contains 0 in 93-97% |
| Margin | landmarks and headings drop exactly 10 | F2 hit rate at most 5% per test |
| Known effect | names strict drop 15, `pos_info` drop 40, rest null | F1 rejection rate within 5 points of the rate `pilot_precision.py` gives for the same setting; MH3 detected in at least 95%. This is a code check: both use the same generating model |
| Nuisance only | env and task-length effects on the clean rate, no cell effect | rejection as under the null |
| Ceiling | 30% of tasks at p ≈ 1 in clean | rejection and coverage as under the null |
| Near-deterministic | every task at p ≤ 0.02 or ≥ 0.98 in clean, as in the scripted replay (every reference task 0/3 or 3/3) | coverage as below |
| Drift | clean rate changes by 5 points between day blocks, equally in every cell | rejection as under the null |
| Coverage | each scenario | intervals cover the true Δ in 92-97% for every registered cell (F1, F2, MH1, MH3) on its exact strata; otherwise the §4.1 fallback applies to that cell |

Grounds: a test rejected the null in 33% of 10,000 simulated null instances where 5% was expected ([Gorgen2018](../../../ai-accessibility-paper/literature/papers/L_Gorgen2018.md), p. 20); coverage of clustered intervals at small cluster counts is unverified at our scale (DQ-analysis Gaps). A failed criterion is fixed and the simulation rerun before Stage 0r.

## 8. Sizing the main study from the pilot

1. Take σ_task, τ_k per kind, the within-task variance and the clean rate per model from §4.2, with their parametric-bootstrap distributions. Env enters as a fixed effect and the components are reweighted to the sealed set's env composition (amazon 27, booking 16, gmail 15, reddit 19, robinhood 11), because the pilot holds every lms and patient-portal task and the sealed set none.
2. Simulate the main design on a grid of repeats (clean R 4 to 8, cell R 2 to 5) at the task counts the sealed pool allows (47 strict names, 67 primary names, 23 strict labels, 88 for page kinds; plus any new reference tasks), and compute the power to detect the drop Alex sets (DESIGN.md §10, item 7) under the main family's correction. The simulation runs twice: at the point estimates and at the 80th percentile of the bootstrap distribution of each τ_k and the within-task variance; a percentile above the grid maximum is set to τ = 1.0 and reported.
3. Cost each grid point with the pilot's measured tokens and steps per run, per model and harness.
4. Choose the cheapest point with at least 80% power at the 80th-percentile components. If no point within the sealed caps reaches it, more reference tasks are needed (DESIGN.md §5 rule).

- The tasks-versus-repeats split follows from the per-kind ratio of task-by-cell to within-task variance: repeats lower only the within-task term ([Miller2024](../../../ai-accessibility-paper/literature/papers/L_Miller2024.md); [Nam2011](../../../ai-accessibility-paper/literature/papers/L_Nam2011.md)). The half-vs-half band width is not used for it.
- Before any pilot data, `mde_sealed.json` gives the same calculation over the full grid (DESIGN.md §5 table).
- Power comes from the variance components and the chosen minimum drop, never from the pilot's effect estimates ([Card2020](../../../ai-accessibility-paper/literature/papers/L_Card2020.md) advises against post-hoc power; its application to the pilot case is ours).
- No kind is dropped from the main study because of its pilot estimate; a kind leaves only if a manipulation check fails or Alex removes it with a stated reason (ours).
- **What the pilot can change, and the contrast that decides it.** Each needs the named contrast's 95% interval to exclude 0 and its estimate to lie outside the cell's band:
  - `names+` kept in every main-study names cell: recovery I / Δ_names below 0.5 (E-N3).
  - `fmt_wrap` kept beside landmarks: `fmt_wrap` drop (E-F1).
  - `labels~` kept beside labels: `labels~` drop (E-L3).
  - Kind by model registered as a confirmatory interaction: E-M2.
  - Harness set: H2 dropped if the H2 names drop is inside its band and H is not resolved.
  - Exposure definition: realised versus assigned agreement below 90% on clean and `none` runs (a count; no interval needed).

## 9. Reporting

- Per model, per harness, per env and pooled; clean level beside each drop; the cell's band beside each estimate; every exclusion and missing run counted per cell.
- Tables labelled F1, F2, must-hold or exploratory ([Wei2026](../../../ai-accessibility-paper/literature/papers/L_Wei2026.md), [Hofman2023](../../../ai-accessibility-paper/literature/papers/L_Hofman2023.md)).
- Every registered prediction graded hit, miss, unresolved or not tested (PREDICTIONS.md §7); failed predictions reported as failed.
- Secondary outcomes, tokens, steps, wall-clock, refusals, truncations and history trims per cell; Bedrock model ids, regions and reasoning settings per run.
- Sensitivity analyses: all tasks (admission ignored), env-weighted, env-matched subset, names strict without amazon, bounds for missing runs, M4 as-assigned runs, evaluator-audited outcomes for flagged cells, before/after-fix slot.
- A numbered deviation log ([Chen2026a](../../../ai-accessibility-paper/literature/papers/L_Chen2026a.md)).

Stopping rules are in DESIGN.md §7. They act only on infrastructure, clean rates and cost, never on variant outcomes, and no variant result is read before Stage 3.
