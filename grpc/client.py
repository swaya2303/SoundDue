# grpc/client.py
# ==============================================================================
# SoundDue gRPC client — prototype stub
#
# Calls the local gRPC server to analyze a case or fetch its findings.
#
# Prerequisites (same as server.py):
#   pip install grpcio grpcio-tools
#   python -m grpc_tools.protoc \
#       -I grpc \
#       --python_out=grpc \
#       --grpc_python_out=grpc \
#       grpc/sounddue.proto
#
# Usage:
#   # Analyze case 1
#   python grpc/client.py --case-id 1 --action analyze
#
#   # Fetch existing findings for case 1
#   python grpc/client.py --case-id 1 --action findings
#
#   # Custom host
#   python grpc/client.py --case-id 2 --host localhost:50051 --action analyze
# ==============================================================================

from __future__ import annotations

import argparse
import json
import sys

# Guard: stubs may not exist yet.
try:
    import sounddue_pb2          # type: ignore[import]
    import sounddue_pb2_grpc     # type: ignore[import]
    _STUBS_AVAILABLE = True
except ImportError:
    _STUBS_AVAILABLE = False

try:
    import grpc
    _GRPC_AVAILABLE = True
except ImportError:
    _GRPC_AVAILABLE = False


def _check_deps() -> None:
    if not _GRPC_AVAILABLE:
        sys.exit("grpcio is not installed. Run: pip install grpcio")
    if not _STUBS_AVAILABLE:
        sys.exit(
            "gRPC stubs not found. Generate them first:\n"
            "  pip install grpcio-tools\n"
            "  python -m grpc_tools.protoc -I grpc "
            "--python_out=grpc --grpc_python_out=grpc grpc/sounddue.proto"
        )


def _print_response(resp: "sounddue_pb2.AnalyzeResponse") -> None:
    print(f"\nCase ID      : {resp.case_id}")
    print(f"Findings     : {resp.finding_count}")
    print(f"Records      : {resp.record_count}")
    print(f"Links        : {resp.link_count}")

    if not resp.findings:
        print("\n  (no findings)")
        return

    print("\nFindings:")
    print("-" * 72)
    for f in resp.findings:
        sev_icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(f.severity, "⚪")
        print(f"  [{f.id}] {sev_icon} {f.severity.upper():7s} | {f.rule_id} v{f.rule_version}")
        print(f"          {f.summary}")
        if f.status != "open":
            print(f"          Status: {f.status}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SoundDue gRPC client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python grpc/client.py --case-id 1 --action analyze
  python grpc/client.py --case-id 1 --action findings
  python grpc/client.py --case-id 2 --host myserver:50051 --action analyze
        """,
    )
    parser.add_argument("--case-id", type=int, required=True, help="SoundDue case ID")
    parser.add_argument("--host", default="localhost:50051", help="gRPC server host:port (default: localhost:50051)")
    parser.add_argument(
        "--action",
        choices=["analyze", "findings"],
        default="analyze",
        help="analyze = POST analyze + return findings; findings = GET only (default: analyze)",
    )
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of formatted output")
    args = parser.parse_args()

    _check_deps()

    channel = grpc.insecure_channel(args.host)
    stub = sounddue_pb2_grpc.RoyaltyReconciliationStub(channel)

    try:
        if args.action == "analyze":
            print(f"→ Calling AnalyzeRoyaltyRecords(case_id={args.case_id}) on {args.host} …")
            resp = stub.AnalyzeRoyaltyRecords(sounddue_pb2.AnalyzeRequest(case_id=args.case_id))
        else:
            print(f"→ Calling GetFindings(case_id={args.case_id}) on {args.host} …")
            resp = stub.GetFindings(sounddue_pb2.GetFindingsRequest(case_id=args.case_id))
    except grpc.RpcError as exc:
        print(f"\n❌  gRPC error: {exc.code()} — {exc.details()}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        # Emit a plain dict (proto → dict manually for portability)
        output = {
            "case_id": resp.case_id,
            "finding_count": resp.finding_count,
            "record_count": resp.record_count,
            "link_count": resp.link_count,
            "findings": [
                {
                    "id": f.id,
                    "finding_type": f.finding_type,
                    "rule_id": f.rule_id,
                    "rule_version": f.rule_version,
                    "severity": f.severity,
                    "summary": f.summary,
                    "status": f.status,
                    "uncertainty": f.uncertainty,
                    "next_step": f.next_step,
                }
                for f in resp.findings
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        _print_response(resp)


if __name__ == "__main__":
    main()
