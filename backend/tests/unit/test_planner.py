"""Tests for app/agents/planner.py — keyword-based rule planner."""
import pytest

from app.agents.planner import _parse_duration, _rule_based_plan


class TestParseDuration:
    def test_seconds_with_unit(self):
        assert _parse_duration("make a 30 second clip") == 30.0

    def test_secs_abbreviation(self):
        assert _parse_duration("trim to 45 secs") == 45.0

    def test_s_abbreviation(self):
        assert _parse_duration("cut to 12s long") == 12.0

    def test_minutes(self):
        assert _parse_duration("a 2 minute video") == 120.0

    def test_mins_abbreviation(self):
        assert _parse_duration("3 mins") == 180.0

    def test_decimal_seconds(self):
        assert _parse_duration("a 1.5 second clip") == 1.5

    def test_no_match(self):
        assert _parse_duration("no duration mentioned") is None


class TestRuleBasedPlan:
    @pytest.fixture
    def empty_signals(self):
        return {"media_manifest": {"files": []}}

    def test_detects_remove_silence(self, empty_signals):
        plan = _rule_based_plan("Cut silence from this clip", empty_signals)
        assert "remove_silence" in plan["operations"]

    def test_detects_captions(self, empty_signals):
        plan = _rule_based_plan("Add subtitles", empty_signals)
        assert "add_captions" in plan["operations"]

    def test_detects_vertical_aspect(self, empty_signals):
        plan = _rule_based_plan("Make a TikTok video", empty_signals)
        assert plan["style"]["aspect"] == "9:16"
        assert plan["style"]["width"] == 1080
        assert plan["style"]["height"] == 1920

    def test_detects_landscape_aspect(self, empty_signals):
        plan = _rule_based_plan("Horizontal 16:9 edit", empty_signals)
        assert plan["style"]["aspect"] == "16:9"

    def test_detects_square_aspect(self, empty_signals):
        plan = _rule_based_plan("Square Instagram post", empty_signals)
        assert plan["style"]["aspect"] == "1:1"

    def test_detects_high_energy(self, empty_signals):
        plan = _rule_based_plan("Hype montage", empty_signals)
        assert plan["style"]["energy"] == "high"

    def test_detects_low_energy(self, empty_signals):
        plan = _rule_based_plan("calm chill recap", empty_signals)
        assert plan["style"]["energy"] == "low"

    def test_montage_implies_highlights_and_story(self, empty_signals):
        plan = _rule_based_plan("Make a montage", empty_signals)
        assert "highlight_select" in plan["operations"]
        assert "story_compose" in plan["operations"]

    def test_montage_auto_adds_transitions(self, empty_signals):
        plan = _rule_based_plan("Make a montage", empty_signals)
        assert "add_transitions" in plan["operations"]

    def test_target_duration_extracted(self, empty_signals):
        plan = _rule_based_plan("30 second highlight reel", empty_signals)
        assert plan["target_duration"] == 30.0

    def test_priorities_sum_to_one(self, empty_signals):
        plan = _rule_based_plan("vibrant montage", empty_signals)
        total = sum(plan["priorities"].values())
        assert total == pytest.approx(1.0, abs=0.01)

    def test_planner_field_marked_rule_based(self, empty_signals):
        plan = _rule_based_plan("anything", empty_signals)
        assert plan["planner"] == "rule_based"

    def test_operations_deduplicated(self, empty_signals):
        # "captions" and "subtitles" both map to add_captions.
        plan = _rule_based_plan("Add captions and subtitles", empty_signals)
        assert plan["operations"].count("add_captions") == 1

    def test_total_media_duration_summed(self):
        signals = {
            "media_manifest": {
                "files": [
                    {"duration": 10.0},
                    {"duration": 15.0},
                    {"duration": 5.5},
                ]
            }
        }
        plan = _rule_based_plan("anything", signals)
        assert plan["total_media_duration"] == pytest.approx(30.5)
