"""Tests for runtime version detection and metadata persistence."""

from unittest import mock

from sparkrun.core.recipe import Recipe
from sparkrun.orchestration.job_metadata import save_job_metadata, load_job_metadata
from sparkrun.orchestration.ssh import RemoteResult
from sparkrun.runtimes.base import RuntimePlugin
from sparkrun.runtimes.vllm_ray import VllmRayRuntime
from sparkrun.runtimes.vllm_distributed import VllmDistributedRuntime
from sparkrun.runtimes.sglang import SglangRuntime
from sparkrun.runtimes.llama_cpp import LlamaCppRuntime
from sparkrun.runtimes.trtllm import TrtllmRuntime


# --- version_commands() tests ---

class TestVersionCommands:
    """Test version_commands() returns expected keys for base and subclasses."""

    def test_base_has_common_keys(self):
        cmds = RuntimePlugin.version_commands(RuntimePlugin())
        assert "cuda" in cmds
        assert "python" in cmds
        assert "torch" in cmds
        assert "nccl" in cmds

    def test_vllm_ray_has_vllm_key(self):
        cmds = VllmRayRuntime().version_commands()
        assert "vllm" in cmds
        assert "cuda" in cmds

    def test_vllm_distributed_has_vllm_key(self):
        cmds = VllmDistributedRuntime().version_commands()
        assert "vllm" in cmds
        assert "cuda" in cmds

    def test_sglang_has_sglang_key(self):
        cmds = SglangRuntime().version_commands()
        assert "sglang" in cmds
        assert "cuda" in cmds

    def test_llama_cpp_has_llama_cpp_key(self):
        cmds = LlamaCppRuntime().version_commands()
        assert "llama_cpp" in cmds
        assert "cuda" in cmds

    def test_trtllm_has_trtllm_key(self):
        cmds = TrtllmRuntime().version_commands()
        assert "trtllm" in cmds
        assert "cuda" in cmds


# --- _collect_runtime_info() tests ---

class TestCollectRuntimeInfo:
    """Test _collect_runtime_info parses output and handles failures."""

    def test_parses_key_value_output(self):
        stdout = (
            "SPARKRUN_VER_CUDA=12.9\n"
            "SPARKRUN_VER_PYTHON=3.12.3\n"
            "SPARKRUN_VER_TORCH=2.7.0\n"
            "SPARKRUN_VER_VLLM=0.8.5\n"
        )
        fake_result = RemoteResult(
            host="host1", stdout=stdout, stderr="", returncode=0,
        )

        runtime = VllmRayRuntime()
        with mock.patch("sparkrun.orchestration.primitives.run_script_on_host", return_value=fake_result):
            info = runtime._collect_runtime_info("host1", "container1", {}, dry_run=False)

        assert info == {
            "cuda": "12.9",
            "python": "3.12.3",
            "torch": "2.7.0",
            "vllm": "0.8.5",
        }

    def test_skips_unknown_values(self):
        stdout = (
            "SPARKRUN_VER_CUDA=12.9\n"
            "SPARKRUN_VER_TORCH=unknown\n"
        )
        fake_result = RemoteResult(
            host="host1", stdout=stdout, stderr="", returncode=0,
        )

        runtime = VllmRayRuntime()
        with mock.patch("sparkrun.orchestration.primitives.run_script_on_host", return_value=fake_result):
            info = runtime._collect_runtime_info("host1", "container1", {}, dry_run=False)

        assert info == {"cuda": "12.9"}
        assert "torch" not in info

    def test_returns_empty_on_failure(self):
        fake_result = RemoteResult(
            host="host1", stdout="", stderr="error", returncode=1,
        )

        runtime = VllmRayRuntime()
        with mock.patch("sparkrun.orchestration.primitives.run_script_on_host", return_value=fake_result):
            info = runtime._collect_runtime_info("host1", "container1", {}, dry_run=False)

        assert info == {}

    def test_returns_empty_on_exception(self):
        runtime = VllmRayRuntime()
        with mock.patch("sparkrun.orchestration.primitives.run_script_on_host", side_effect=RuntimeError("boom")):
            info = runtime._collect_runtime_info("host1", "container1", {}, dry_run=False)

        assert info == {}

    def test_returns_empty_on_dry_run(self):
        runtime = VllmRayRuntime()
        info = runtime._collect_runtime_info("host1", "container1", {}, dry_run=True)
        assert info == {}

    def test_handles_empty_lines_and_noise(self):
        stdout = (
            "some noise before\n"
            "SPARKRUN_VER_CUDA=12.9\n"
            "\n"
            "SPARKRUN_VER_PYTHON=\n"
            "more noise\n"
            "SPARKRUN_VER_SGLANG=0.4.6.post1\n"
        )
        fake_result = RemoteResult(
            host="host1", stdout=stdout, stderr="", returncode=0,
        )

        runtime = SglangRuntime()
        with mock.patch("sparkrun.orchestration.primitives.run_script_on_host", return_value=fake_result):
            info = runtime._collect_runtime_info("host1", "container1", {}, dry_run=False)

        assert info == {"cuda": "12.9", "sglang": "0.4.6.post1"}
        assert "python" not in info  # empty value skipped


# --- job_metadata runtime_info persistence tests ---

class TestJobMetadataRuntimeInfo:
    """Test save/load of runtime_info in job metadata."""

    def _make_recipe(self):
        return Recipe.from_dict({
            "name": "test", "runtime": "vllm", "model": "test/model",
        })

    def test_save_and_load_with_runtime_info(self, tmp_path):
        recipe = self._make_recipe()
        runtime_info = {"vllm": "0.8.5", "cuda": "12.9", "torch": "2.7.0"}

        save_job_metadata(
            "sparkrun_abc123",
            recipe,
            ["host1"],
            cache_dir=str(tmp_path),
            runtime_info=runtime_info,
        )

        meta = load_job_metadata("sparkrun_abc123", cache_dir=str(tmp_path))
        assert meta is not None
        assert meta["runtime_info"] == runtime_info

    def test_save_without_runtime_info(self, tmp_path):
        recipe = self._make_recipe()

        save_job_metadata(
            "sparkrun_def456",
            recipe,
            ["host1"],
            cache_dir=str(tmp_path),
        )

        meta = load_job_metadata("sparkrun_def456", cache_dir=str(tmp_path))
        assert meta is not None
        assert "runtime_info" not in meta

    def test_save_with_empty_runtime_info(self, tmp_path):
        recipe = self._make_recipe()

        save_job_metadata(
            "sparkrun_ghi789",
            recipe,
            ["host1"],
            cache_dir=str(tmp_path),
            runtime_info={},
        )

        meta = load_job_metadata("sparkrun_ghi789", cache_dir=str(tmp_path))
        assert meta is not None
        assert "runtime_info" not in meta  # empty dict not persisted
