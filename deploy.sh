#!/bin/bash

set -e

echo "🚀 Starting Status Tracker Deployment..."

if ! command -v docker-compose &> /dev/null && ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

COMPOSE_CMD="docker compose"
if ! docker compose version &> /dev/null; then
    COMPOSE_CMD="docker-compose"
fi

echo "📦 Building containers..."
$COMPOSE_CMD build

echo "🏃 Starting services..."
$COMPOSE_CMD up -d

echo "✅ Deployment complete!"
echo ""
echo "📊 Status:"
$COMPOSE_CMD ps
echo ""
echo "🔗 API available at: http://localhost:8000"
echo "🏥 Health check: http://localhost:8000/health"
echo ""
echo "📝 Useful commands:"
echo "  View logs: $COMPOSE_CMD logs -f"
echo "  Stop: $COMPOSE_CMD down"
echo "  Restart: $COMPOSE_CMD restart"
