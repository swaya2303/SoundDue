# SoundDue gRPC — Stub & Server Setup

## 1. Generate Python stubs

```bash
pip install grpcio grpcio-tools

# Run from the project root:
python -m grpc_tools.protoc \
    -I grpc \
    --python_out=grpc \
    --grpc_python_out=grpc \
    grpc/sounddue.proto
```

This creates:
- `grpc/sounddue_pb2.py`
- `grpc/sounddue_pb2_grpc.py`

## 2. Start the HTTP backend

```bash
cd backend
uvicorn main:app --port 8000
```

## 3. Start the gRPC server

```bash
cd grpc
python server.py --http-base http://localhost:8000 --port 50051
```

## 4. Run the client

```bash
# Analyze case 1 and show findings:
python grpc/client.py --case-id 1 --action analyze

# Get findings without re-running analysis:
python grpc/client.py --case-id 1 --action findings

# JSON output:
python grpc/client.py --case-id 1 --action analyze --json
```

## Notes

- The server delegates to the HTTP API — no analysis logic is duplicated.
- SingularityNET daemon / testnet publishing is a **documented next step**, not implemented.
  See `docs/integration-status.md` for the full status.
- Omega AGI integration is a plan-only item — see `docs/omega-plan.md`.
