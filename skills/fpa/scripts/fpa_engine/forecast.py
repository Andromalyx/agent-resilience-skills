"""Predictive forecasting for P&L lines (pure numpy/pandas, no heavy deps).

- Statistical: naive, moving average, seasonal naive, linear trend, Holt-Winters
  (additive, grid-searched). ``auto_forecast`` backtests each eligible method with
  rolling-origin evaluation and picks the lowest WAPE - the model choice is evidence,
  not a default.
- Prediction intervals come from backtest errors (empirical, widen with horizon).
- ``seasonality_index`` profiles month-of-year strength.
- ``DriverModel`` builds a driver-based P&L forecast (units x price, headcount x cost,
  % of revenue, fixed + growth) that plugs into ``scenarios``.

Rules the skill enforces: label forecasts, never blend them into actuals, report the
backtest error alongside the point forecast, and refuse seasonal methods with < 2 cycles.
"""

from __future__ import annotations

import itertools
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .pnl import pnl_from_lines

logger = logging.getLogger(__name__)

Method = Callable[[np.ndarray, int, int], np.ndarray]


# ------------------------------------------------------------------ period helpers


def next_periods(last: str, horizon: int) -> list[str]:
    """['2026-10', '2026-11', ...] after ``last`` (YYYY-MM)."""
    start = pd.Period(last, freq="M") + 1
    return [str(start + i) for i in range(horizon)]


# ------------------------------------------------------------------ methods
# Each method: (history, horizon, season_length) -> forecast array of len horizon.


def naive(y: np.ndarray, h: int, m: int = 12) -> np.ndarray:
    return np.repeat(y[-1], h)


def moving_average(y: np.ndarray, h: int, m: int = 12, window: int = 3) -> np.ndarray:
    return np.repeat(y[-window:].mean(), h)


def seasonal_naive(y: np.ndarray, h: int, m: int = 12) -> np.ndarray:
    if len(y) < m:
        raise ValueError("seasonal_naive needs at least one full season")
    last_season = y[-m:]
    return np.array([last_season[i % m] for i in range(h)])


def linear_trend(y: np.ndarray, h: int, m: int = 12) -> np.ndarray:
    x = np.arange(len(y))
    slope, intercept = np.polyfit(x, y, 1)
    return intercept + slope * np.arange(len(y), len(y) + h)


def _holt_winters_fit(y: np.ndarray, m: int, alpha: float, beta: float, gamma: float):
    """Additive Holt-Winters; returns (sse, level, trend, seasonals)."""
    level = y[:m].mean()
    trend = (y[m:2 * m].mean() - y[:m].mean()) / m
    season = list(y[:m] - level)
    sse = 0.0
    for t in range(m, len(y)):
        s = season[t - m]
        pred = level + trend + s
        sse += (y[t] - pred) ** 2
        new_level = alpha * (y[t] - s) + (1 - alpha) * (level + trend)
        trend = beta * (new_level - level) + (1 - beta) * trend
        season.append(gamma * (y[t] - new_level) + (1 - gamma) * s)
        level = new_level
    return sse, level, trend, season


def holt_winters(y: np.ndarray, h: int, m: int = 12) -> np.ndarray:
    """Additive Holt-Winters with a coarse grid search (requires >= 2 seasons)."""
    if len(y) < 2 * m:
        raise ValueError("holt_winters needs at least two full seasons")
    grid = (0.1, 0.3, 0.5, 0.8)
    best = min(
        (_holt_winters_fit(y, m, a, b, g) + (a, b, g)
         for a, b, g in itertools.product(grid, (0.01, 0.1, 0.3), grid)),
        key=lambda r: r[0],
    )
    _, level, trend, season = best[:4]
    n = len(y)
    return np.array([level + (i + 1) * trend + season[n - m + (i % m)] for i in range(h)])


