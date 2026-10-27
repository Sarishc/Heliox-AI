"""Tests for the Heliox GPU agent (plan task 1.2)."""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import heliox_agent as agent  # noqa: E402

# ── GPU name decoding ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw", [b"NVIDIA A100-SXM4-80GB", "NVIDIA A100-SXM4-80GB"])
def test_gpu_name_accepts_bytes_and_str(raw):
    # Older pynvml returns bytes, current pynvml returns str
    assert agent.decode_gpu_name(raw) == "NVIDIA A100-SXM4-80GB"


def test_normalize_gpu_name():
    assert agent.normalize_gpu_name("NVIDIA A100-SXM4-80GB") == "a100"
    assert agent.normalize_gpu_name("NVIDIA H100 80GB HBM3") == "h100"
    assert agent.normalize_gpu_name("Tesla T4") == "tesla-t4"


# ── No silent mock data ────────────────────────────────────────────────────────


def test_missing_nvml_is_an_error_not_mock_data(monkeypatch):
    monkeypatch.setitem(sys.modules, "pynvml", None)  # import pynvml -> ImportError

    with pytest.raises(agent.AgentError, match="NVML"):
        agent.open_reader(mock=False)


def test_mock_reader_only_when_asked():
    reader = agent.open_reader(mock=True)
    samples = reader.read()
    assert samples and all(s["gpu_type"] == "mock-gpu" for s in samples)


# ── Busy GPU-hours from sampled utilization ────────────────────────────────────


def test_accumulator_averages_samples_over_real_elapsed_time():
    acc = agent.IntervalAccumulator()
    acc.add([{"index": 0, "gpu_type": "a100", "utilization": 100.0}])
    acc.add([{"index": 0, "gpu_type": "a100", "utilization": 0.0}])

    # 50% average over 2 hours = 1 busy GPU-hour
    result = acc.flush(elapsed_seconds=7200)

    # Busy hours for idle waste, plus the hours the GPU was powered (what you pay for)
    assert result == [{"gpu_type": "a100", "gpu_hours": 1.0, "allocated_gpu_hours": 2.0}]


def test_accumulator_reports_each_gpu_separately():
    acc = agent.IntervalAccumulator()
    acc.add(
        [
            {"index": 0, "gpu_type": "a100", "utilization": 100.0},
            {"index": 1, "gpu_type": "a100", "utilization": 50.0},
        ]
    )

    result = acc.flush(elapsed_seconds=3600)

    assert sorted(r["gpu_hours"] for r in result) == [0.5, 1.0]
    assert [r["allocated_gpu_hours"] for r in result] == [1.0, 1.0]


def test_accumulator_is_empty_after_flush():
    acc = agent.IntervalAccumulator()
    acc.add([{"index": 0, "gpu_type": "a100", "utilization": 80.0}])
    acc.flush(elapsed_seconds=60)

    assert acc.flush(elapsed_seconds=60) == []


def test_usage_payload_shape():
    now = datetime(2026, 10, 27, tzinfo=timezone.utc)
    payload = agent.build_usage_payload(
        [{"gpu_type": "a100", "gpu_hours": 0.25, "allocated_gpu_hours": 1.0}],
        provider="aws",
        tags={"node": "n1"},
        now=now,
    )

    assert payload == {
        "metrics": [
            {
                "timestamp": now.isoformat(),
                "provider": "aws",
                "gpu_type": "a100",
                "gpu_hours": 0.25,
                "allocated_gpu_hours": 1.0,
                "tags": {"node": "n1"},
            }
        ]
    }


def test_cost_estimate_prices_powered_hours_not_busy_hours():
    # A powered GPU costs the same whether it's busy or idle
    now = datetime(2026, 10, 27, tzinfo=timezone.utc)
    payload = agent.build_cost_payload(
        [{"gpu_type": "a100", "gpu_hours": 0.25, "allocated_gpu_hours": 1.0}], provider="aws", now=now
    )

    assert payload["records"][0]["cost_usd"] == agent.PRICING_TABLE["a100"]["aws"]


