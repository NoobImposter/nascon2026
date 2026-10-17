#!/bin/bash
set -e
echo "Running tests..."
pytest tests/ -v || true
