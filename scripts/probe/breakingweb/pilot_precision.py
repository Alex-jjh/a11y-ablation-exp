"""Precision, power and smallest detectable drop for the v2 pilot and the main study (ours).

No LLM, no environment. Planning model only; the registered primary interval is the
task bootstrap (studies/v2-pilot/ANALYSIS.md section 4.1); here a t test over per-task
differences stands in for it (ours).

Model, per (model, harness):
  - a task's clean success probability: with probability `ceil` the task is at the
    ceiling (logit 6, p ~ 0.998); otherwise logit ~ N(mu, sigma_task). mu is solved so
    that the mean clean probability over tasks equals `p_clean`.
  - a cell shifts each task's logit by -(delta + u), u ~ N(0, tau). delta is solved so
    that the MEAN PROBABILITY-SCALE DROP over admitted tasks equals `drop` points (the
    estimand of ANALYSIS.md section 2). Under the null, delta = u = 0.
  - admission inside the simulation: 2 screening clean runs, task admitted if >= 1
    succeeds; screening runs are not used as baseline.
  - Rc baseline clean runs and Rv cell runs per task, binomial given the task's p.
  - statistic: mean over admitted tasks of (clean rate - cell rate); t over tasks.

Outputs (OUT, default /tmp/amt-syn/pilot/; the small files are copied to studies/v2-pilot/)
  precision.json   per config: implied clean rate, admission share, pairwise run
                   disagreement, half-vs-half band half-width at 64 tasks; null 95%
                   half-width by task count (before admission) for 4 vs 3 runs
  power.json       pilot tests: PC1/PC2 one-sided (alpha 0.025 and 0.05; and the
                   superseded two-sided Holm-6 first step 0.05/6), PC3-PC6 TOST at
                   margins 5 and 10, MH1 sensitivity, MH3/MH4 lower-bound rule
  mde_sealed.json  main study on the sealed pool: smallest mean drop detected with 80%
                   power, one-sided alpha 0.025, at the sealed caps (47 strict names,
                   67 primary names, 23 strict labels, 88 landmarks/headings), for
                   repeat counts (Rc, Rv) in {(4,3), (8,5), (50,50)}

Run
  ~/.workspace/ai-agent-accessibility/analysis/.venv/bin/python pilot_precision.py [OUT]
  (needs numpy and scipy; under a minute on 16 cores). MH1 power is computed as the one-sided 0.025 tail, which equals two-sided 0.05 power up to the negligible opposite tail.
"""
import itertools
import json
import os
import sys

import numpy as np
from scipy import stats

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/amt-syn/pilot"
REPS = 2000
CEIL_LOGIT = 6.0


def expit(x):
    return 1 / (1 + np.exp(-x))


def solve_mu(p_clean, s_task, ceil, rng):
    z = rng.normal(0, 1, 200_000)
    lo, hi = -8.0, 8.0
    for _ in range(60):
        mid = (lo + hi) / 2
        m = ceil * expit(CEIL_LOGIT) + (1 - ceil) * expit(mid + s_task * z).mean()
        lo, hi = (mid, hi) if m < p_clean else (lo, mid)
    return (lo + hi) / 2


