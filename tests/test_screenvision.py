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

    def test_calc_eval_matches_decibel_and_compound_interest(self):
        db = screen_vision._safe_calc_eval("10*log10(9e-3/1e-12)")
        self.assertAlmostEqual(db, 99.54242509439325, places=6)
        cd = screen_vision._safe_calc_eval("2500*(1+0.045/4)**(4*4)")
        self.assertAlmostEqual(cd, 2990.037, places=2)

    def test_exam_parser_calculator_overrides_wrong_letter(self):
        reply = (
            "ANSWER: C\n"
            "CALC: 10*log10(9e-3/1e-12)\n"
            "OPTIONS: A=-2; B=10; C=229.2; D=100\n"
        )
        letter, expr, options = screen_vision._parse_exam_spec(reply)
        self.assertEqual(letter, "C")
        val = screen_vision._safe_calc_eval(expr)
        closest = min(options, key=lambda k: abs(options[k] - val))
        self.assertEqual(closest, "D")

    def test_calc_eval_rejects_imports(self):
        with self.assertRaises(ValueError):
            screen_vision._safe_calc_eval("__import__('os').system('whoami')")

    def test_calc_eval_allows_round_and_dotted_math(self):
        self.assertAlmostEqual(
            screen_vision._safe_calc_eval("round(2500*(1+0.045/4)**16, 2)"), 2990.04, places=2)
        self.assertAlmostEqual(screen_vision._safe_calc_eval("math.log10(1000)"), 3.0, places=9)

    def test_calc_eval_refuses_to_hang_on_huge_exponents(self):
        with self.assertRaises(ValueError):
            screen_vision._safe_calc_eval("9**9**9")

    def test_option_list_survives_thousands_separators(self):
        _letter, _expr, options = screen_vision._parse_exam_spec(
            "ANSWER: C\nCALC: 1+1\nOPTIONS: A=$2,545.38; B=$2,990.03; C=$13,763.86\n")
        self.assertEqual(options, {"A": 2545.38, "B": 2990.03, "C": 13763.86})

    def test_research_off_costs_no_extra_model_calls(self):
        """Default path must stay one call — the whole point of the opt-in gate."""
        calls = []

        def fake_ask(_b64, mode, _prompt=None):
            calls.append(mode)
            return "ANSWER: B\nCALC: none\nOPTIONS: none\n"

        with mock.patch.object(screen_vision, "_ask_blocking", fake_ask), \
                mock.patch.object(screen_vision, "_RESEARCH", "Off"):
            out = screen_vision._exam_answer("fake-b64")
        self.assertEqual(calls, ["Exam"])
        self.assertEqual(out, "B")

    def test_research_cites_its_source_when_evidence_supports_an_option(self):
        def fake_ask(_b64, mode, _prompt=None):
            if mode == "Transcribe":
                return "Which organelle performs photosynthesis?\nA. Ribosome\nB. Chloroplast"
            return "ANSWER: A\nCALC: none\nOPTIONS: none\n"

        with mock.patch.object(screen_vision, "_ask_blocking", fake_ask), \
                mock.patch.object(screen_vision, "_RESEARCH", "Wikipedia"), \
                mock.patch.object(screen_vision, "_wiki_search", lambda q, n=3: [
                    ("Wikipedia — Chloroplast", "http://x", "Chloroplasts conduct photosynthesis.")]), \
                mock.patch.object(screen_vision, "_text_ask",
                                  lambda *a, **k: "ANSWER: B\nCITE: Chloroplasts conduct photosynthesis."):
            out = screen_vision._exam_answer("fake-b64")
        self.assertTrue(out.startswith("B"), out)
        self.assertIn("Chloroplasts conduct photosynthesis", out)
        self.assertIn("Wikipedia — Chloroplast", out)
        self.assertIn("model first said A", out)

    def test_research_says_so_instead_of_failing_open(self):
        """No evidence must be announced, not silently swapped for a guess."""
        def fake_ask(_b64, mode, _prompt=None):
            if mode == "Transcribe":
                return "Some question?\nA. one\nB. two"
            return "ANSWER: A\nCALC: none\nOPTIONS: none\n"

        with mock.patch.object(screen_vision, "_ask_blocking", fake_ask), \
                mock.patch.object(screen_vision, "_RESEARCH", "Wikipedia"), \
                mock.patch.object(screen_vision, "_wiki_search", lambda q, n=3: []):
            out = screen_vision._exam_answer("fake-b64")
        self.assertIn("model's own answer", out)
        self.assertTrue(out.startswith("A"), out)


if __name__ == "__main__":
    unittest.main()
