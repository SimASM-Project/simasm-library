"""Statistical analysis: log-log regression, LOOCV, Q², MAPE, sign test."""

import math
from dataclasses import dataclass, field

import numpy as np
from scipy import stats


@dataclass
class RegressionResult:
    beta0: float
    beta1: float
    r_squared: float
    residual_std: float
    n: int
    hat_matrix_diag: np.ndarray = field(repr=False)
    ln_x: np.ndarray = field(repr=False)
    ln_y: np.ndarray = field(repr=False)


def fit_loglog(metric_values, runtimes):
    """Fit ln(runtime) = beta0 + beta1 * ln(metric) via OLS.

    Returns RegressionResult with coefficients and diagnostics.
    """
    ln_x = np.log(np.array(metric_values, dtype=float))
    ln_y = np.log(np.array(runtimes, dtype=float))
    n = len(ln_x)

    X = np.column_stack([np.ones(n), ln_x])
    XtX_inv = np.linalg.inv(X.T @ X)
    beta = XtX_inv @ X.T @ ln_y

    y_hat = X @ beta
    ss_res = np.sum((ln_y - y_hat) ** 2)
    ss_tot = np.sum((ln_y - np.mean(ln_y)) ** 2)
    r_sq = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    res_std = math.sqrt(ss_res / (n - 2)) if n > 2 else 0.0

    H_diag = np.diag(X @ XtX_inv @ X.T)

    return RegressionResult(
        beta0=beta[0], beta1=beta[1], r_squared=r_sq,
        residual_std=res_std, n=n,
        hat_matrix_diag=H_diag, ln_x=ln_x, ln_y=ln_y,
    )


@dataclass
class LOOCVResult:
    q_squared: float
    mape: float
    rmse: float
    loocv_errors: list
    loocv_predictions: list


def run_loocv(metric_values, runtimes):
    """Leave-one-out cross-validation on log-log regression.

    Returns LOOCVResult with Q², MAPE, RMSE, and per-model errors.
    """
    ln_x = np.log(np.array(metric_values, dtype=float))
    ln_y = np.log(np.array(runtimes, dtype=float))
    n = len(ln_x)

    errors = []
    predictions = []

    for i in range(n):
        mask = np.ones(n, dtype=bool)
        mask[i] = False

        x_train, y_train = ln_x[mask], ln_y[mask]
        X_train = np.column_stack([np.ones(n - 1), x_train])
        beta = np.linalg.lstsq(X_train, y_train, rcond=None)[0]

        y_pred_i = beta[0] + beta[1] * ln_x[i]
        predictions.append(math.exp(y_pred_i))
        errors.append(y_pred_i - ln_y[i])

    errors = np.array(errors)
    press = np.sum(errors ** 2)
    ss_tot = np.sum((ln_y - np.mean(ln_y)) ** 2)
    q_sq = 1 - press / ss_tot if ss_tot > 0 else 0.0

    actual = np.exp(ln_y)
    predicted = np.array(predictions)
    ape = np.abs(predicted - actual) / actual * 100
    mape = np.mean(ape)

    rmse_log = math.sqrt(np.mean(errors ** 2))

    return LOOCVResult(
        q_squared=q_sq, mape=mape, rmse=rmse_log,
        loocv_errors=errors.tolist(),
        loocv_predictions=predictions,
    )


def sign_test(smc_errors, other_errors):
    """One-sided binomial sign test: H1: P(|SMC error| < |other error|) > 0.5.

    Returns (wins, total, p_value).
    """
    smc_abs = np.abs(np.array(smc_errors))
    other_abs = np.abs(np.array(other_errors))
    wins = int(np.sum(smc_abs < other_abs))
    n = len(smc_abs)
    if hasattr(stats, "binomtest"):
        p_val = stats.binomtest(wins, n, 0.5, alternative="greater").pvalue
    else:
        p_val = stats.binom_test(wins, n, 0.5, alternative="greater")
    return wins, n, p_val


def prediction_interval(reg, x_new, alpha=0.05):
    """95% prediction interval for a new observation.

    Args:
        reg: RegressionResult from fit_loglog.
        x_new: Metric value for the new observation.
        alpha: Significance level (default 0.05 for 95% PI).

    Returns:
        (predicted, lower, upper) in original scale (seconds).
    """
    ln_x_new = math.log(x_new)
    ln_y_pred = reg.beta0 + reg.beta1 * ln_x_new

    x_vec = np.array([1.0, ln_x_new])
    X = np.column_stack([np.ones(reg.n), reg.ln_x])
    XtX_inv = np.linalg.inv(X.T @ X)

    h0 = x_vec @ XtX_inv @ x_vec
    se_pred = reg.residual_std * math.sqrt(1 + h0)

    df = reg.n - 2
    t_crit = stats.t.ppf(1 - alpha / 2, df)

    pred = math.exp(ln_y_pred)
    lower = math.exp(ln_y_pred - t_crit * se_pred)
    upper = math.exp(ln_y_pred + t_crit * se_pred)

    return pred, lower, upper, h0
