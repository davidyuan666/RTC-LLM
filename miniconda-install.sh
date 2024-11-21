#!/bin/bash

#sudo passwd root
#ssh-keygen -t rsa -b 4096 -C "wu.xiguanghua2014@gmail.com"

# 下载 Miniconda 安装脚本
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh

# 使安装脚本可执行
chmod +x Miniconda3-latest-Linux-x86_64.sh

# 运行安装脚本
./Miniconda3-latest-Linux-x86_64.sh

# 更新 shell
source ~/.bashrc

# 安装gcc
sudo apt update
sudo apt install build-essential

# 安装图形库
sudo apt update
sudo apt install libgl1

# 安装ffmpeg
sudo apt update
sudo apt install ffmpeg
