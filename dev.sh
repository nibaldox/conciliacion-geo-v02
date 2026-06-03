#!/bin/bash
# Start both backend and frontend for development

echo "🚀 Starting Conciliación Geotécnica dev environment..."

# Start backend in background
echo "📡 Starting API server on :8000..."
uvicorn api.main:app --reload --port 8000 &
API_PID=$!

# Start frontend
echo "🎨 Starting web app on :5173..."
cd web && npm run dev &
WEB_PID=$!

echo ""
echo "✅ Dev environment running!"
echo "   API:    http://localhost:8000/docs"
echo "   Web:    http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop both servers..."

# Trap Ctrl+C to kill both processes
trap "kill $API_PID $WEB_PID 2>/dev/null; exit" INT TERM
wait