METHODS: dict[str, tuple[Method, int]] = {
    # name: (function, minimum history length as multiple of m or absolute)
    "naive": (naive, 2),
    "moving_average_3": (moving_average, 4),
    "linear_trend": (linear_trend, 6),
    "seasonal_naive": (seasonal_naive, -1),  # -1 => needs m + backtest room
    "holt_winters": (holt_winters, -2),      # -2 => needs 2m + backtest room
}


def _min_len(name: str, m: int) -> int:
    req = METHODS[name][1]
    return req if req > 0 else (-req) * m


# ------------------------------------------------------------------ evaluation


@dataclass
class ForecastResult:
    target: str
    method: str
    periods: list[str]
    point: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    interval: float
    backtest_wape: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame({"forecast": self.point, "lower": self.lower, "upper": self.upper},
                            index=pd.Index(self.periods, name="period"))


def backtest(y: np.ndarray, method: str, horizon: int, m: int = 12,
             folds: int | None = None) -> tuple[float, np.ndarray]:
    """Rolling-origin backtest. Returns (WAPE %, error matrix [folds x horizon]).

    Default folds = up to one full season of origins, so seasonal peaks are inside the
    evaluation window (3 folds in a flat quarter would always crown ``naive``).
    """
    folds = folds or max(3, min(m, len(y) - horizon - _min_len(method, m) + 1))
    fn = METHODS[method][0]
    need = _min_len(method, m)
    errors, actual_sum, abs_err = [], 0.0, 0.0
    for f in range(folds):
        cut = len(y) - horizon - f  # origin steps back one period per fold
        if cut < need:
            continue
        train, test = y[:cut], y[cut:cut + horizon]
        pred = fn(train, len(test), m)
        e = test - pred
        errors.append(np.pad(e, (0, horizon - len(e)), constant_values=np.nan))
        abs_err += np.abs(e).sum()
        actual_sum += np.abs(test).sum()
    if not errors:
        raise ValueError(f"Not enough history to backtest {method}")
    wape = abs_err / actual_sum * 100 if actual_sum else float("nan")
    return wape, np.vstack(errors)


def auto_forecast(
    series: pd.Series,
    horizon: int = 3,
    season_length: int = 12,
    methods: list[str] | None = None,
    interval: float = 0.8,
    folds: int | None = None,
) -> ForecastResult:
    """Backtest eligible methods, pick lowest WAPE, attach empirical intervals.

    ``series``: indexed by 'YYYY-MM' (sorted), presentation-signed values.
    """
    s = series.sort_index().astype(float)
    y = s.to_numpy()
    m = season_length
    warnings: list[str] = []
    if len(y) < 6:
        warnings.append(f"Only {len(y)} periods of history - forecast is indicative only.")
    if len(y) < 2 * m:
        warnings.append(f"< {2 * m} periods: seasonal methods excluded.")

    scores: dict[str, float] = {}
    err_by_method: dict[str, np.ndarray] = {}
    for name in methods or list(METHODS):
        if len(y) < _min_len(name, m) + horizon:
            continue
        try:
            scores[name], err_by_method[name] = backtest(y, name, horizon, m, folds)
        except ValueError as exc:
            logger.debug("skip %s: %s", name, exc)
    if not scores:
        best = "naive"
        warnings.append("Too little history to backtest; using naive (last value).")
        errs = np.full((1, horizon), np.nan)
    else:
        best = min(scores, key=lambda k: (np.nan_to_num(scores[k], nan=np.inf)))
        errs = err_by_method[best]

    point = METHODS[best][0](y, horizon, m)
    # Empirical interval: quantile of |error| per step; fall back to sqrt(h) scaling.
    q = np.nanquantile(np.abs(errs), interval, axis=0) if np.isfinite(errs).any() else None
    if q is None or np.isnan(q).any():
        sigma = np.nanstd(np.diff(y)) if len(y) > 2 else abs(y[-1]) * 0.1
        q = sigma * np.sqrt(np.arange(1, horizon + 1)) * 1.28
    q = np.maximum.accumulate(q)  # intervals never narrow with horizon
    return ForecastResult(
        target=str(series.name), method=best, periods=next_periods(s.index[-1], horizon),
        point=point, lower=point - q, upper=point + q, interval=interval,
        backtest_wape={k: round(v, 2) for k, v in scores.items()}, warnings=warnings,
    )


