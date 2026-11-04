"""One-year illustrative losses on observed balances and assumed PD/LGD."""
from collections.abc import Mapping
import math
from numbers import Real


def _number(value, name, upper=None):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite number")
    try:
        value = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if value < 0 or (upper is not None and value > upper):
        limit = f"between 0 and {upper}" if upper is not None else ">= 0"
        raise ValueError(f"{name} must be {limit}")
    return value


def validate_exposures(records):
    """Return normalized copies with unique, nonempty sector identifiers."""
    if isinstance(records, (str, bytes, Mapping)):
        raise ValueError("exposures must be an iterable of records")
    try:
        records = list(records)
    except TypeError as exc:
        raise ValueError("exposures must be an iterable of records") from exc
    if not records:
        raise ValueError("at least one exposure record is required")
    result, seen = [], set()
    for i, row in enumerate(records):
        if not isinstance(row, Mapping):
            raise ValueError(f"exposure {i} must be a record")
        sector = row.get("sector")
        if not isinstance(sector, str) or not sector or sector.strip() != sector:
            raise ValueError(f"exposure {i} requires a nonempty sector identifier")
        if sector in seen:
            raise ValueError(f"duplicate exposure sector: {sector}")
        seen.add(sector)
        result.append({"sector": sector,
                       "exposure_eur": _number(row.get("exposure_eur"), f"{sector}.exposure_eur")})
    try:
        total = math.fsum(row["exposure_eur"] for row in result)
    except OverflowError as exc:
        raise ValueError("total exposure exceeds finite numeric range") from exc
    if not math.isfinite(total):
        raise ValueError("total exposure exceeds finite numeric range")
    return result


def validate_scenarios(config):
    """Validate baseline probabilities before applying any stress caps."""
    if not isinstance(config, Mapping):
        raise ValueError("scenario configuration must be a mapping")
    if config.get("currency", "EUR") != "EUR":
        raise ValueError("exposure_eur requires EUR scenario currency")
    if _number(config.get("horizon_years"), "horizon_years") != 1:
        raise ValueError("this illustration supports a one-year horizon only")
    sectors = config.get("sectors")
    if not isinstance(sectors, Mapping) or not sectors:
        raise ValueError("configuration requires a nonempty sectors mapping")
    result = {}
    for sector, assumptions in sectors.items():
        if not isinstance(sector, str) or not sector or sector.strip() != sector:
            raise ValueError("configuration sector identifiers must be nonempty strings")
        if not isinstance(assumptions, Mapping):
            raise ValueError(f"assumptions for {sector} must be a mapping")
        result[sector] = {
            key: _number(assumptions.get(key), f"{sector}.{key}", upper)
            for key, upper in [
                ("baseline_pd", 1), ("baseline_lgd", 1),
                ("adverse_pd_multiplier", None), ("adverse_lgd_uplift", 1),
            ]
        }
    return {"horizon_years": 1, "sectors": result}


def _inputs(records, config):
    records, config = validate_exposures(records), validate_scenarios(config)
    supplied, configured = {r["sector"] for r in records}, set(config["sectors"])
    if supplied != configured:
        raise ValueError(
            f"exposure/configuration sector mismatch; unknown={sorted(supplied-configured)}, "
            f"missing={sorted(configured-supplied)}"
        )
    return records, config


def _stress(pd, lgd, multiplier, uplift):
    raw_pd, raw_lgd = pd * multiplier, lgd + uplift
    return min(raw_pd, 1.0), min(raw_lgd, 1.0), raw_pd > 1.0, raw_lgd > 1.0


def calculate_losses(records, config):
    """Rates are fractions; zero exposure gives zero rate. Caps count sectors."""
    records, config = _inputs(records, config)
    segments = []
    for row in records:
        sector, exposure = row["sector"], row["exposure_eur"]
        a = config["sectors"][sector]
        pd, lgd = a["baseline_pd"], a["baseline_lgd"]
        apd, algd, pd_cap, lgd_cap = _stress(
            pd, lgd, a["adverse_pd_multiplier"], a["adverse_lgd_uplift"])
        baseline, adverse = exposure * (pd * lgd), exposure * (apd * algd)
        segments.append({
            "sector": sector, "exposure_eur": exposure,
            "baseline_pd": pd, "baseline_lgd": lgd,
            "baseline_loss_eur": baseline,
            "baseline_loss_rate": baseline / exposure if exposure else 0.0,
            "adverse_pd": apd, "adverse_lgd": algd,
            "adverse_loss_eur": adverse,
            "adverse_loss_rate": adverse / exposure if exposure else 0.0,
            "increase_eur": adverse - baseline,
            "pd_capped": pd_cap, "lgd_capped": lgd_cap,
        })
    total = {key: math.fsum(r[key] for r in segments)
             for key in ("exposure_eur", "baseline_loss_eur", "adverse_loss_eur", "increase_eur")}
    exposure = total["exposure_eur"]
    total.update({
        "baseline_loss_rate": total["baseline_loss_eur"] / exposure if exposure else 0.0,
        "adverse_loss_rate": total["adverse_loss_eur"] / exposure if exposure else 0.0,
        "pd_cap_count": sum(r["pd_capped"] for r in segments),
        "lgd_cap_count": sum(r["lgd_capped"] for r in segments),
    })
    return {"segments": segments, "totals": total}


def sensitivity(records, config, pd_multipliers=None, lgd_uplifts=None):
    """Uniform baseline stress grid, separate from the sector-specific scenario."""
    records, config = _inputs(records, config)
    try:
        multipliers = [1, 1.5, 2, 2.5, 3, 3.5, 4] if pd_multipliers is None else list(pd_multipliers)
        uplifts = [0, .05, .1, .15, .2] if lgd_uplifts is None else list(lgd_uplifts)
    except TypeError as exc:
        raise ValueError("sensitivity axes must be iterable") from exc
    multipliers = [_number(x, "sensitivity PD multiplier") for x in multipliers]
    uplifts = [_number(x, "sensitivity LGD uplift", 1) for x in uplifts]
    if not multipliers or not uplifts:
        raise ValueError("sensitivity axes must be nonempty")
    if len(set(multipliers)) != len(multipliers) or len(set(uplifts)) != len(uplifts):
        raise ValueError("sensitivity axes must not contain duplicates")
    exposure = math.fsum(r["exposure_eur"] for r in records)
    grid = []
    for multiplier in multipliers:
        for uplift in uplifts:
            losses, pd_caps, lgd_caps = [], 0, 0
            for row in records:
                a = config["sectors"][row["sector"]]
                pd, lgd, pd_cap, lgd_cap = _stress(a["baseline_pd"], a["baseline_lgd"], multiplier, uplift)
                losses.append(row["exposure_eur"] * (pd * lgd))
                pd_caps += pd_cap
                lgd_caps += lgd_cap
            loss = math.fsum(losses)
            grid.append({
                "pd_multiplier": multiplier, "lgd_uplift": uplift,
                "loss_eur": loss, "loss_rate": loss / exposure if exposure else 0.0,
                "pd_cap_count": pd_caps, "lgd_cap_count": lgd_caps,
            })
    return grid
