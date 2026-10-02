import unittest

from imageaudit.analyzers.annotation import YoloAnnotationAnalyzer
from imageaudit.core.config import AnnotationConfig
from imageaudit.core.models import ISSUE_LEVELS


def parse(text: str, classes: int | None = 3):
    return YoloAnnotationAnalyzer(AnnotationConfig(), classes).parse_text(text, "labels/x.txt")


def codes(parsed) -> list[str]:
    return [i.code for i in parsed.issues]


class YoloParserTests(unittest.TestCase):
    def test_valid_lines_produce_boxes_and_no_issues(self):
        p = parse("0 0.5 0.5 0.2 0.3\n2 0.1 0.9 0.05 0.05\n")
        self.assertEqual(p.status, "ok")
        self.assertEqual(len(p.boxes), 2)
        self.assertEqual((p.total_lines, p.invalid_lines), (2, 0))
        self.assertEqual(codes(p), [])

    def test_empty_file_is_background_not_error(self):
        p = parse("\n  \n")
        self.assertEqual(p.status, "empty")
        self.assertEqual(codes(p), ["empty_label_file"])
        self.assertEqual(p.invalid_lines, 0)

    def test_malformed_lines_are_reported_with_line_numbers(self):
        p = parse("0 0.5 0.5 0.2\nsquare 0.5 0.5 0.2 0.2\n0 a 0.5 0.2 0.2\n0 0.5 0.5 0.2 0.2 0.9\n0 nan 0.5 0.2 0.2\n")
        self.assertEqual(codes(p), ["malformed_line"] * 5)
        self.assertEqual([i.line for i in p.issues], [1, 2, 3, 4, 5])
        self.assertEqual((p.total_lines, p.invalid_lines, len(p.boxes)), (5, 5, 0))

    def test_invalid_class_ids(self):
        self.assertIn("invalid_class_id", codes(parse("3 0.5 0.5 0.2 0.2\n")))
        self.assertIn("invalid_class_id", codes(parse("-1 0.5 0.5 0.2 0.2\n")))
        self.assertNotIn("invalid_class_id", codes(parse("7 0.5 0.5 0.2 0.2\n", classes=None)))

    def test_negative_and_out_of_range_coordinates(self):
        self.assertEqual(codes(parse("0 -0.1 0.5 0.2 0.2\n")), ["negative_coordinate"])
        self.assertEqual(codes(parse("0 160 120 50 40\n")), ["coordinate_out_of_range"])

    def test_invalid_and_zero_sizes(self):
        self.assertEqual(codes(parse("0 0.5 0.5 -0.2 0.2\n")), ["invalid_size"])
        self.assertEqual(codes(parse("0 0.5 0.5 0.0 0.2\n")), ["zero_area"])

    def test_error_lines_never_become_boxes(self):
        p = parse("0 0.5 0.5 0.0 0.2\n1 0.5 0.5 0.2 0.2\n")
        self.assertEqual([b.class_id for b in p.boxes], [1])
        self.assertEqual(p.invalid_lines, 1)

    def test_tiny_large_and_out_of_bounds_are_warnings(self):
        p = parse("0 0.5 0.5 0.005 0.005\n1 0.5 0.5 0.99 0.99\n2 0.98 0.5 0.1 0.1\n")
        self.assertEqual(sorted(codes(p)), ["box_out_of_bounds", "large_box", "tiny_box"])
        self.assertTrue(all(ISSUE_LEVELS[c] == "warning" for c in codes(p)))
        self.assertEqual(p.invalid_lines, 0)
        self.assertEqual(len(p.boxes), 3)

    def test_duplicate_annotations_detected_only_for_same_class(self):
        self.assertIn("duplicate_annotation", codes(parse("0 0.3 0.3 0.1 0.1\n0 0.3 0.3 0.1 0.1\n")))
        self.assertNotIn("duplicate_annotation", codes(parse("0 0.3 0.3 0.1 0.1\n1 0.3 0.3 0.1 0.1\n")))

    def test_polygon_lines_are_reduced_to_boxes(self):
        p = parse("1 0.1 0.1 0.5 0.1 0.5 0.4 0.1 0.4\n")
        self.assertEqual(len(p.boxes), 1)
        b = p.boxes[0]
        self.assertIn("polygon", b.flags)
        self.assertAlmostEqual(b.w, 0.4)
        self.assertAlmostEqual(b.h, 0.3)

    def test_nothing_is_silently_dropped(self):
        text = "0 0.5 0.5 0.2 0.2\nbad line\n0 2 2 2 2\n"
        p = parse(text)
        self.assertEqual(p.total_lines, 3)
        self.assertEqual(len(p.boxes) + p.invalid_lines, 3)


if __name__ == "__main__":
    unittest.main()
