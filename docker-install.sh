#!/bin/bash

# 脚本运行前请用root权限执行：sudo chmod +x install_docker.sh && sudo ./install_docker.sh

# 更新apt包索引
sudo apt-get update -y

# 安装apt所需要的包
sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common

# 添加Docker的官方GPG密钥
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# 设置stable存储库
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 更新包索引
sudo apt-get update -y

# 安装Docker引擎
sudo apt-get install -y docker-ce docker-ce-cli containerd.io

# 启动并启用Docker服务
sudo systemctl start docker
sudo systemctl enable docker

# 检查Docker状态
sudo systemctl status docker --no-pager

# 打印Docker版本以验证安装
docker --version

# 安装最新版本的 Docker Compose
DOCKER_COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep -oP '"tag_name": "\K(.*)(?=")')
sudo curl -L "https://github.com/docker/compose/releases/download/$DOCKER_COMPOSE_VERSION/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 检查 Docker Compose 版本
docker-compose --version

# 运行测试Docker容器
sudo docker run hello-world

echo "Docker 和 Docker Compose 安装完成。如果需要免sudo运行Docker，请运行：sudo usermod -aG docker \$USER"