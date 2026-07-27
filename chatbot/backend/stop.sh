#!/bin/bash
# Stop MetaKGP RAG System - Indexer + FastAPI Query Service

set -e

echo "Stopping MetaKGP RAG System"

# Clean up processes by name
echo ""
echo " Stopping services..."

STOPPED=0

# Stop Indexer
INDEXER_PIDS=$(pgrep -f "services/indexing/indexer.py" 2>/dev/null || true)
if [ ! -z "$INDEXER_PIDS" ]; then
    echo " Stopping Indexer (PID: $INDEXER_PIDS)..."
    kill $INDEXER_PIDS 2>/dev/null || true
    sleep 2
    
    # Force kill if still running
    if pgrep -f "services/indexing/indexer.py" > /dev/null 2>&1; then
        echo "   Force killing..."
        pkill -9 -f "services/indexing/indexer.py" 2>/dev/null || true
    fi
    echo " Indexer stopped"
    STOPPED=$((STOPPED + 1))
fi

# Stop FastAPI Server
FastAPI_PIDS=$(pgrep -f "uvicorn.*src.app.main:app" 2>/dev/null || true)
if [ ! -z "$FastAPI_PIDS" ]; then
    echo " Stopping FastAPI Server (PID: $FastAPI_PIDS)..."
    kill $FastAPI_PIDS 2>/dev/null || true
    sleep 2
    
    # Force kill if still running
    if pgrep -f "uvicorn.*src.app.main:app" > /dev/null 2>&1; then
        echo "   Force killing..."
        pkill -9 -f "uvicorn.*src.app.main:app" 2>/dev/null || true
    fi
    echo " FastAPI Server stopped"
    STOPPED=$((STOPPED + 1))
fi

echo ""
if [ $STOPPED -gt 0 ]; then
    echo " Stopped $STOPPED service(s)"
else
    echo "No services were running"
fi