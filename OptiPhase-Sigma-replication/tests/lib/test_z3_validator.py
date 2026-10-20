"""Behavioural tests for the Z3 refinement checker, using hand-written blocks whose answers are known."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from lib.z3_validator import STATUS_REFINES, STATUS_VIOLATED, blocks_of_function, check_refinement  # noqa: E402

TIMEOUT_MS = 5000


def first_block(body):
    listing = f"define i32 @f(i32 %x, i32 %y) {{\nentry:\n{body}\n}}\n"
    return blocks_of_function(listing, "f")[0]


def statuses(source_body, target_body):
    statuses_by_name, _ = check_refinement(first_block(source_body), first_block(target_body), TIMEOUT_MS)
    return statuses_by_name


class RefinementTests(unittest.TestCase):
    def test_self_addition_refines_shift_by_one(self):
        result = statuses("  %r = add i32 %x, %x\n  ret i32 %r", "  %r = shl i32 %x, 1\n  ret i32 %r")
        self.assertEqual(result, {"%r": STATUS_REFINES})

    def test_increment_does_not_refine_identity(self):
        result = statuses("  %r = add i32 %x, 1\n  ret i32 %r", "  %r = add i32 %x, 0\n  ret i32 %r")
        self.assertEqual(result, {"%r": STATUS_VIOLATED})

    def test_no_wrap_source_is_refined_by_plain_target(self):
        result = statuses("  %r = add nsw i32 %x, %y\n  ret i32 %r", "  %r = add i32 %x, %y\n  ret i32 %r")
        self.assertEqual(result, {"%r": STATUS_REFINES})

    def test_plain_source_is_not_refined_by_no_wrap_target_on_overflow(self):
        result = statuses("  %r = add i32 %x, %y\n  ret i32 %r", "  %r = add nsw i32 %x, %y\n  ret i32 %r")
        self.assertEqual(result, {"%r": STATUS_VIOLATED})

    def test_select_with_identical_arms_refines_the_arm(self):
        result = statuses(
            "  %c = icmp slt i32 %x, %y\n  %r = select i1 %c, i32 %x, i32 %x\n  ret i32 %r",
            "  %c = icmp slt i32 %x, %y\n  %r = add i32 %x, 0\n  ret i32 %r",
        )
        self.assertEqual(result["%r"], STATUS_REFINES)

    def test_shift_past_bit_width_is_poison_and_violates_a_defined_source(self):
        result = statuses("  %r = add i32 %x, 0\n  ret i32 %r", "  %r = shl i32 %x, 32\n  ret i32 %r")
        self.assertEqual(result, {"%r": STATUS_VIOLATED})

    def test_differing_live_in_sets_are_not_comparable(self):
        from lib.z3_validator import NotEncodable

        with self.assertRaises(NotEncodable):
            statuses("  %r = add i32 %x, %y\n  ret i32 %r", "  %r = add i32 %x, %x\n  ret i32 %r")

    def test_memory_instruction_makes_block_non_encodable(self):
        from lib.z3_validator import NotEncodable

        block = first_block("  %p = load i32, ptr %x\n  ret i32 %p")
        with self.assertRaises(NotEncodable):
            check_refinement(block, block, TIMEOUT_MS)

    def test_multiplication_overflow_at_three_bits_violates_the_plain_source(self):
        result = statuses("  %r = mul i3 %x, %y\n  ret i3 %r", "  %r = mul nsw i3 %x, %y\n  ret i3 %r")
        self.assertEqual(result, {"%r": STATUS_VIOLATED})

    def test_shifted_out_bit_violates_a_source_under_nuw_shift(self):
        result = statuses("  %r = shl i32 %x, 1\n  ret i32 %r", "  %r = shl nuw i32 %x, 1\n  ret i32 %r")
        self.assertEqual(result, {"%r": STATUS_VIOLATED})

    def test_flag_outside_the_model_makes_block_non_encodable(self):
        from lib.z3_validator import NotEncodable

        with self.assertRaises(NotEncodable):
            statuses("  %r = and i32 %x, %y\n  ret i32 %r", "  %r = and nuw i32 %x, %y\n  ret i32 %r")


if __name__ == "__main__":
    unittest.main()
