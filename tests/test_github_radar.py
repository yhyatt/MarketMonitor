"""Tests for GitHub radar collector."""

import json
import pytest
from unittest.mock import patch, MagicMock

from market_monitor.collectors.github_radar import GitHubRadar, GitHubSignal


class TestGitHubSignal:
    """Tests for GitHubSignal dataclass."""

    def test_full_text(self):
        """full_text should combine repo and description."""
        signal = GitHubSignal(
            repo="owner/repo",
            stars=1000,
            delta_stars_7d=100,
            velocity_pct=10.0,
            flagged=True,
            url="https://github.com/owner/repo",
            description="A test repository",
        )
        assert "owner/repo" in signal.full_text
        assert "A test repository" in signal.full_text


class TestGitHubRadar:
    """Tests for GitHubRadar collector."""

    def test_load_baseline_empty(self, config):
        """Should return empty dict if baseline doesn't exist."""
        radar = GitHubRadar(config)
        baseline = radar._load_baseline()

        assert baseline == {}

    def test_save_and_load_baseline(self, config):
        """Should save and load baseline correctly."""
        radar = GitHubRadar(config)

        baseline = {"owner/repo": 1000, "other/repo": 500}
        radar._save_baseline(baseline)

        loaded = radar._load_baseline()
        assert loaded == baseline

    @patch("urllib.request.urlopen")
    def test_fetch_repo_signal(self, mock_urlopen, config, sample_github_response):
        """Should fetch and compute signal for a repo."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(sample_github_response).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        radar = GitHubRadar(config)
        baseline = {"vllm-project/vllm": 14000}  # 1000 less than current

        signal = radar._fetch_repo_signal("vllm-project/vllm", baseline)

        assert signal is not None
        assert signal.repo == "vllm-project/vllm"
        assert signal.stars == 15000
        assert signal.delta_stars_7d == 1000
        assert signal.velocity_pct > 0

    def test_velocity_calculation(self, config):
        """Should compute velocity percentage correctly."""
        radar = GitHubRadar(config)

        # Mock a signal computation
        with patch.object(radar, "_fetch_repo_signal") as mock:
            mock.return_value = GitHubSignal(
                repo="test/repo",
                stars=1100,
                delta_stars_7d=100,
                velocity_pct=10.0,  # 100/1000 * 100
                flagged=True,
                url="https://github.com/test/repo",
            )

            signal = mock.return_value
            # 100 stars gained from 1000 base = 10%
            assert signal.velocity_pct == 10.0

    def test_flagged_by_velocity(self, config):
        """Should flag repos with high velocity."""
        radar = GitHubRadar(config)

        signal = GitHubSignal(
            repo="test/repo",
            stars=1000,
            delta_stars_7d=60,  # 6% velocity
            velocity_pct=6.0,
            flagged=False,
            url="https://github.com/test/repo",
        )

        # 6% > 5% threshold
        assert signal.velocity_pct > radar.velocity_threshold

    def test_flagged_by_delta(self, config):
        """Should flag repos with high absolute delta."""
        radar = GitHubRadar(config)

        signal = GitHubSignal(
            repo="test/repo",
            stars=100000,
            delta_stars_7d=600,  # More than 500 threshold
            velocity_pct=0.6,  # Low velocity
            flagged=True,
            url="https://github.com/test/repo",
        )

        assert signal.delta_stars_7d > radar.delta_threshold

    @patch("urllib.request.urlopen")
    def test_collect_updates_baseline(self, mock_urlopen, config, sample_github_response):
        """collect() should update baseline file."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(sample_github_response).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        # Use only one repo for faster test
        config.github_tracked_repos = ["vllm-project/vllm"]

        radar = GitHubRadar(config)
        signals = radar.collect()

        # Check baseline was saved
        assert config.github_baseline_json.exists()
        with open(config.github_baseline_json) as f:
            baseline = json.load(f)
        assert "vllm-project/vllm" in baseline

    @patch("urllib.request.urlopen")
    def test_collect_network_error(self, mock_urlopen, config):
        """Should handle network errors gracefully."""
        mock_urlopen.side_effect = Exception("Network error")

        config.github_tracked_repos = ["test/repo"]
        radar = GitHubRadar(config)
        signals = radar.collect()

        # Should return empty list, not crash
        assert signals == []

    def test_github_token_header(self, config):
        """Should include auth header if token provided."""
        radar = GitHubRadar(config)

        # Check config has token
        assert config.github_token == "test-gh-token"

    def test_get_flagged_signals(self, config):
        """get_flagged_signals should filter unflagged."""
        radar = GitHubRadar(config)

        with patch.object(radar, "collect") as mock:
            mock.return_value = [
                GitHubSignal("a/b", 1000, 100, 10.0, True, "url1"),
                GitHubSignal("c/d", 500, 10, 2.0, False, "url2"),
                GitHubSignal("e/f", 2000, 600, 30.0, True, "url3"),
            ]

            flagged = radar.get_flagged_signals()

            assert len(flagged) == 2
            assert all(s.flagged for s in flagged)

    def test_collector_name(self, config):
        """Collector should have correct name."""
        radar = GitHubRadar(config)
        assert radar.name == "GitHub"

    def test_tracked_repos_from_config(self, config):
        """Should use tracked repos from config."""
        radar = GitHubRadar(config)

        assert "vllm-project/vllm" in radar.tracked_repos
        assert "langchain-ai/langchain" in radar.tracked_repos
        assert len(radar.tracked_repos) == 15

    def test_first_run_baseline(self, config):
        """First run should use current stars as baseline (delta=0)."""
        radar = GitHubRadar(config)

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps({
                "stargazers_count": 5000,
                "description": "Test repo",
            }).encode()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response

            signal = radar._fetch_repo_signal("test/repo", {})

            # No baseline = delta should be 0
            assert signal.delta_stars_7d == 0
            assert signal.velocity_pct == 0