# ── Cost estimates are opt-in ──────────────────────────────────────────────────


def test_send_costs_is_off_by_default():
    assert agent.parse_args(["--endpoint", "http://x"]).send_costs is False


def test_send_costs_can_be_turned_on():
    assert agent.parse_args(["--endpoint", "http://x", "--send-costs"]).send_costs is True


# ── API key never on the command line ──────────────────────────────────────────


def test_api_key_flag_is_rejected():
    with pytest.raises(SystemExit):
        agent.parse_args(["--endpoint", "http://x", "--api-key", "secret"])


def test_api_key_from_env():
    assert agent.load_api_key({"HELIOX_API_KEY": " k1 \n"}, api_key_file=None) == "k1"


def test_api_key_from_file(tmp_path):
    key_file = tmp_path / "api_key"
    key_file.write_text("k2\n")

    assert agent.load_api_key({}, api_key_file=str(key_file)) == "k2"


def test_missing_api_key_is_an_error():
    with pytest.raises(agent.AgentError, match="HELIOX_API_KEY"):
        agent.load_api_key({}, api_key_file=None)


# ── Provider detection ─────────────────────────────────────────────────────────


class FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class FakeHTTP:
    """Answers only the metadata endpoint of one cloud; everything else fails."""

    def __init__(self, cloud):
        self.cloud = cloud

    def request(self, method, url, headers=None, timeout=None):
        headers = headers or {}
        if self.cloud == "aws" and "169.254.169.254/latest" in url:
            return FakeResponse(200, "token")
        if self.cloud == "gcp" and "metadata.google.internal" in url and headers.get("Metadata-Flavor") == "Google":
            return FakeResponse(200, "projects/123")
        if self.cloud == "azure" and "metadata/instance" in url and headers.get("Metadata") == "true":
            return FakeResponse(200, "{}")
        raise ConnectionError("unreachable")


@pytest.mark.parametrize("cloud", ["aws", "gcp", "azure"])
def test_detect_provider(cloud):
    assert agent.detect_provider(FakeHTTP(cloud)) == cloud


def test_detect_provider_falls_back_to_on_prem():
    assert agent.detect_provider(FakeHTTP(None)) == "on-prem"


def test_provider_flag_overrides_detection():
    args = agent.parse_args(["--endpoint", "http://x", "--provider", "gcp"])
    assert agent.resolve_provider(args, http=FakeHTTP("aws")) == "gcp"


# ── Shutdown ───────────────────────────────────────────────────────────────────


def test_sigterm_exits_cleanly():
    # As PID 1 in a container, Python ignores SIGTERM unless a handler is installed,
    # so Kubernetes would have to wait out the grace period and SIGKILL the pod
    import os
    import signal

    previous = signal.getsignal(signal.SIGTERM)
    try:
        agent.install_signal_handlers()
        with pytest.raises(SystemExit) as exc_info:
            os.kill(os.getpid(), signal.SIGTERM)
        assert exc_info.value.code == 0
    finally:
        signal.signal(signal.SIGTERM, previous)


# ── Tags ───────────────────────────────────────────────────────────────────────


def test_tags_include_kubernetes_node_and_flags():
    args = agent.parse_args(
        ["--endpoint", "http://x", "--environment", "prod", "--project", "llm", "--tags", '{"cluster": "c1"}']
    )

    tags = agent.build_tags(args, env={"NODE_NAME": "gpu-node-7"})

    assert tags == {"cluster": "c1", "environment": "prod", "project": "llm", "node": "gpu-node-7"}


def test_invalid_tags_json_is_an_error():
    args = agent.parse_args(["--endpoint", "http://x", "--tags", "{not json"])

    with pytest.raises(agent.AgentError, match="--tags"):
        agent.build_tags(args, env={})
