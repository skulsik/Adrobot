import unittest
from dataclasses import dataclass
from decimal import Decimal

from app.services.offer_weights import (
    distribute,
    set_offer_weight,
    validate_total,
    WeightDistributionError,
)


@dataclass
class Offer:
    share: Decimal
    is_fixed: bool = False
    is_deleted: bool = False


class OfferWeightTests(unittest.TestCase):

    def test_three_offers(self):
        offers = [Offer(Decimal("0")) for _ in range(3)]
        distribute(offers)
        self.assertEqual(
            [x.share for x in offers],
            [Decimal("34"), Decimal("33"), Decimal("33")],
        )
        validate_total(offers)

    def test_six_offers(self):
        offers = [Offer(Decimal("0")) for _ in range(6)]
        distribute(offers)
        self.assertEqual(
            [x.share for x in offers],
            [
                Decimal("17"), Decimal("17"), Decimal("17"),
                Decimal("17"), Decimal("16"), Decimal("16"),
            ],
        )
        validate_total(offers)

    def test_fixed_weight(self):
        offers = [
            Offer(Decimal("25"), is_fixed=True),
            Offer(Decimal("0")),
            Offer(Decimal("0")),
        ]
        distribute(offers)
        self.assertEqual(
            [x.share for x in offers],
            [Decimal("25"), Decimal("38"), Decimal("37")],
        )
        validate_total(offers)

    def test_deleted_offer(self):
        offers = [
            Offer(Decimal("15"), is_deleted=True),
            Offer(Decimal("0")),
            Offer(Decimal("0")),
        ]
        distribute(offers)
        self.assertEqual(
            [x.share for x in offers],
            [Decimal("0"), Decimal("50"), Decimal("50")],
        )
        validate_total(offers)

    def test_fixed_over_100(self):
        offers = [
            Offer(Decimal("60"), is_fixed=True),
            Offer(Decimal("50"), is_fixed=True),
        ]
        with self.assertRaises(WeightDistributionError):
            distribute(offers)

    def test_all_fixed_not_100(self):
        offers = [
            Offer(Decimal("40"), is_fixed=True),
            Offer(Decimal("40"), is_fixed=True),
        ]
        with self.assertRaises(WeightDistributionError):
            distribute(offers)

    def test_manual_weight(self):
        offers = [Offer(Decimal("0")) for _ in range(3)]
        set_offer_weight(offers, offers[0], Decimal("40"))
        self.assertEqual(
            [x.share for x in offers],
            [Decimal("40"), Decimal("30"), Decimal("30")],
        )
        validate_total(offers)

    def test_manual_weight_with_fixed(self):
        offers = [
            Offer(Decimal("20"), is_fixed=True),
            Offer(Decimal("0")),
            Offer(Decimal("0")),
        ]
        set_offer_weight(offers, offers[1], Decimal("50"))
        self.assertEqual(
            [x.share for x in offers],
            [Decimal("20"), Decimal("50"), Decimal("30")],
        )
        validate_total(offers)

    def test_fractional_weight_rejected(self):
        offers = [Offer(Decimal("0")), Offer(Decimal("0"))]
        with self.assertRaises(WeightDistributionError):
            set_offer_weight(offers, offers[0], Decimal("33.5"))

    def test_deleted_share_zeroed(self):
        offers = [
            Offer(Decimal("25"), is_deleted=True),
            Offer(Decimal("75")),
        ]
        distribute(offers)
        self.assertEqual(offers[0].share, Decimal("0"))
        self.assertEqual(offers[1].share, Decimal("100"))
        validate_total(offers)


if __name__ == "__main__":
    unittest.main()
