这份总结包含了你需要的所有关键信息。你可以把它保存下来，下次开启新对话时，直接发给我（或者其他 AI），我们就能立刻接手工作，而不需要从头排查。

-----

### 📁 项目状态快照 (Project Summary)

  * **当前状态**：全栈 Next.js + Prisma + SQLite 应用已成功部署在 Azure 服务器上。
  * **服务器 IP**：`20.193.248.140` (HTTP 端口 80 已开放)。
  * **部署方式**：Docker 容器 (`znnnnh2/todolist:latest`)。
  * **数据存储**：
      * 使用了 **外部挂载 (Volume Mapping)**。
      * 数据位置（服务器）：`/home/azureuser/my-todo-data`。
      * 重要文件：`dev.db` (数据库) 和 `schema.prisma` (手动上传的模型文件)。
  * **特殊配置**：
      * **SSH 连接**：必须使用代理 (`ProxyCommand`) 才能连接。
      * **Prisma 版本**：项目锁定 v6.19.0，必须避免使用 v7+ 版本命令。
      * **架构**：在 `schema.prisma` 中添加了 `linux-musl-openssl-3.0.x` 以兼容 Docker 环境。

-----

### 🔄 场景一：我更新了代码，如何升级？

如果你修改了前端样式或后端逻辑（但不涉及数据库结构变更），请按以下步骤操作：

**1. 本地电脑操作：**

```powershell
# 重新构建并推送到云端 (确保不使用缓存)
docker buildx build --platform linux/amd64 -t znnnnh2/todolist:latest . --push
```

**2. 服务器操作 (SSH 登录后)：**

```bash
# 1. 拉取最新镜像
sudo docker pull znnnnh2/todolist:latest

# 2. 删除旧容器 (放心，数据在文件夹里，删容器不会丢数据)
sudo docker rm -f my-todo-app

# 3. 启动新容器 (使用刚才验证过的完美命令)
sudo docker run -d \
  --name my-todo-app \
  --restart always \
  -p 80:3000 \
  -v /home/azureuser/my-todo-data:/app/prisma \
  -e DATABASE_URL="file:/app/prisma/dev.db" \
  znnnnh2/todolist:latest
```

*只需这三步，网站就更新了。*

-----

### 🛠️ 场景二：我修改了数据库结构，怎么更新？

如果你在 `schema.prisma` 里加了新字段（例如加了 `priority`），步骤稍微多一点：

**1. 本地电脑操作：**

  * 先在本地 `package.json` 所在目录运行 `npx prisma migrate dev` 确保本地没问题。
  * 按照“场景一”的步骤构建并推送镜像。
  * **关键步骤**：把本地最新的 `prisma/schema.prisma` 内容复制下来。

**2. 服务器操作：**

  * 更新服务器上的“卡带”文件：
    ```bash
    nano /home/azureuser/my-todo-data/schema.prisma
    # 把新内容粘贴进去，保存退出 (Ctrl+O, Enter, Ctrl+X)
    ```
  * 按照“场景一”的步骤重启容器。
  * **手动同步数据库结构**（因为我们是挂载文件模式）：
    ```bash
    # 注意指定版本 @6.19.0 避免报错
    sudo docker exec my-todo-app npx prisma@6.19.0 db push
    ```

-----

### 🚨 场景三：服务器炸了，我要重新部署 (灾难恢复)

如果有一天你误删了容器，或者换了台新服务器，请按这个“一键复活”流程：

1.  **连接服务器**：

    ```bash
    # Git Bash 中运行 (记得检查 Azure 后台 22 端口是否开放)
    ssh -o "ProxyCommand=connect -S 127.0.0.1:7890 %h %p" -i /c/Users/ZnH2/.ssh/apps_key.pem azureuser@20.193.248.140
    ```

2.  **准备环境 (如果是新机器)**：

    ```bash
    # 安装 Docker
    curl -fsSL https://get.docker.com | sudo bash
    # 创建数据目录并给权限
    mkdir -p /home/azureuser/my-todo-data
    sudo chmod -R 777 /home/azureuser/my-todo-data
    # 记得在这里创建 schema.prisma 文件并填入内容
    ```

3.  **启动服务**：
    *(直接复制上面场景一里的 `docker run` 命令即可)*

4.  **初始化数据库**：

    ```bash
    sudo docker exec my-todo-app npx prisma@6.19.0 db push
    ```

-----

### 💡 避坑指南 (切记！)

1.  **数据安全**：永远不要删除 `/home/azureuser/my-todo-data` 文件夹，否则你的所有待办事项都会消失。
2.  **权限问题**：如果报错 `Error code 14`，闭眼运行 `sudo chmod -R 777 /home/azureuser/my-todo-data`。
3.  **版本问题**：如果报错 `url` 属性不支持，检查命令里是不是漏了 `@6.19.0`。
4.  **网络问题**：如果 SSH 连不上，先去 Azure 看防火墙是不是被改了，或者试试去掉/加上代理命令。