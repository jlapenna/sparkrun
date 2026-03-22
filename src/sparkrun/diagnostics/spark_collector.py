"""Spark host diagnostics collector.

Runs ``spark_diagnose.sh`` on remote hosts, parses the key=value output,
and transforms flat results into structured diagnostic records.
"""

from __future__ import annotations

import logging
import time

from sparkrun.diagnostics.ndjson_writer import NDJSONWriter
from sparkrun.orchestration.ssh import run_remote_scripts_parallel
from sparkrun.scripts import read_script
from sparkrun.utils import parse_kv_output

logger = logging.getLogger(__name__)

# Keys grouped by record type for structured output.
_HARDWARE_KEYS = (
    "DIAG_CPU_MODEL", "DIAG_CPU_CORES", "DIAG_CPU_THREADS",
    "DIAG_RAM_TOTAL_KB", "DIAG_RAM_AVAILABLE_KB",
    "DIAG_DISK_ROOT_TOTAL_KB", "DIAG_DISK_ROOT_AVAIL_KB",
    "DIAG_DISK_HOME_TOTAL_KB", "DIAG_DISK_HOME_AVAIL_KB",
    "DIAG_GPU_NAME", "DIAG_GPU_MEMORY_MB", "DIAG_GPU_DRIVER",
    "DIAG_GPU_PSTATE", "DIAG_GPU_TEMP_C", "DIAG_GPU_POWER_W",
    "DIAG_GPU_SERIAL", "DIAG_GPU_UUID",
)

_FIRMWARE_KEYS = (
    "DIAG_OS_NAME", "DIAG_OS_VERSION", "DIAG_OS_PRETTY",
    "DIAG_KERNEL", "DIAG_ARCH",
    "DIAG_BIOS_VERSION", "DIAG_BOARD_NAME", "DIAG_PRODUCT_NAME",
    "DIAG_JETPACK_VERSION", "DIAG_CUDA_VERSION",
)

_DOCKER_KEYS = (
    "DIAG_DOCKER_VERSION", "DIAG_DOCKER_STORAGE", "DIAG_DOCKER_ROOT",
    "DIAG_DOCKER_NVIDIA_RUNTIME", "DIAG_DOCKER_RUNNING", "DIAG_DOCKER_SPARKRUN",
)


def _extract_keys(kv: dict[str, str], keys: tuple[str, ...], strip_prefix: str = "DIAG_") -> dict[str, str]:
    """Extract and rename keys from a flat kv dict."""
    result: dict[str, str] = {}
    for k in keys:
        if k in kv:
            short = k[len(strip_prefix):].lower() if k.startswith(strip_prefix) else k.lower()
            result[short] = kv[k]
    return result


def _extract_network(kv: dict[str, str]) -> dict:
    """Extract indexed network interface records from flat kv output."""
    count = int(kv.get("DIAG_NET_COUNT", "0"))
    interfaces = []
    for i in range(count):
        prefix = "DIAG_NET_%d_" % i
        iface = {}
        for k, v in kv.items():
            if k.startswith(prefix):
                short = k[len(prefix):].lower()
                iface[short] = v
        if iface:
            interfaces.append(iface)

    return {
        "interfaces": interfaces,
        "default_iface": kv.get("DIAG_DEFAULT_IFACE", ""),
        "mgmt_ip": kv.get("DIAG_MGMT_IP", ""),
    }


def collect_spark_diagnostics(
        hosts: list[str],
        ssh_kwargs: dict,
        writer: NDJSONWriter | None = None,
        dry_run: bool = False,
) -> dict[str, dict]:
    """Collect hardware/firmware/network/Docker diagnostics from hosts.

    Runs ``spark_diagnose.sh`` on all hosts in parallel, parses stdout,
    and emits structured records via *writer* (if provided).

    Args:
        hosts: Target hostnames or IPs.
        ssh_kwargs: SSH connection parameters (ssh_user, ssh_key, etc.).
        writer: Optional NDJSONWriter for NDJSON output.
        dry_run: If True, don't actually execute on remote hosts.

    Returns:
        ``{host: parsed_kv_dict}`` for programmatic use.  Failed hosts
        have an empty dict.
    """
    script = read_script("spark_diagnose.sh")
    t0 = time.monotonic()

    results = run_remote_scripts_parallel(
        hosts=hosts,
        script=script,
        timeout=60,
        dry_run=dry_run,
        **ssh_kwargs,
    )

    host_data: dict[str, dict] = {}
    successful = 0
    failed = 0

    for result in results:
        if not result.success:
            failed += 1
            host_data[result.host] = {}
            if writer:
                writer.emit("host_error", {
                    "host": result.host,
                    "error": "Script failed with rc=%d" % result.returncode,
                    "stderr": result.stderr.strip()[:500],
                })
            logger.warning("Diagnostics failed on %s: rc=%d", result.host, result.returncode)
            continue

        kv = parse_kv_output(result.stdout)
        if kv.get("DIAG_COMPLETE") != "1":
            failed += 1
            host_data[result.host] = kv
            if writer:
                writer.emit("host_error", {
                    "host": result.host,
                    "error": "Incomplete diagnostics (missing DIAG_COMPLETE sentinel)",
                    "stderr": result.stderr.strip()[:500],
                })
            continue

        successful += 1
        host_data[result.host] = kv

        if writer:
            hw = _extract_keys(kv, _HARDWARE_KEYS)
            hw["host"] = result.host
            writer.emit("host_hardware", hw)

            fw = _extract_keys(kv, _FIRMWARE_KEYS)
            fw["host"] = result.host
            writer.emit("host_firmware", fw)

            net = _extract_network(kv)
            net["host"] = result.host
            writer.emit("host_network", net)

            docker = _extract_keys(kv, _DOCKER_KEYS)
            docker["host"] = result.host
            writer.emit("host_docker", docker)

    duration = time.monotonic() - t0

    if writer:
        writer.emit("diag_summary", {
            "total_hosts": len(hosts),
            "successful": successful,
            "failed": failed,
            "duration_seconds": round(duration, 2),
        })

    logger.info(
        "Diagnostics: %d/%d hosts OK in %.1fs",
        successful, len(hosts), duration,
    )

    return host_data
