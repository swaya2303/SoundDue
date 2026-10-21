# grpc/server.py
# ==============================================================================
# SoundDue gRPC server — prototype stub
#
# This server delegates all work to the running SoundDue HTTP API via httpx.
# It does NOT duplicate any analysis logic.
#
# Prerequisites
# -------------
# 1. Generate Python stubs from the .proto file:
#      pip install grpcio-tools grpcio
#      python -m grpc_tools.protoc \
#          -I grpc \
#          --python_out=grpc \
#          --grpc_python_out=grpc \
#          grpc/sounddue.proto
#    This creates grpc/sounddue_pb2.py and grpc/sounddue_pb2_grpc.py.
#
# 2. Start the SoundDue HTTP backend:
#      cd backend && uvicorn main:app --port 8000
#
# 3. Run this server:
#      cd grpc && python server.py --http-base http://localhost:8000 --port 50051
#
# ==============================================================================

from __future__ import annotations

import argparse
import sys
import time
from concurrent import futures

import httpx

# Guard: stubs may not exist yet (they are generated from the .proto).
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


# ---------------------------------------------------------------------------
# Servicer implementation
# ---------------------------------------------------------------------------

class RoyaltyReconciliationServicer:
    """Delegates to the SoundDue HTTP API."""

    def __init__(self, http_base: str) -> None:
        self._http = httpx.Client(base_url=http_base, timeout=30.0)

    # ------------------------------------------------------------------
    # rpc AnalyzeRoyaltyRecords
    # ------------------------------------------------------------------
    def AnalyzeRoyaltyRecords(self, request, context):  # noqa: N802
        case_id = request.case_id
        try:
            r = self._http.post(f"/cases/{case_id}/analyze")
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as exc:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"HTTP {exc.response.status_code}: {exc.response.text}")
            return sounddue_pb2.AnalyzeResponse()
        except Exception as exc:  # noqa: BLE001
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details(str(exc))
            return sounddue_pb2.AnalyzeResponse()

        return self._build_response(case_id, data)

    # ------------------------------------------------------------------
    # rpc GetFindings
    # ------------------------------------------------------------------
    def GetFindings(self, request, context):  # noqa: N802
        case_id = request.case_id
        try:
            r = self._http.get(f"/cases/{case_id}/findings")
            r.raise_for_status()
            findings = r.json()
        except httpx.HTTPStatusError as exc:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"HTTP {exc.response.status_code}: {exc.response.text}")
            return sounddue_pb2.AnalyzeResponse()
        except Exception as exc:  # noqa: BLE001
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details(str(exc))
            return sounddue_pb2.AnalyzeResponse()

        data = {
            "finding_count": len(findings),
            "findings_by_type": {},
            "finding_ids": [f["id"] for f in findings],
            "record_count": 0,
            "link_count": 0,
            "findings": findings,
        }
        return self._build_response(case_id, data)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _build_response(self, case_id: int, data: dict) -> "sounddue_pb2.AnalyzeResponse":
        # Fetch full finding list if not embedded
        if "findings" not in data:
            try:
                r = self._http.get(f"/cases/{case_id}/findings")
                r.raise_for_status()
                data["findings"] = r.json()
            except Exception:  # noqa: BLE001
                data["findings"] = []

        summaries = []
        for f in data.get("findings", []):
            summaries.append(
                sounddue_pb2.FindingSummary(
                    id=f.get("id", 0),
                    finding_type=f.get("finding_type", ""),
                    rule_id=f.get("rule_id", ""),
                    rule_version=f.get("rule_version", ""),
                    severity=f.get("severity", ""),
                    summary=f.get("summary", ""),
                    status=f.get("status", ""),
                    uncertainty=f.get("uncertainty", ""),
                    next_step=f.get("next_step", ""),
                )
            )

        return sounddue_pb2.AnalyzeResponse(
            case_id=case_id,
            finding_count=data.get("finding_count", len(summaries)),
            record_count=data.get("record_count", 0),
            link_count=data.get("link_count", 0),
            findings=summaries,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def serve(port: int, http_base: str, workers: int = 4) -> None:
    if not _GRPC_AVAILABLE:
        sys.exit("grpcio is not installed. Run: pip install grpcio")
    if not _STUBS_AVAILABLE:
        sys.exit(
            "gRPC stubs not found. Generate them first:\n"
            "  pip install grpcio-tools\n"
            "  python -m grpc_tools.protoc -I grpc "
            "--python_out=grpc --grpc_python_out=grpc grpc/sounddue.proto"
        )

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=workers))
    sounddue_pb2_grpc.add_RoyaltyReconciliationServicer_to_server(
        RoyaltyReconciliationServicer(http_base), server
    )
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"SoundDue gRPC server listening on port {port}")
    print(f"  Delegating to HTTP API at: {http_base}")
    print("  Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop(grace=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SoundDue gRPC server")
    parser.add_argument("--port", type=int, default=50051, help="gRPC listen port (default: 50051)")
    parser.add_argument("--http-base", default="http://localhost:8000", help="SoundDue HTTP API base URL")
    parser.add_argument("--workers", type=int, default=4, help="Thread pool size")
    args = parser.parse_args()
    serve(port=args.port, http_base=args.http_base, workers=args.workers)
