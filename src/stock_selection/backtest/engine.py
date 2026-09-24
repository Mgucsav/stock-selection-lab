"""Yürüyen (walk-forward) backtest motoru.

Her yeniden dengeleme tarihinde model **yalnızca o tarihe kadarki veriyle**
yeniden çalıştırılır: kriterler → üyelikler → fpfs/CCE10 → portföy ağırlıkları.
İşlemler bir sonraki işlem gününün açılış fiyatından, tam lot ve komisyonla
yapılır. Böylece "bugünün kazananlarını geçmişe uygulama" yanlılığı olmaz.

```text
karar günü t   : sıralama ve hedef ağırlıklar (veri ≤ t)
işlem günü t+1 : açılış fiyatından fark kadar alım/satım, komisyon düşülür
t+1 … t'       : günlük değerleme (kapanış), temettüler nakde eklenir
```

Modellenen: tam lot, nakit bakiyesi, çift yönlü komisyon (varsayılan 10 bp),
brüt nakit temettü, karşılaştırma için BIST 100 al-tut.

**Modellenmeyen** (sonuçlar bu ölçüde iyimserdir): stopaj, kayma (slippage),
emir derinliği/piyasa etkisi, borsa tatilleri dışındaki işlem kesintileri ve
en önemlisi **survivorship** — evren bugünkü BIST 100 listesidir, dönem içinde
endeksten çıkmış şirketler yoktur.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import math
from typing import Any

import numpy as np
import pandas as pd

from src.day01_baseline import TRADING_DAYS, max_drawdown

from ..features.panel import CriteriaPanel
from ..fuzzy.fpfs import evaluate_fpfs
from ..fuzzy.membership import build_memberships
from ..fuzzy.profiles import InvestorProfile
from ..portfolio.builder import build_candidate

REBALANCE_RULES = {"monthly": "MS", "quarterly": "QS", "yearly": "YS"}
DEFAULT_COST_BPS = 10.0  # tek yön; BIST'te aracı kurum komisyonu + BSMV mertebesi


@dataclass
class BacktestConfig:
    """Tek bir profil için yürüyen test parametreleri."""

    start: date
    end: date
    rebalance: str = "monthly"
    initial_capital: float = 1_000_000.0
    lookback_days: int = 1095
    min_observations: int = 120
    cost_bps: float = DEFAULT_COST_BPS
    benchmark_symbol: str = "XU100.IS"
    constant_policy: str = "neutral"


@dataclass
class BacktestResult:
    profile_id: str
    config: dict[str, Any]
    equity: pd.DataFrame           # date, value, cash, invested, benchmark_value, portfolio_norm, benchmark_norm
    metrics: dict[str, Any]
    rebalances: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def rebalance_dates(panel: CriteriaPanel, config: BacktestConfig) -> list[pd.Timestamp]:
    """Dönem başlarına denk gelen ilk işlem günleri (karar günleri)."""
    rule = REBALANCE_RULES.get(config.rebalance)
    if rule is None:
        raise ValueError(f"Bilinmeyen yeniden dengeleme sıklığı: {config.rebalance}")
    days = panel.trading_days(config.start, config.end)
    if not days:
        return []
    index = pd.DatetimeIndex(days)
    periods = pd.Series(index, index=index).groupby(index.to_period(rule.replace("S", "")[0] if rule != "MS" else "M")).first()
    return [pd.Timestamp(d) for d in periods.tolist()]


def _wide(clean: pd.DataFrame, column: str) -> pd.DataFrame:
    frame = clean.loc[:, ["date", "symbol", column]].copy()
    frame["date"] = pd.to_datetime(frame["date"])
    wide = frame.pivot(index="date", columns="symbol", values=column).sort_index()
    wide.columns.name = None
    return wide


def _first_valid_after(prices: pd.DataFrame, symbol: str, after: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    """Karar gününden **sonraki** ilk geçerli fiyat (look-ahead engeli)."""
    if symbol not in prices.columns:
        return None
    series = prices[symbol]
    series = series.loc[series.index > after].dropna()
    series = series.loc[series > 0]
    if series.empty:
        return None
    return series.index[0], float(series.iloc[0])


def fpfs_strategy(profile: InvestorProfile, constant_policy: str = "neutral"):
    """Karar tarihindeki kriterlerden fpfs/CCE10 ile hedef ağırlık üretir (canlı akışın aynısı)."""

    def decide(criteria, history: pd.DataFrame) -> dict[str, float] | None:
        memberships = build_memberships(criteria.table, constant_policy=constant_policy)
        fpfs = evaluate_fpfs(memberships.frame, profile.weights)
        try:
            candidate = build_candidate(profile, fpfs.scores, criteria.table, history, with_stats=False)
        except ValueError:
            return None
        return dict(candidate.weights)

    return decide


def equal_weight_strategy(size: int | None = None):
    """Kontrol senaryosu: seçim yapmadan (ya da ilk N sembolü alfabetik alarak) eşit ağırlık.

    fpfs sonuçlarının anlamlı olup olmadığını ölçmek için gereklidir: endeks sermaye
    ağırlıklıyken eşit ağırlıklı her portföy sistematik olarak farklı davranır.
    """

    def decide(criteria, history: pd.DataFrame) -> dict[str, float] | None:
        symbols = [s for s in criteria.table.index if s in history.columns]
        if size is not None:
            symbols = symbols[:size]
        if not symbols:
            return None
        weight = 1.0 / len(symbols)
        return {s: weight for s in symbols}

    return decide


def run_backtest(
    clean: pd.DataFrame,
    benchmark: pd.DataFrame | None,
    profile: InvestorProfile,
    config: BacktestConfig,
    panel: CriteriaPanel | None = None,
    free_float_market_cap: dict[str, float] | None = None,
    strategy=None,
    label: str | None = None,
) -> BacktestResult:
    """Stratejiyi dönem boyunca yürütür ve BIST 100 ile karşılaştırır.

    ``strategy`` verilmezse profilin fpfs stratejisi kullanılır; kontrol senaryoları
    (ör. ``equal_weight_strategy``) aynı işlem/maliyet/lot mantığını paylaşır.
    """
    warnings: list[str] = [
        "Evren bugünkü BIST 100 listesidir; dönem içinde endeksten çıkan şirketler yoktur (survivorship).",
        "Stopaj, kayma ve piyasa etkisi modellenmez; komisyon çift yönlü uygulanır.",
    ]
    if clean is None or clean.empty:
        raise ValueError("Backtest için temiz veri gerekli.")
    panel = panel or CriteriaPanel(clean)
    decide = strategy or fpfs_strategy(profile, config.constant_policy)
    schedule = rebalance_dates(panel, config)
    if len(schedule) < 2:
        raise ValueError("Yeniden dengeleme için yeterli işlem günü yok.")

    opens, closes, dividends, adj = (_wide(clean, c) for c in ("open", "close", "dividends", "adj_close"))
    calendar = [d for d in panel.trading_days(config.start, config.end)]
    cost_rate = config.cost_bps / 10_000.0

    cash = float(config.initial_capital)
    positions: dict[str, int] = {}
    rebalances: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    pending: dict[pd.Timestamp, dict[str, float]] = {}  # işlem günü → hedef ağırlıklar
    total_cost = 0.0
    total_dividends = 0.0

    # --- karar günlerinde hedef ağırlıkları üret (yalnızca ≤ t verisiyle)
    for decision in schedule:
        criteria = panel.criteria_at(
            decision, lookback_days=config.lookback_days, min_observations=config.min_observations,
            free_float_market_cap=free_float_market_cap,
        )
        if criteria.table.empty:
            continue
        history = adj.loc[adj.index <= decision]
        targets = decide(criteria, history)
        if not targets:
            continue
        trade_day: pd.Timestamp | None = None
        for symbol in targets:
            found = _first_valid_after(opens, symbol, decision)
            if found and (trade_day is None or found[0] < trade_day):
                trade_day = found[0]
        if trade_day is None:
            continue
        pending[trade_day] = dict(targets)

    if not pending:
        raise ValueError("Hiçbir karar gününde uygulanabilir portföy üretilemedi.")

    first_trade_day = min(pending)
    benchmark_units = 0.0
    bench_series = None
    if benchmark is not None and not benchmark.empty:
        bench = benchmark.copy()
        bench["date"] = pd.to_datetime(bench["date"])
        bench_series = bench.set_index("date")["close"].sort_index()

    # --- günlük döngü
    for day in calendar:
        if day < first_trade_day:
            continue
        # temettüler (elde tutulan paylar için) nakde eklenir
        if day in dividends.index:
            row = dividends.loc[day]
            for symbol, quantity in positions.items():
                amount = row.get(symbol, np.nan)
                if quantity and isinstance(amount, (int, float)) and np.isfinite(amount) and amount > 0:
                    credited = quantity * float(amount)
                    cash += credited
                    total_dividends += credited

        # yeniden dengeleme (fark kadar işlem)
        if day in pending:
            targets = pending.pop(day)
            open_row = opens.loc[day] if day in opens.index else pd.Series(dtype=float)
            close_row = closes.loc[day] if day in closes.index else pd.Series(dtype=float)

            def price_of(symbol: str) -> float | None:
                for source in (open_row, close_row):
                    value = source.get(symbol, np.nan)
                    if isinstance(value, (int, float)) and np.isfinite(value) and value > 0:
                        return float(value)
                return None

            portfolio_value = cash + sum(
                quantity * (price_of(symbol) or 0.0) for symbol, quantity in positions.items()
            )
            # Komisyon payı ayrılır: en kötü durumda tüm portföy bir kez dönerse maliyet
            # (satış + alım) × oran olur; bu yüzden 2×oran kadar kesinti güvenli üst sınırdır.
            investable = portfolio_value * (1.0 - 2.0 * cost_rate)
            desired: dict[str, int] = {}
            for symbol, weight in targets.items():
                price = price_of(symbol)
                if price:
                    desired[symbol] = int(math.floor(investable * weight / price))
            traded_value = 0.0
            for symbol in set(positions) | set(desired):
                price = price_of(symbol)
                if price is None:
                    continue
                delta = desired.get(symbol, 0) - positions.get(symbol, 0)
                if delta == 0:
                    continue
                amount = abs(delta) * price
                cost = amount * cost_rate
                cash += -delta * price - cost
                traded_value += amount
                total_cost += cost
                new_quantity = positions.get(symbol, 0) + delta
                if new_quantity > 0:
                    positions[symbol] = new_quantity
                else:
                    positions.pop(symbol, None)
            if cash < -1e-6:  # tam lot yuvarlaması nedeniyle oluşamaz; güvenlik kontrolü
                raise ValueError(f"{day.date()}: nakit negatife düştü ({cash:.2f}).")
            rebalances.append({
                "date": day.date().isoformat(),
                "symbols": sorted(desired),
                "turnover": round(traded_value / portfolio_value, 6) if portfolio_value else None,
                "cost": round(traded_value * cost_rate, 2),
                "value": round(portfolio_value, 2),
            })
            if bench_series is not None and benchmark_units == 0.0:
                level = bench_series.loc[bench_series.index <= day]
                if not level.empty and float(level.iloc[-1]) > 0:
                    benchmark_units = config.initial_capital / float(level.iloc[-1])

        # günlük değerleme
        close_row = closes.loc[day] if day in closes.index else pd.Series(dtype=float)
        invested = 0.0
        for symbol, quantity in positions.items():
            price = close_row.get(symbol, np.nan)
            if not (isinstance(price, (int, float)) and np.isfinite(price) and price > 0):
                history = closes[symbol].loc[closes.index <= day].dropna()
                price = float(history.iloc[-1]) if not history.empty else 0.0
            invested += quantity * float(price)
        benchmark_value = np.nan
        if bench_series is not None and benchmark_units:
            level = bench_series.loc[bench_series.index <= day]
            if not level.empty:
                benchmark_value = benchmark_units * float(level.iloc[-1])
        records.append({"date": day, "value": cash + invested, "cash": cash, "invested": invested,
                        "benchmark_value": benchmark_value})

    equity = pd.DataFrame.from_records(records).set_index("date").sort_index()
    if equity.empty:
        raise ValueError("Backtest değer serisi boş.")
    equity["portfolio_norm"] = 100.0 * equity["value"] / equity["value"].iloc[0]
    if equity["benchmark_value"].notna().any():
        base = equity["benchmark_value"].dropna().iloc[0]
        equity["benchmark_norm"] = 100.0 * equity["benchmark_value"] / base
    else:
        equity["benchmark_norm"] = np.nan
        warnings.append("BIST 100 serisi bulunamadı; karşılaştırma yapılamadı.")

    metrics = _metrics(equity, config, rebalances, total_cost, total_dividends)
    equity = equity.reset_index()
    return BacktestResult(
        profile_id=label or profile.id,
        config={
            "start": config.start.isoformat(), "end": config.end.isoformat(), "rebalance": config.rebalance,
            "initial_capital": config.initial_capital, "lookback_days": config.lookback_days,
            "cost_bps": config.cost_bps, "benchmark_symbol": config.benchmark_symbol,
            "profile_weights": dict(profile.weights), "portfolio_size": profile.portfolio_size,
            "max_weight": profile.max_weight, "weighting_scheme": profile.weighting_scheme,
        },
        equity=equity,
        metrics=metrics,
        rebalances=rebalances,
        warnings=warnings,
    )


def _metrics(equity: pd.DataFrame, config: BacktestConfig, rebalances: list[dict[str, Any]],
             total_cost: float, total_dividends: float) -> dict[str, Any]:
    values = equity["value"]
    returns = values.pct_change().dropna()
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1e-9)
    total_return = float(values.iloc[-1] / values.iloc[0] - 1.0)
    bench = equity["benchmark_value"].dropna()
    benchmark_return = float(bench.iloc[-1] / bench.iloc[0] - 1.0) if len(bench) > 1 else None

    metrics: dict[str, Any] = {
        "start": equity.index[0].date().isoformat(),
        "end": equity.index[-1].date().isoformat(),
        "trading_days": int(len(equity)),
        "initial_capital": float(values.iloc[0]),
        "final_value": float(values.iloc[-1]),
        "total_return": total_return,
        "cagr": float((1 + total_return) ** (1 / years) - 1) if total_return > -1 else None,
        "volatility": float(returns.std(ddof=1) * np.sqrt(TRADING_DAYS)) if len(returns) > 2 else None,
        "max_drawdown": float(max_drawdown(values)),
        "benchmark_return": benchmark_return,
        "excess_return": (total_return - benchmark_return) if benchmark_return is not None else None,
        "rebalances": len(rebalances),
        "avg_turnover": float(np.mean([r["turnover"] for r in rebalances if r["turnover"] is not None]))
        if rebalances else None,
        "total_cost": round(total_cost, 2),
        "cost_drag": round(total_cost / float(values.iloc[0]), 6),
        "total_dividends": round(total_dividends, 2),
    }
    if benchmark_return is not None and len(bench) > 2:
        bench_returns = bench.pct_change().dropna()
        aligned = pd.concat([returns.rename("p"), bench_returns.rename("b")], axis=1).dropna()
        if len(aligned) > 2:
            active = aligned["p"] - aligned["b"]
            tracking_error = float(active.std(ddof=1) * np.sqrt(TRADING_DAYS))
            metrics["tracking_error"] = tracking_error
            metrics["information_ratio"] = (
                float(active.mean() * TRADING_DAYS / tracking_error) if tracking_error > 0 else None
            )
            monthly = aligned.resample("ME").apply(lambda x: (1 + x).prod() - 1)
            metrics["monthly_hit_rate"] = float((monthly["p"] > monthly["b"]).mean()) if len(monthly) else None
            metrics["months"] = int(len(monthly))
    return metrics
