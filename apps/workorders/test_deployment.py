from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.test import SimpleTestCase, override_settings
from django.urls import reverse


class VercelCronEndpointTests(SimpleTestCase):
    @override_settings(CRON_SECRET="", MMS_CRON_MAX_OCCURRENCES=100)
    def test_unconfigured_endpoint_is_unavailable(self):
        response = self.client.get(reverse("workorder-cron"))

        self.assertEqual(response.status_code, 503)

    @override_settings(CRON_SECRET="cron-test-secret", MMS_CRON_MAX_OCCURRENCES=25)
    def test_endpoint_rejects_missing_or_incorrect_bearer_token(self):
        for header in ("", "Bearer wrong"):
            with self.subTest(header=header):
                response = self.client.get(
                    reverse("workorder-cron"),
                    HTTP_AUTHORIZATION=header,
                )
                self.assertEqual(response.status_code, 401)

    @override_settings(CRON_SECRET="cron-test-secret", MMS_CRON_MAX_OCCURRENCES=25)
    @patch("apps.workorders.views.generate_recurring_work_orders")
    def test_authorized_endpoint_runs_bounded_scan(self, generate):
        work_order_id = uuid4()
        generate.return_value = [SimpleNamespace(id=work_order_id)]

        response = self.client.get(
            reverse("workorder-cron"),
            HTTP_AUTHORIZATION="Bearer cron-test-secret",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"generated": 1, "work_order_ids": [str(work_order_id)]},
        )
        generate.assert_called_once_with(max_occurrences=25)
        self.assertEqual(response["Cache-Control"], "max-age=0, no-cache, no-store, must-revalidate, private")

    @override_settings(CRON_SECRET="cron-test-secret", MMS_CRON_MAX_OCCURRENCES=25)
    def test_endpoint_accepts_get_only(self):
        response = self.client.post(
            reverse("workorder-cron"),
            HTTP_AUTHORIZATION="Bearer cron-test-secret",
        )

        self.assertEqual(response.status_code, 405)
