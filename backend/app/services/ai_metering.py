"""Provider-cost-backed AI metering with client-friendly credit units."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PlatformSetting


DEFAULT_AI_CREDIT_POLICY = {
    "version": "2026-08-cost-v1",
    "paise_per_credit": 25,
    "minimum_credits": 1,
    "route_max_credits": {"business": 8, "analytics": 20, "knowledge": 25, "action": 15},
    # Credits per million tokens include the configured provider-cost buffer.
    "models": {
        "gpt-5.4-mini": {"input": 255, "cached_input": 26, "output": 1530},
        "text-embedding-3-small": {"input": 7, "cached_input": 7, "output": 0},
    },
    "fallback": {"input": 255, "cached_input": 26, "output": 1530},
}


@dataclass(frozen=True)
class AICharge:
    credits: int
    provider_cost_paise: int
    rate_version: str


def credit_policy(db: Session) -> dict:
    row = db.execute(select(PlatformSetting).where(PlatformSetting.key == "ai_credit_policy")).scalar_one_or_none()
    configured = row.value if row and isinstance(row.value, dict) else {}
    return {
        **DEFAULT_AI_CREDIT_POLICY,
        **configured,
        "route_max_credits": {
            **DEFAULT_AI_CREDIT_POLICY["route_max_credits"],
            **(configured.get("route_max_credits") or {}),
        },
        "models": {**DEFAULT_AI_CREDIT_POLICY["models"], **(configured.get("models") or {})},
    }


def _model_rate(policy: dict, model: str) -> dict:
    rates = policy["models"]
    if model in rates:
        return rates[model]
    match = next((rate for name, rate in rates.items() if model.startswith(f"{name}-")), None)
    return match or policy["fallback"]


def calculate_charge(db: Session, model: str, usage: dict) -> AICharge:
    provider_requests = int(usage.get("provider_requests", 0))
    input_tokens = max(int(usage.get("input_tokens", 0)), 0)
    cached_tokens = min(max(int(usage.get("cached_input_tokens", 0)), 0), input_tokens)
    output_tokens = max(int(usage.get("output_tokens", 0)), 0)
    embedding_tokens = max(int(usage.get("embedding_tokens", 0)), 0)
    if provider_requests <= 0 and not any((input_tokens, output_tokens, embedding_tokens)):
        return AICharge(credits=0, provider_cost_paise=0, rate_version="no-provider")

    policy = credit_policy(db)
    rate = _model_rate(policy, model)
    embedding_rate = _model_rate(policy, "text-embedding-3-small")
    million = Decimal(1_000_000)
    raw_credits = (
        Decimal(input_tokens - cached_tokens) * Decimal(rate["input"])
        + Decimal(cached_tokens) * Decimal(rate.get("cached_input", rate["input"]))
        + Decimal(output_tokens) * Decimal(rate["output"])
        + Decimal(embedding_tokens) * Decimal(embedding_rate["input"])
    ) / million
    credits = max(int(policy.get("minimum_credits", 1)), int(raw_credits.to_integral_value(rounding=ROUND_CEILING)))
    provider_cost = int((raw_credits * Decimal(policy.get("paise_per_credit", 25))).to_integral_value(rounding=ROUND_CEILING))
    return AICharge(credits=credits, provider_cost_paise=provider_cost, rate_version=str(policy["version"]))


def route_credit_limit(db: Session, route: str) -> int:
    return max(1, int(credit_policy(db)["route_max_credits"].get(route, 8)))
