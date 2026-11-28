from decimal import Decimal, InvalidOperation


TOTAL = Decimal("100")
ZERO = Decimal("0")


class WeightDistributionError(ValueError):
    pass


def percent(value) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise WeightDistributionError("Некорректное значение веса") from exc

    if not result.is_finite():
        raise WeightDistributionError("Вес должен быть конечным числом")

    if result != result.to_integral_value():
        raise WeightDistributionError(
            "Вес должен быть целым числом процентов"
        )

    return result.quantize(Decimal("1"))


def distribute(offers: list) -> None:
    for offer in offers:
        if offer.is_deleted:
            offer.share = ZERO

    active = [offer for offer in offers if not offer.is_deleted]
    fixed = [offer for offer in active if offer.is_fixed]
    flexible = [offer for offer in active if not offer.is_fixed]

    fixed_total = sum((percent(x.share) for x in fixed), ZERO)

    if fixed_total > TOTAL:
        raise WeightDistributionError(
            "Сумма фиксированных весов превышает 100%"
        )

    if fixed_total < ZERO:
        raise WeightDistributionError(
            "Фиксированный вес не может быть отрицательным"
        )

    remaining = TOTAL - fixed_total

    if not flexible:
        if remaining != ZERO:
            raise WeightDistributionError(
                "Невозможно распределить остаток: нет незакреплённых офферов"
            )
        return

    base, remainder = divmod(int(remaining), len(flexible))

    for index, offer in enumerate(flexible):
        offer.share = Decimal(base + (1 if index < remainder else 0))


def set_offer_weight(offers: list, target, new_share) -> None:
    value = percent(new_share)

    if value < ZERO or value > TOTAL:
        raise WeightDistributionError(
            "Вес должен находиться в диапазоне 0–100%"
        )

    if target.is_deleted:
        raise WeightDistributionError(
            "Нельзя менять вес удалённого оффера"
        )

    if target.is_fixed:
        raise WeightDistributionError(
            "Сначала снимите фиксацию веса"
        )

    active = [x for x in offers if not x.is_deleted]

    fixed_total = sum(
        (percent(x.share) for x in active if x.is_fixed),
        ZERO,
    )

    others = [
        x for x in active
        if x is not target and not x.is_fixed
    ]

    remaining = TOTAL - fixed_total - value

    if remaining < ZERO:
        raise WeightDistributionError(
            "Фиксированные веса и выбранный вес превышают 100%"
        )

    if not others and remaining != ZERO:
        raise WeightDistributionError(
            "Для распределения остатка нет других офферов"
        )

    target.share = value

    if others:
        base, remainder = divmod(int(remaining), len(others))

        for index, offer in enumerate(others):
            offer.share = Decimal(base + (1 if index < remainder else 0))


def validate_total(offers: list) -> None:
    active = [x for x in offers if not x.is_deleted]

    total = sum((percent(x.share) for x in active), ZERO)

    if total != TOTAL:
        raise WeightDistributionError(
            f"Сумма весов должна быть 100%, сейчас {total}%"
        )

    for offer in offers:
        value = percent(offer.share)

        if value < ZERO or value > TOTAL:
            raise WeightDistributionError(
                "Вес оффера должен находиться в диапазоне 0–100%"
            )

        if offer.is_deleted and value != ZERO:
            raise WeightDistributionError(
                "Удалённый оффер должен иметь вес 0%"
            )
