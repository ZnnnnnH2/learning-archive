#!/bin/bash
set -e

# 配置变量 - 请修改为你的实际配置
IMAGE_NAME="znnnnh2/todolist"
SERVER_USER="root"
SERVER_IP="20.193.248.140"
REMOTE_DIR="/opt/todolist"

echo "📦 Building Docker image..."
docker build -t $IMAGE_NAME:latest .

echo "🚀 Pushing to Docker Registry..."
docker push $IMAGE_NAME:latest

echo "🔄 Deploying to server..."
ssh $SERVER_USER@$SERVER_IP << EOF
  cd $REMOTE_DIR
  docker-compose pull
  docker-compose down
  docker-compose up -d
  docker-compose exec -T web npx prisma migrate deploy
  echo "✅ Deployment complete!"
EOF

echo "🎉 Done!"