class Pop:
    """Task population for one config; draws clean logits and solves delta for a drop."""

    def __init__(self, p_clean, s_task, tau, ceil, seed=7):
        self.p_clean, self.s_task, self.tau, self.ceil = p_clean, s_task, tau, ceil
        rng = np.random.default_rng(seed)
        self.mu = solve_mu(p_clean, s_task, ceil, rng)
        n = 200_000
        self.a = np.where(rng.random(n) < ceil, CEIL_LOGIT, rng.normal(self.mu, s_task, n))
        self.u = rng.normal(0, tau, n)
        pc = expit(self.a)
        self.w = 1 - (1 - pc) ** 2
        self.pc = pc
        self._delta = {}

    def delta(self, drop):
        if drop == 0:
            return 0.0
        if drop in self._delta:
            return self._delta[drop]
        lo, hi = 0.0, 20.0
        for _ in range(50):
            mid = (lo + hi) / 2
            pv = expit(self.a - mid - self.u)
            m = 100 * np.sum(self.w * (self.pc - pv)) / np.sum(self.w)
            lo, hi = (mid, hi) if m < drop else (lo, mid)
        self._delta[drop] = (lo + hi) / 2
        return self._delta[drop]

    def implied(self):
        w = self.w
        disagree = np.sum(w * 2 * self.pc * (1 - self.pc)) / np.sum(w)
        return dict(mean_clean=round(float(self.pc.mean()), 3), admitted_share=round(float(w.mean()), 3),
                    pairwise_disagreement_admitted=round(float(disagree), 3))

    def draw(self, rng, n, drop, Rc, Rv, reps=REPS):
        """Per-task differences (clean - cell) for admitted tasks; NaN for not admitted."""
        a = np.where(rng.random((reps, n)) < self.ceil, CEIL_LOGIT, rng.normal(self.mu, self.s_task, (reps, n)))
        pc = expit(a)
        if drop == 0:
            pv = pc
        else:
            pv = expit(a - self.delta(drop) - rng.normal(0, self.tau, (reps, n)))
        adm = rng.binomial(2, pc) >= 1
        yc = rng.binomial(Rc, pc) / Rc
        yv = rng.binomial(Rv, pv) / Rv
        d = np.where(adm, yc - yv, np.nan)
        return d


def tstats(d):
    g = np.sum(~np.isnan(d), axis=1)
    m = np.nanmean(d, axis=1)
    s = np.nanstd(d, axis=1, ddof=1)
    se = s / np.sqrt(g)
    se = np.where(se == 0, 1e-9, se)
    return m, se, g


def onesided_power(d, alpha):
    m, se, g = tstats(d)
    crit = stats.t.ppf(1 - alpha, np.maximum(g - 1, 1))
    return float(np.mean(m / se > crit))


def halfwidth(d, conf=0.95):
    m, se, g = tstats(d)
    return float(np.mean(stats.t.ppf(1 - (1 - conf) / 2, np.maximum(g - 1, 1)) * se))


def tost(d, margin):
    """Null prediction graded by the 90% interval: hit if upper < margin, miss if lower > margin."""
    m, se, g = tstats(d)
    c = stats.t.ppf(0.95, np.maximum(g - 1, 1)) * se
    up, lo = 100 * (m + c), 100 * (m - c)
    return dict(hit=round(float(np.mean(up < margin)), 3), miss=round(float(np.mean(lo > margin)), 3))


CONFIGS = [dict(p_clean=p, s_task=s, tau=t, ceil=c)
           for p, s, t, c in itertools.product((0.6, 0.7, 0.8, 0.9), (1.0, 1.5, 2.0, 3.0), (0.0, 0.5, 0.8), (0.0, 0.3))]
# Reference config for the pilot tables: the old pilot_precision.py values (sigma 1.5, tau 0.5,
# no ceiling) at clean 0.7, plus one config consistent with E-R2 (disagreement 8-20%).
REF = [dict(p_clean=0.7, s_task=1.5, tau=0.5, ceil=0.0), dict(p_clean=0.8, s_task=3.0, tau=0.5, ceil=0.3),
       dict(p_clean=0.9, s_task=3.0, tau=0.5, ceil=0.3)]


def key(c):
    return f"p{c['p_clean']}_s{c['s_task']}_t{c['tau']}_c{c['ceil']}"


def precision_block(cfg, rng):
    pop = Pop(**cfg)
    out = dict(config=cfg, **pop.implied())
    # half-vs-half band at 64 tasks: 2 vs 2 baseline runs
    out["half_vs_half_95hw_64"] = round(100 * halfwidth(pop.draw(rng, 64, 0, 2, 2)), 1)
    out["null_95hw_by_n_4v3"] = {n: round(100 * halfwidth(pop.draw(rng, n, 0, 4, 3)), 1) for n in (10, 24, 29, 46, 53, 62, 64)}
    out["null_95hw_by_n_4v2"] = {n: round(100 * halfwidth(pop.draw(rng, n, 0, 4, 2)), 1) for n in (24,)}
    return out


