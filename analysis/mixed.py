from __future__ import annotations
from dataclasses import dataclass, asdict
import numpy as np
from scipy import optimize, stats
from scipy.special import expit

LOG_SIGMA_FLOOR = np.log(1e-4)
GH_NODES = 41
_Z, _W = np.polynomial.hermite.hermgauss(GH_NODES)
_LOGW = np.log(_W) + _Z ** 2

def _group_loglik(theta: np.ndarray, X: np.ndarray, y: np.ndarray, u: float) -> float:
    eta = X @ theta + u
    return float(np.sum(y * eta - np.logaddexp(0.0, eta)))

def _group_marginal(theta: np.ndarray, log_sigma: float, X: np.ndarray, y: np.ndarray) -> float:
    sigma = np.exp(log_sigma)
    eta0 = X @ theta

    def negf(u: float) -> float:
        return -(_group_loglik(theta, X, y, u) - 0.5 * (u / sigma) ** 2 - np.log(sigma) - 0.5 * np.log(2 * np.pi))

    def grad(u: float) -> float:
        p = expit(eta0 + u)
        return -(np.sum(y - p) - u / sigma ** 2)

    def hess(u: float) -> float:
        p = expit(eta0 + u)
        return float(np.sum(p * (1 - p)) + 1.0 / sigma ** 2)

    u = 0.0
    f = negf(u)
    for _ in range(100):
        step = grad(u) / hess(u)
        t = 1.0
        while t > 1e-8:
            cand = u - t * step
            fc = negf(cand)
            if fc <= f:
                u, f = cand, fc
                break
            t *= 0.5
        if abs(t * step) < 1e-10:
            break
    h = hess(u)
    scale = np.sqrt(2.0 / h)
    nodes = u + scale * _Z
    vals = np.array([-negf(v) for v in nodes])
    return float(np.log(scale) + np.logaddexp.reduce(_LOGW + vals))

def marginal_loglik(params: np.ndarray, groups: list[tuple[np.ndarray, np.ndarray]]) -> float:
    theta, log_sigma = params[:-1], params[-1]
    return sum(_group_marginal(theta, log_sigma, X, y) for X, y in groups)

@dataclass
class MixedFit:
    beta: list[float]
    sigma: float
    loglik: float
    converged: bool
    boundary: bool
    message: str
    wald_se: list[float]

def fit_mixed(groups: list[tuple[np.ndarray, np.ndarray]], p: int) -> MixedFit:
    x0 = np.zeros(p + 1)
    x0[-1] = 0.0
    bounds = [(None, None)] * p + [(LOG_SIGMA_FLOOR, 5.0)]

    def obj(v: np.ndarray) -> float:
        return -marginal_loglik(v, groups)

    res = optimize.minimize(obj, x0, method="L-BFGS-B", bounds=bounds,
                            options={"ftol": 1e-12, "gtol": 1e-8, "maxiter": 500})
    ll = -float(res.fun)
    beta = res.x[:p]
    boundary = bool(np.exp(res.x[-1]) < 1e-3)
    hess = _numeric_hessian(lambda b: -marginal_loglik(np.append(b, res.x[-1]), groups), beta)
    try:
        cov = np.linalg.inv(hess)
        se = np.sqrt(np.diag(cov))
        hess_ok = bool(np.all(np.isfinite(se)))
    except np.linalg.LinAlgError:
        se = np.full(p, np.nan)
        hess_ok = False
    converged = bool(res.success) and np.isfinite(ll) and hess_ok
    return MixedFit([float(b) for b in beta], float(np.exp(res.x[-1])), ll, converged, boundary,
                    str(res.message), [float(s) for s in se])

def _numeric_hessian(f, x: np.ndarray, h: float = 1e-4) -> np.ndarray:
    n = len(x)
    H = np.zeros((n, n))
    f0 = f(x)
    for i in range(n):
        for j in range(i, n):
            xpp = x.copy(); xpp[i] += h; xpp[j] += h
            xpm = x.copy(); xpm[i] += h; xpm[j] -= h
            xmp = x.copy(); xmp[i] -= h; xmp[j] += h
            xmm = x.copy(); xmm[i] -= h; xmm[j] -= h
            H[i, j] = H[j, i] = (f(xpp) - f(xpm) - f(xmp) + f(xmm)) / (4 * h * h)
    if n == 1:
        xp = x.copy(); xp[0] += h
        xm = x.copy(); xm[0] -= h
        H[0, 0] = (f(xp) - 2 * f0 + f(xm)) / (h * h)
    return H

def profile_ci(groups: list[tuple[np.ndarray, np.ndarray]], full: MixedFit, level: float = 0.95) -> tuple[float, float]:
    crit = stats.chi2.ppf(level, 1) / 2.0
    b1_hat = full.beta[1]

    def profile(b1: float) -> float:
        def obj(v: np.ndarray) -> float:
            params = np.array([v[0], b1, v[1]])
            return -marginal_loglik(params, groups)
        res = optimize.minimize(obj, np.array([full.beta[0], np.log(full.sigma)]), method="L-BFGS-B",
                                bounds=[(None, None), (LOG_SIGMA_FLOOR, 5.0)])
        return -float(res.fun)

    def root(b1: float) -> float:
        return full.loglik - profile(b1) - crit

    step = max(4 * (full.wald_se[1] if np.isfinite(full.wald_se[1]) else 1.0), 0.5)
    lo_b = b1_hat - step
    while root(lo_b) < 0 and step < 50:
        step *= 2
        lo_b = b1_hat - step
    hi_b = b1_hat + step
    while root(hi_b) < 0 and step < 50:
        step *= 2
        hi_b = b1_hat + step
    lo = optimize.brentq(root, lo_b, b1_hat) if root(lo_b) > 0 else float("-inf")
    hi = optimize.brentq(root, b1_hat, hi_b) if root(hi_b) > 0 else float("inf")
    return float(lo), float(hi)

