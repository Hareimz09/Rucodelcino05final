from __future__ import annotations

import base64
import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import TryOnGeneration
from .services.ai_tryon import Placement, _estimate_placement, normalize_uploaded_image_bytes, parse_data_url


TEMP_MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="rucodelcino-test-media-"))


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class TryOnGenerationTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def _png_file(self, name: str) -> SimpleUploadedFile:
        image = Image.new("RGBA", (32, 32), (255, 255, 255, 255))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    def test_update_work_title_is_disabled(self):
        user = get_user_model().objects.create_user(
            username="user@example.com",
            email="user@example.com",
            password="testpass123",
        )
        work = TryOnGeneration.objects.create(
            user=user,
            category=TryOnGeneration.CATEGORY_HAT,
            summary="Бежевая шапка",
            gallery_title="Автоназвание",
            user_image=self._png_file("user.png"),
            accessory_image=self._png_file("accessory.png"),
            result_image=self._png_file("result.png"),
        )

        self.client.force_login(user)
        response = self.client.post(
            reverse("update_work_title", args=[work.id]),
            {
                "gallery_title": "Новое название",
                "next": reverse("account"),
            },
        )

        work.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(work.gallery_title, "Автоназвание")
        self.assertFalse(work.title_was_edited)

    def test_standard_hat_placement_is_tighter_and_lower(self):
        user_photo = Image.new("RGBA", (740, 1110), (255, 255, 255, 255))
        accessory = Image.new("RGBA", (1200, 1200), (120, 120, 120, 255))

        with patch("constructor.services.ai_tryon._detect_face_box", return_value=(251, 218, 259, 259)):
            placement, face_box, warnings = _estimate_placement(
                user_photo,
                accessory,
                "hat",
                {"hat_model_slug": "beanie"},
            )

        self.assertEqual(face_box, (251, 218, 259, 259))
        self.assertEqual(warnings, [])
        self.assertGreater(placement.y, 40)
        self.assertLessEqual(placement.height, 190)
        self.assertLessEqual(placement.width, 330)

    def test_hat_fallback_without_face_detection_keeps_hat_in_upper_head_zone(self):
        user_photo = Image.new("RGBA", (740, 1110), (255, 255, 255, 255))
        accessory = Image.new("RGBA", (1200, 1200), (120, 120, 120, 255))

        with patch("constructor.services.ai_tryon._detect_face_box", return_value=None):
            placement, face_box, warnings = _estimate_placement(
                user_photo,
                accessory,
                "hat",
                {"hat_model_slug": "beanie"},
            )

        self.assertIsNone(face_box)
        self.assertIn("Лицо не найдено автоматически, использована приблизительная посадка.", warnings)
        self.assertGreaterEqual(placement.y, 70)
        self.assertLessEqual(placement.y, 110)
        self.assertLessEqual(placement.height, 190)

    def test_bracelet_placement_prefers_detected_wrist_geometry(self):
        user_photo = Image.new("RGBA", (740, 1110), (255, 255, 255, 255))
        accessory = Image.new("RGBA", (1200, 680), (120, 120, 120, 255))

        with patch("constructor.services.ai_tryon._detect_face_box", return_value=None), patch(
            "constructor.services.ai_tryon._estimate_bracelet_placement",
            return_value=Placement(x=140, y=520, width=210, height=118, rotation=84.0),
        ):
            placement, face_box, warnings = _estimate_placement(
                user_photo,
                accessory,
                "jewelry",
                {"jewelry_kind_code": "bracelet"},
            )

        self.assertIsNone(face_box)
        self.assertEqual(warnings, [])
        self.assertEqual(placement.x, 140)
        self.assertEqual(placement.y, 520)
        self.assertEqual(placement.rotation, 84.0)


class ImageNormalizationTests(TestCase):
    def test_parse_data_url_accepts_octet_stream_payload(self):
        payload = base64.b64encode(b"abc").decode("ascii")
        self.assertEqual(parse_data_url(f"data:application/octet-stream;base64,{payload}"), b"abc")

    def test_normalize_uploaded_image_bytes_converts_png_to_jpeg(self):
        image = Image.new("RGBA", (24, 24), (10, 20, 30, 255))
        buffer = BytesIO()
        image.save(buffer, format="PNG")

        normalized = normalize_uploaded_image_bytes(buffer.getvalue(), output_format="JPEG")
        reopened = Image.open(BytesIO(normalized))

        self.assertEqual(reopened.format, "JPEG")
        self.assertEqual(reopened.size, (24, 24))
