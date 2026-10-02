import unittest

import cv2
import numpy as np
from PIL import Image

from imageaudit.analyzers import hashing
from imageaudit.analyzers.image import ImageAnalyzer
from imageaudit.analyzers.quality import quality_flags
from imageaudit.core.config import AuditConfig

from .helpers import TempCase, textured, write_img


class HashingTests(unittest.TestCase):
    def test_identical_images_have_zero_distance(self):
        g = cv2.cvtColor(textured(1), cv2.COLOR_BGR2GRAY)
        self.assertEqual(hashing.hamming(hashing.phash(g), hashing.phash(g.copy())), 0)

    def test_recompression_stays_close_but_different_images_do_not(self):
        img = textured(2)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 40])
        again = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        other = cv2.cvtColor(textured(3), cv2.COLOR_BGR2GRAY)
        self.assertLessEqual(hashing.hamming(hashing.phash(g), hashing.phash(again)), 6)
        self.assertGreater(hashing.hamming(hashing.phash(g), hashing.phash(other)), 12)

    def test_hex_roundtrip_is_64_bit(self):
        h = hashing.phash(cv2.cvtColor(textured(4), cv2.COLOR_BGR2GRAY))
        self.assertEqual(hashing.from_hex(hashing.to_hex(h)), h)
        self.assertEqual(len(hashing.to_hex(h)), 16)


class ImageAnalyzerTests(TempCase):
    def setUp(self):
        super().setUp()
        self.an = ImageAnalyzer(AuditConfig())

    def test_valid_image_measurements(self):
        p = write_img(self.tmp / "ok.jpg", textured(5, 200, 100))
        m = self.an.analyze(p)
        self.assertEqual(m.status, "ok")
        self.assertEqual((m.width, m.height, m.format, m.channels), (200, 100, "JPEG", 3))
        self.assertEqual(len(m.sha256), 64)
        self.assertEqual(len(m.phash), 16)
        self.assertTrue(m.hash_reliable)
        self.assertFalse(m.is_grayscale)
        self.assertGreater(m.file_size, 0)

    def test_corrupted_file_is_reported_not_raised(self):
        p = self.tmp / "bad.jpg"
        p.write_bytes(b"\xff\xd8\xff\xe0 definitely not a jpeg")
        m = self.an.analyze(p)
        self.assertEqual(m.status, "corrupted")
        self.assertTrue(m.error)

    def test_truncated_jpeg_is_corrupted(self):
        good = write_img(self.tmp / "good.jpg", textured(6)).read_bytes()
        p = self.tmp / "trunc.jpg"
        p.write_bytes(good[: len(good) // 2])
        self.assertEqual(self.an.analyze(p).status, "corrupted")

    def test_zero_byte_file(self):
        p = self.tmp / "empty.png"
        p.write_bytes(b"")
        self.assertEqual(self.an.analyze(p).status, "zero_byte")

    def test_unsupported_format_and_forced_status(self):
        p = self.tmp / "anim.gif"
        Image.new("P", (16, 16)).save(p, format="GIF")
        self.assertEqual(self.an.analyze(p).status, "unsupported")
        q = self.tmp / "notes.txt"
        q.write_text("hello")
        self.assertEqual(self.an.analyze(q, force_status="unsupported").status, "unsupported")

    def test_blur_score_separates_sharp_from_blurred(self):
        sharp = textured(7, 320, 240)
        blurred = cv2.GaussianBlur(sharp, (0, 0), 6)
        ms = self.an.analyze(write_img(self.tmp / "s.png", sharp))
        mb = self.an.analyze(write_img(self.tmp / "b.png", blurred))
        self.assertGreater(ms.blur_score, mb.blur_score * 10)
        cfg = AuditConfig().quality
        self.assertNotIn("blurry", quality_flags(ms, cfg))
        self.assertIn("blurry", quality_flags(mb, cfg))

    def test_exposure_and_contrast_flags(self):
        base = textured(8)
        dark = self.an.analyze(write_img(self.tmp / "d.png", (base * 0.05).astype(np.uint8)))
        bright = self.an.analyze(write_img(self.tmp / "l.png", np.clip(base * 0.1 + 235, 0, 255).astype(np.uint8)))
        cfg = AuditConfig().quality
        self.assertIn("dark", quality_flags(dark, cfg))
        self.assertIn("bright", quality_flags(bright, cfg))
        self.assertLess(dark.brightness, bright.brightness)

    def test_grayscale_detection_including_rgb_stored_gray(self):
        g = cv2.cvtColor(textured(9), cv2.COLOR_BGR2GRAY)
        m1 = self.an.analyze(write_img(self.tmp / "g1.png", g))
        m2 = self.an.analyze(write_img(self.tmp / "g2.png", cv2.merge([g, g, g])))
        self.assertTrue(m1.is_grayscale)
        self.assertEqual(m1.channels, 1)
        self.assertTrue(m2.is_grayscale)
        self.assertEqual(m2.channels, 3)

    def test_low_resolution_and_extreme_aspect_flags(self):
        cfg = AuditConfig().quality
        small = self.an.analyze(write_img(self.tmp / "s.png", textured(10, 40, 30)))
        wide = self.an.analyze(write_img(self.tmp / "w.png", textured(11, 800, 100)))
        self.assertIn("low_resolution", quality_flags(small, cfg))
        self.assertIn("extreme_aspect", quality_flags(wide, cfg))

    def test_oversized_pixel_count_is_rejected_without_decoding(self):
        cfg = AuditConfig(max_pixels=1000)
        m = ImageAnalyzer(cfg).analyze(write_img(self.tmp / "big.png", textured(12)))
        self.assertEqual(m.status, "too_large")

    def test_validate_mode_skips_pixel_statistics(self):
        m = ImageAnalyzer(AuditConfig(), full=False).analyze(write_img(self.tmp / "a.jpg", textured(13)))
        self.assertEqual(m.status, "ok")
        self.assertIsNone(m.blur_score)
        self.assertIsNone(m.phash)

    def test_exif_rotated_images_report_displayed_dimensions(self):
        p = self.tmp / "rot.jpg"
        im = Image.fromarray(cv2.cvtColor(textured(14, 200, 100), cv2.COLOR_BGR2RGB))
        exif = Image.Exif()
        exif[0x0112] = 6  # rotate 90 deg CW when displayed
        im.save(p, exif=exif)
        m = self.an.analyze(p)
        self.assertEqual((m.width, m.height), (100, 200))

    def test_flat_image_is_not_hash_reliable(self):
        flat = np.full((64, 64, 3), 128, np.uint8)
        m = self.an.analyze(write_img(self.tmp / "flat.png", flat))
        self.assertFalse(m.hash_reliable)


if __name__ == "__main__":
    unittest.main()
