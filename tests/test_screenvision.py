import io
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

import numpy as np
from PIL import Image

os.environ.setdefault("SCREENVISION_AGREE", "1")
os.environ.setdefault("SCREENVISION_TOKEN", "test-secret")

import screen_vision
import snap_server


class FakeCapture:
    monitors = [
        {"left": 0, "top": 0, "width": 200, "height": 100},
        {"left": 0, "top": 0, "width": 100, "height": 100, "is_primary": True},
        {"left": 100, "top": 0, "width": 100, "height": 100},
    ]


class ScreenVisionTests(unittest.TestCase):
    def test_invalid_monitor_is_rejected_instead_of_capturing_all_screens(self):
        with self.assertRaisesRegex(ValueError, "invalid monitor selector"):
            snap_server._pick_monitor(FakeCapture(), "not-a-monitor")

    def test_invalid_monitor_request_returns_400(self):
        snap_server.TOKEN = "test-secret"
        server = ThreadingHTTPServer(("127.0.0.1", 0), snap_server.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/snap?screen=not-a-monitor"
            request = urllib.request.Request(
                url,
                headers={"X-Auth-Token": "test-secret"},
            )
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request, timeout=2)
            self.assertEqual(caught.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_screenshot_token_is_sent_in_a_header_not_the_url(self):
        image = Image.new("RGB", (2, 2), "black")
        encoded = io.BytesIO()
        image.save(encoded, format="JPEG")

        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = encoded.getvalue()
        response.__exit__.return_value = False
        with mock.patch("screen_vision.urllib.request.urlopen", return_value=response) as open_mock:
            screen_vision._fetch_and_encode()

        request = open_mock.call_args.args[0]
        self.assertNotIn("test-secret", request.full_url)
        self.assertEqual(request.get_header("X-auth-token"), "test-secret")

    def test_graph_expression_evaluator_supports_expected_math(self):
        x = np.array([0.0, 1.0, 2.0])
        actual = screen_vision._safe_expr_eval("sin(x) + x^2 + pi", x)
        expected = np.sin(x) + x**2 + np.pi
        np.testing.assert_allclose(actual, expected)

    def test_graph_expression_evaluator_rejects_object_traversal_and_code(self):
        bad_expressions = (
            "(1).__class__",
            "__import__('os').system('whoami')",
            "[item for item in x]",
            "x.__class__",
        )
        for expression in bad_expressions:
            with self.subTest(expression=expression):
                with self.assertRaises(ValueError):
                    screen_vision._safe_expr_eval(expression, np.array([1.0]))


if __name__ == "__main__":
    unittest.main()
