from dataclasses import dataclass, field
from typing import Dict, List, Optional
import logging
import sys


logger = logging.getLogger("framework")


@dataclass
class CheckResult:
    name: str
    status: str  # OK / WARN / FAIL / ERROR
    details: List[str] = field(default_factory=list)


class BaseCheck:
    name = "base"

    def __init__(self, ctx=None):
        self.ctx = ctx
        self.logger = logging.getLogger(self.__class__.__name__)

    def run(self) -> CheckResult:
        raise NotImplementedError


def run_selected_checks(all_checks: Dict[str, BaseCheck], selected_name: Optional[str] = None):
    if selected_name:
        check = all_checks.get(selected_name)

        if not check:
            print(f"Unknown check: {selected_name}")
            sys.exit(1)

        checks_to_run = [check]
    else:
        checks_to_run = list(all_checks.values())

    results = []

    for check in checks_to_run:
        try:
            result = check.run()
            results.append(result)

            logger.info("Check %s: %s", result.name, result.status)
            for msg in result.details:
                logger.info("  %s", msg)

        except Exception as e:
            logger.exception("Check %s crashed", check.__class__.__name__)
            results.append(
                CheckResult(
                    name=check.__class__.__name__,
                    status="ERROR",
                    details=[f"Check crashed: {e}"],
                )
            )

    return results


def print_summary(results: List[CheckResult]):
    counters = {"OK": 0, "WARN": 0, "FAIL": 0, "ERROR": 0}

    print("=== CHECK RESULTS ===")

    for result in results:
        counters[result.status] = counters.get(result.status, 0) + 1

        print(f"[{result.status:<5}] {result.name}")
        for detail in result.details:
            print(f"        - {detail}")

    print("\n=== SUMMARY ===")
    for status, count in counters.items():
        print(f"{status}: {count}")


def run_selected_exports(all_exports, selected: Optional[str] = None):
    if selected:
        exporter = all_exports.get(selected)

        if not exporter:
            print(f"Unknown export: {selected}")
            sys.exit(1)

        exporters_to_run = [exporter]
    else:
        exporters_to_run = list(all_exports.values())

    failed = []

    for exporter in exporters_to_run:
        try:
            exporter.collect()
            logger.info(
                "Export %s finished",
                exporter.__class__.__name__,
            )

        except Exception as exc:
            name = exporter.__class__.__name__

            logger.exception(
                "Export %s crashed",
                name,
            )

            failed.append(
                f"{name}: {exc}"
            )

    if failed:
        logger.error(
            "%d exporter(s) failed",
            len(failed),
        )

        for error in failed:
            logger.error("  %s", error)

    return failed