def power_block(cfg, rng):
    pop = Pop(**cfg)
    r = dict(config=cfg)
    r["PC1_PC2_n24_power"] = {
        str(dd): dict(one_sided_0025=round(onesided_power(pop.draw(rng, 24, dd, 4, 3), 0.025), 2),
                      one_sided_005=round(onesided_power(pop.draw(rng, 24, dd, 4, 3), 0.05), 2),
                      old_two_sided_holm6_first=round(onesided_power(pop.draw(rng, 24, dd, 4, 3), 0.05 / 12), 2))
        for dd in (10, 15, 20, 30)}
    r["PC1_PC2_n53_primary_power_0025"] = {str(dd): round(onesided_power(pop.draw(rng, 53, dd, 4, 3), 0.025), 2)
                                          for dd in (5, 10, 15)}
    r["PC3_PC6_n62_tost"] = {f"margin{mg}_true{dd}": tost(pop.draw(rng, 62, dd, 4, 3), mg)
                             for mg in (5, 10) for dd in (0, 5, 10, 15)}
    r["MH1_n64_two_sided_005_power"] = {str(dd): round(onesided_power(pop.draw(rng, 64, dd, 4, 3), 0.025), 2)
                                        for dd in (5, 10, 15)}
    lb = {}
    for dd in (20, 30, 40):
        d = pop.draw(rng, 24, dd, 4, 2)
        m, se, g = tstats(d)
        lower = 100 * (m - stats.t.ppf(0.975, np.maximum(g - 1, 1)) * se)
        lb[str(dd)] = round(float(np.mean(lower >= 15)), 2)
    r["MH3_MH4_n24_4v2_P_lower95_ge15"] = lb
    r["names50_n24_power_0025"] = {str(dd): round(onesided_power(pop.draw(rng, 24, dd, 4, 3), 0.025), 2) for dd in (5, 10)}
    return r


def mde(pop, rng, n, Rc, Rv, alpha=0.025, target=0.8):
    for dd in np.arange(2.5, 50.01, 2.5):
        if onesided_power(pop.draw(rng, n, float(dd), Rc, Rv, reps=1000), alpha) >= target:
            return float(dd)
    return None


def mde_block(cfg, seed):
    rng = np.random.default_rng(seed)
    pop = Pop(**cfg)
    res = dict(config=cfg, **pop.implied())
    for name, n in (("names_strict_47", 47), ("names_primary_67", 67), ("labels_strict_23", 23), ("all_88", 88)):
        res[name] = {f"{Rc}v{Rv}": mde(pop, rng, n, Rc, Rv) for Rc, Rv in ((4, 3), (8, 5), (50, 50))}
    return res


def main():
    os.makedirs(OUT, exist_ok=True)
    rng = np.random.default_rng(1)
    prec = [precision_block(c, rng) for c in REF]
    # implied disagreement over the whole grid (cheap)
    grid = [dict(config=c, **Pop(**c).implied()) for c in CONFIGS]
    json.dump(dict(reference_configs=prec, grid_implied=grid), open(os.path.join(OUT, "precision.json"), "w"), indent=1)
    pw = [power_block(c, rng) for c in REF]
    json.dump(pw, open(os.path.join(OUT, "power.json"), "w"), indent=1)
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(14) as ex:
        md = list(ex.map(mde_block, CONFIGS, range(len(CONFIGS))))
    summ = {}
    for name in ("names_strict_47", "names_primary_67", "labels_strict_23", "all_88"):
        for rr in ("4v3", "8v5", "50v50"):
            vals = [m[name][rr] if m[name][rr] is not None else 99 for m in md]
            plaus = [m[name][rr] if m[name][rr] is not None else 99 for m in md
                     if 0.08 <= m["pairwise_disagreement_admitted"] <= 0.20]
            summ[f"{name}/{rr}"] = dict(min=min(vals), median=float(np.median(vals)), max=max(vals),
                                        median_if_disagreement_8_20=float(np.median(plaus)) if plaus else None,
                                        n_configs_disagreement_8_20=len(plaus))
    json.dump(dict(note="99 = not reached by 50 points", summary=summ, configs=md),
              open(os.path.join(OUT, "mde_sealed.json"), "w"), indent=1)
    print(json.dumps(prec, indent=1))
    print(json.dumps(pw, indent=1))
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
