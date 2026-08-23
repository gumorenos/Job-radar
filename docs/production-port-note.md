# Production port note

`127.0.0.1:8000` is reserved by an existing unrelated VPS service. Job Radar production uses `JOB_RADAR_PORT=8010`, with `ops/preflight.sh` required immediately before deploy to ensure the selected loopback port is still conflict-free.