def forecast_pnl(pnl: pd.DataFrame, horizon: int = 3, season_length: int = 12,
                 lines: list[str] | None = None) -> tuple[pd.DataFrame, dict[str, ForecastResult]]:
    """Forecast each P&L line independently, then rebuild subtotals so they tie.

    Returns (forecast P&L in ``build_pnl`` layout, per-line ForecastResult).
    """
    from .coa import PNL_LINES

    periods = [c for c in pnl.columns if c not in {"label", "kind"}]
    lines = lines or list(PNL_LINES)
    results: dict[str, ForecastResult] = {}
    table = {}
    for line in lines:
        s = pnl.loc[line, periods].astype(float)
        s.name = line
        if (s == 0).all():
            table[line] = np.zeros(horizon)
            continue
        results[line] = auto_forecast(s, horizon, season_length)
        table[line] = results[line].point
    future = next_periods(periods[-1], horizon)
    t = pd.DataFrame(table, index=future).T
    return pnl_from_lines(t), results


def seasonality_index(series: pd.Series) -> pd.DataFrame:
    """Month-of-year index (100 = average). Range > 50 pts = strongly seasonal."""
    s = series.copy()
    s.index = pd.PeriodIndex(s.index, freq="M")
    by_month = s.groupby(s.index.month).mean()
    idx = by_month / s.mean() * 100 if s.mean() else by_month * np.nan
    years = s.index.year.nunique()
    out = pd.DataFrame({"avg": by_month, "index": idx.round(1)})
    out.index.name = "month"
    out.attrs["range_pts"] = float(idx.max() - idx.min())
    out.attrs["years_of_data"] = years
    return out


# ------------------------------------------------------------------ driver-based


@dataclass
class DriverModel:
    """Driver-based monthly P&L.

    Each line spec is one of:
      ``("units_x_price", units_key, price_key)``
      ``("pct_of", base_line, pct)``           e.g. COGS 42% of revenue
      ``("headcount_x_cost", hc_key, cost_key)``
      ``("fixed", amount, monthly_growth)``
    ``drivers`` maps keys to a scalar or list (one value per period).
    """

    periods: list[str]
    lines: dict[str, tuple]
    drivers: dict[str, float | list[float]] = field(default_factory=dict)

    def _drv(self, key: str) -> np.ndarray:
        v = self.drivers[key]
        arr = np.asarray(v if isinstance(v, (list, tuple, np.ndarray)) else [v] * len(self.periods),
                         dtype=float)
        if len(arr) != len(self.periods):
            raise ValueError(f"Driver {key!r} has {len(arr)} values for {len(self.periods)} periods")
        return arr

    def lines_frame(self) -> pd.DataFrame:
        n = len(self.periods)
        values: dict[str, np.ndarray] = {}
        # Resolve non-dependent lines first, then pct_of (single pass ordering).
        for pass_pct in (False, True):
            for line, spec in self.lines.items():
                kind = spec[0]
                if (kind == "pct_of") != pass_pct:
                    continue
                if kind == "units_x_price" or kind == "headcount_x_cost":
                    values[line] = self._drv(spec[1]) * self._drv(spec[2])
                elif kind == "fixed":
                    values[line] = spec[1] * (1 + spec[2]) ** np.arange(n)
                elif kind == "pct_of":
                    if spec[1] not in values:
                        raise ValueError(f"{line}: base line {spec[1]!r} not defined")
                    values[line] = values[spec[1]] * spec[2]
                else:
                    raise ValueError(f"Unknown driver spec {kind!r} for {line}")
        return pd.DataFrame(values, index=self.periods).T

    def pnl(self) -> pd.DataFrame:
        return pnl_from_lines(self.lines_frame())
