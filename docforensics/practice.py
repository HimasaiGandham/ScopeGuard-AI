"""Exercise foundation processing contracts using explicitly simulated adapters."""

import argparse
import json
from pathlib import Path

from .manifest import verify_manifest
from .processing import ErrorCode, ProcessingError, Stage, StepFailure, StepOutput, run_pipeline


def practice_run(manifest: Path, scenario: str = "success"):
    if scenario not in ("success", "ocr-failure", "awaiting-review"):
        raise ValueError("unsupported practice scenario")
    case = verify_manifest(manifest)
    failed_id = case.documents[min(1, len(case.documents) - 1)].document_id

    def simulated(request):
        if scenario == "ocr-failure" and request.stage == Stage.OCR and request.document_ids == (failed_id,):
            raise StepFailure(ProcessingError(ErrorCode.TIMEOUT, "Simulated OCR timeout", retryable=True))
        if scenario == "awaiting-review" and request.stage == Stage.REVIEW:
            return StepOutput(awaiting_review=True)
        return StepOutput()

    return run_pipeline(case, {stage: simulated for stage in Stage}, practice_mode=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--scenario", choices=("success", "ocr-failure", "awaiting-review"), default="success")
    parser.add_argument("--json", action="store_true", help="print progress JSON without source contents")
    args = parser.parse_args()
    try:
        run = practice_run(args.manifest, args.scenario)
    except (OSError, ValueError, KeyError, RuntimeError, TypeError) as exc:
        parser.exit(1, f"Practice error: {exc}\n")
    if args.json:
        print(json.dumps(run.summary(), indent=2))
    else:
        print("PRACTICE ONLY: simulated steps; no OCR, alteration detection, or report was generated.")
        print(f"Case {run.case.case_id}; scenario {args.scenario}")
        for step in run.steps:
            detail = step.error.code.value if step.error else (step.reason or "")
            print(f"{step.stage.value:12} {','.join(step.document_ids):28} {step.status.value:10} {detail}")
            for warning in step.warnings:
                print(f"  warning {warning.code.value}: {warning.message}")
        print(f"Audit events: {len(run.case.audit_events)}")


if __name__ == "__main__":
    main()
