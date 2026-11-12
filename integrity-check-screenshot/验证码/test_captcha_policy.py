# -*- coding: utf-8 -*-
"""验证码重试与人工介入策略的离线测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "GUI"))

from modules.scraper import actions_captcha as ac
from modules.scraper import batch_runner
from modules.scraper import actions_basic
from modules.scraper import foreground_runner
from modules.scraper.site_configs import WEB_CONFIG, default_2, default_3


class CaptchaPolicyTests(unittest.TestCase):
    def test_normal_ocr_model_is_selected(self):
        self.assertFalse(ac.DDDD_OCR_BETA)

    def test_manual_threshold_is_inclusive(self):
        with patch.object(ac, "_CAPTCHA_SITE_COUNT", 10):
            self.assertTrue(ac._manual_allowed())
        with patch.object(ac, "_CAPTCHA_SITE_COUNT", 11):
            self.assertFalse(ac._manual_allowed())

    def test_court_result_returns_immediately_when_signal_is_true(self):
        with patch.object(ac, "_court_result_appeared", return_value="rows"):
            with patch.object(ac.time, "sleep") as sleep:
                self.assertTrue(ac._wait_court_result(None, {}, timeout=5))
        sleep.assert_not_called()

    def test_court_result_waits_for_popup_to_close(self):
        popup = object()
        page = Mock()
        with patch.object(ac, "_court_result_appeared", return_value="rows"):
            with patch.object(ac, "_find_popup", side_effect=[popup, None]) as find_popup:
                with patch.object(ac, "_popup_visible", side_effect=[True, False]):
                    with patch.object(ac.time, "sleep") as sleep:
                        self.assertTrue(ac._wait_court_result(page, {}, timeout=5))
        self.assertEqual(find_popup.call_args_list[0].kwargs, {"timeout": 0.1})
        sleep.assert_called_once_with(ac.MANUAL_POLL_INTERVAL)

    def test_court_observation_prioritizes_visible_popup(self):
        popup = object()
        with patch.object(ac, "_find_popup", return_value=popup):
            with patch.object(ac, "_popup_visible", return_value=True):
                with patch.object(ac, "_court_result_appeared", return_value="rows"):
                    outcome, found_popup = ac._observe_after_query(None, {}, timeout=5)
        self.assertEqual(outcome, "popup")
        self.assertIs(found_popup, popup)

    def test_manual_court_poll_uses_0_3_seconds(self):
        page = Mock()
        page.run_js.side_effect = ["old title", None, None]
        popup = object()
        clock = [0.0]

        def now():
            return clock[0]

        def advance(seconds):
            clock[0] += seconds

        with patch.object(ac, "_court_result_appeared", return_value=""):
            with patch.object(ac, "_find_popup", return_value=popup):
                with patch.object(ac.time, "time", side_effect=now):
                    with patch.object(ac.time, "sleep", side_effect=advance) as sleep:
                        self.assertFalse(ac._manual_fallback(page, {}, timeout=0.9))

        self.assertTrue(sleep.call_count >= 3)
        self.assertTrue(all(call.args == (0.3,) for call in sleep.call_args_list))

    def test_manual_court_uses_five_second_wait_after_popup_disappears(self):
        page = Mock()
        page.run_js.side_effect = ["old title", None, None]
        with patch.object(ac, "_court_result_appeared", return_value=""):
            with patch.object(ac, "_find_popup", return_value=None):
                with patch.object(ac, "_wait_court_result", return_value=True) as wait:
                    self.assertTrue(ac._manual_fallback(page, {}))
        wait.assert_called_once_with(page, {}, timeout=ac.MANUAL_RESULT_WAIT)
        self.assertEqual(ac.MANUAL_RESULT_WAIT, 5)

    def test_batch_runner_injects_and_clears_site_count(self):
        log_queue = Mock()
        sites = [f"site-{index}" for index in range(11)]
        with patch.object(batch_runner, "set_captcha_site_count") as set_count:
            batch_runner.run_batch_screenshot_task(
                [], log_queue, str(REPO), sites, {}, 0
            )
        self.assertEqual(set_count.call_args_list[0].args, (11,))
        self.assertEqual(set_count.call_args_list[-1].args, (0,))

    def test_transport_config_uses_previous_result_navigation(self):
        config_key = next(key for key in default_2 if "交通运输部" in key)
        config = default_2[config_key]
        self.assertTrue(config.get("require_result_navigation"))
        self.assertEqual(config.get("popup_timeout"), 15)
        self.assertNotIn("action_ready_selector", config)

    def test_statistics_action_only_fills_input_and_waits(self):
        page = Mock()
        search_input = Mock()
        page.ele.return_value = search_input
        with patch.object(actions_basic.time, "sleep"):
            actions_basic.action_tongji_info(page, "示例主体")
        search_input.input.assert_called_once_with("示例主体")
        search_input.click.assert_not_called()

    def test_action_ready_selector_precedes_document_ready_state(self):
        tab = Mock()
        tab.ele.return_value = object()
        config = {"action_ready_selector": "#qt", "load_timeout": 7}
        with patch.object(foreground_runner, "wait_tab_ready") as wait_ready:
            self.assertTrue(foreground_runner._wait_action_ready(tab, config))
        tab.ele.assert_called_once_with("#qt", timeout=7)
        wait_ready.assert_not_called()

    def test_csrc_site_configs_keep_original_frontend_settings(self):
        presets = (WEB_CONFIG, default_2, default_3)
        for preset in presets:
            captcha_configs = [
                config for key, config in preset.items()
                if "证监会证券期货市场失信记录" in key
            ]
            for config in captcha_configs:
                self.assertNotIn("action_ready_selector", config)
                self.assertNotIn("require_result_navigation", config)
                self.assertNotIn("result_require_complete", config)

    def test_court_configs_have_bounded_startup_wait(self):
        for preset in (WEB_CONFIG, default_2, default_3):
            court_configs = [
                config for key, config in preset.items()
                if "执行信息公开网" in key or "失信被执行人名单" in key
            ]
            for config in court_configs:
                self.assertEqual(config.get("load_timeout"), 15)
                self.assertEqual(config.get("action_ready_selector"), "#pName")


if __name__ == "__main__":
    unittest.main()
