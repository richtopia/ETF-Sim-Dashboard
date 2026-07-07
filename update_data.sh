#!/bin/bash
# Navigate to the simulator directory on the Asustor NAS
cd /volume1/Docker/ETF_Simulator

# Run Python inside a temporary container to execute the data update scripts
docker run --rm \
  -v /volume1/Docker/ETF_Simulator:/app \
  -w /app \
  python:3.10-slim \
  sh -c "pip install --no-cache-dir -r requirements.txt && python generate_risk_kpi.py && python run_backtest.py"
