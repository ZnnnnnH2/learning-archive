git add .
git commit -m "Add drag-and-drop sorting feature"
git push origin main
# 2. 构建 Docker 镜像
docker build -t todolist:latest .
# 3. 标记镜像 (替换为你的 Docker Registry 地址)
# 如果使用 Docker Hub:
docker tag todolist:latest znnnnh2/todolist:latest
# 如果使用私有 Registry:
# docker tag todolist:latest your-registry.com/todolist:latest
# 4. 推送镜像到 Registry
docker push znnnnh2/todolist:latest

ssh -i "c:\Users\ZnH2\.ssh\apps_key.pem" azureuser@20.193.248.140
# 6. 拉取最新镜像
docker pull znnnnh2/todolist:latest
# 7. 停止并删除旧容器
docker-compose down
# 8. 启动新容器
docker-compose up -d
# 9. 运行数据库迁移 (如果需要)
docker-compose exec web npx prisma migrate deploy
# 10. 查看日志
docker-compose logs -f web