@dataclass
class PrimaryResult:
    method: str
    n: int
    n_present: int
    n_control: int
    k_present: int
    k_control: int
    rate_present: float
    rate_control: float
    log_odds_ratio: float | None
    odds_ratio: float | None
    ci95_low: float | None
    ci95_high: float | None
    wald_se: float | None
    intercept: float | None
    sigma_project: float | None
    loglik_full: float | None
    loglik_null: float | None
    lrt_statistic: float | None
    lrt_df: int | None
    p_value: float
    converged: bool
    boundary_variance: bool
    optimizer_message: str
    fallback_reason: str | None
    fallback_details: dict | None

    def to_dict(self) -> dict:
        return asdict(self)

def primary_contrast(project: np.ndarray, present: np.ndarray, y: np.ndarray,
                     permutations: int = 10000, seed: int = 0) -> PrimaryResult:
    project = np.asarray(project)
    present = np.asarray(present, dtype=float)
    y = np.asarray(y, dtype=float)
    groups_full, groups_null = [], []
    for g in sorted(set(project)):
        m = project == g
        groups_full.append((np.column_stack([np.ones(m.sum()), present[m]]), y[m]))
        groups_null.append((np.ones((m.sum(), 1)), y[m]))
    counts = dict(n=int(len(y)), n_present=int(present.sum()), n_control=int((1 - present).sum()),
                  k_present=int(y[present == 1].sum()), k_control=int(y[present == 0].sum()))
    counts["rate_present"] = counts["k_present"] / counts["n_present"]
    counts["rate_control"] = counts["k_control"] / counts["n_control"]

    separated = counts["k_control"] == 0 or counts["k_present"] == 0 or \
        counts["k_control"] == counts["n_control"] or counts["k_present"] == counts["n_present"]
    full = fit_mixed(groups_full, 2)
    null = fit_mixed(groups_null, 1)
    if full.converged and null.converged and not separated:
        lrt = 2.0 * (full.loglik - null.loglik)
        lrt = max(lrt, 0.0)
        pval = float(stats.chi2.sf(lrt, 1))
        lo, hi = profile_ci(groups_full, full)
        return PrimaryResult("mixed_logistic_lrt", **counts, log_odds_ratio=full.beta[1],
                             odds_ratio=float(np.exp(full.beta[1])), ci95_low=lo, ci95_high=hi,
                             wald_se=full.wald_se[1], intercept=full.beta[0], sigma_project=full.sigma,
                             loglik_full=full.loglik, loglik_null=null.loglik, lrt_statistic=lrt, lrt_df=1,
                             p_value=pval, converged=True, boundary_variance=full.boundary or null.boundary,
                             optimizer_message=full.message, fallback_reason=None, fallback_details=None)
    reason = (f"separation: one arm of the contrast has no verification-positive or no verification-negative trials "
              f"(present {counts['k_present']}/{counts['n_present']}, control {counts['k_control']}/{counts['n_control']}), "
              f"so the maximum likelihood estimate of the contrast does not exist; " if separated else "") + \
        f"full: {full.message} (converged={full.converged}); null: {null.message} (converged={null.converged})"
    fb = stratified_exact_permutation(project, present, y, permutations, seed)
    return PrimaryResult("stratified_fisher_permutation", **counts, log_odds_ratio=None, odds_ratio=None,
                         ci95_low=None, ci95_high=None, wald_se=None, intercept=None, sigma_project=None,
                         loglik_full=full.loglik if np.isfinite(full.loglik) else None,
                         loglik_null=null.loglik if np.isfinite(null.loglik) else None,
                         lrt_statistic=None, lrt_df=None, p_value=fb["p_value"], converged=False,
                         boundary_variance=full.boundary, optimizer_message=full.message,
                         fallback_reason=reason, fallback_details=fb)

def _fisher_combined(project: np.ndarray, present: np.ndarray, y: np.ndarray) -> tuple[float, dict]:
    stat = 0.0
    per = {}
    for g in sorted(set(project)):
        m = project == g
        a = int(np.sum((present[m] == 1) & (y[m] == 1)))
        b = int(np.sum((present[m] == 1) & (y[m] == 0)))
        c = int(np.sum((present[m] == 0) & (y[m] == 1)))
        d = int(np.sum((present[m] == 0) & (y[m] == 0)))
        p = float(stats.fisher_exact([[a, b], [c, d]], alternative="two-sided")[1])
        per[str(g)] = dict(present_pos=a, present_neg=b, control_pos=c, control_neg=d, fisher_p=p)
        stat += -2.0 * np.log(max(p, 1e-300))
    return stat, per

def stratified_exact_permutation(project: np.ndarray, present: np.ndarray, y: np.ndarray,
                                 permutations: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    observed, per = _fisher_combined(project, present, y)
    idx = {g: np.flatnonzero(project == g) for g in sorted(set(project))}
    count = 0
    for _ in range(permutations):
        perm = present.copy()
        for g, ii in idx.items():
            perm[ii] = rng.permutation(present[ii])
        s, _ = _fisher_combined(project, perm, y)
        if s >= observed - 1e-12:
            count += 1
    return dict(statistic=observed, per_project=per, permutations=permutations, seed=seed,
                p_value=(count + 1) / (permutations + 1))

def plain_logistic(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    def obj(b: np.ndarray) -> float:
        eta = X @ b
        return -float(np.sum(y * eta - np.logaddexp(0.0, eta)))
    res = optimize.minimize(obj, np.zeros(X.shape[1]), method="BFGS", options={"gtol": 1e-9})
    return res.x, -float(res.fun)
