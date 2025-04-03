install-lib:
	# Update package list once at the beginning
	apt-get update

	# Install all required packages in one command
	apt-get install -y \
		libgl1-mesa-glx \
		libgl1 \
		build-essential


install-pdm:
	pdm install .


install-miniconda:
	# Update package list once at the beginning
	sudo apt-get update

	# Install all required packages in one command
	sudo apt-get install -y \
		build-essential \
		libgl1 \
		ffmpeg

	wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh

	# Make installation script executable and run it
	chmod +x Miniconda3-latest-Linux-x86_64.sh
	./Miniconda3-latest-Linux-x86_64.sh

	# Update shell
	source ~/.bashrc


install-docker:
	# Update package list once at the beginning
	sudo apt-get update

	# Install all required packages in one command
	sudo apt-get install -y \
		apt-transport-https \
		ca-certificates \
		curl \
		software-properties-common

	# Update apt package index
	sudo apt-get update -y

	# Install required packages
	sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common

	# Add Docker's official GPG key
	curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

	# Set stable repository
	echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

	# Update package index
	sudo apt-get update -y

	# Install Docker engine
	sudo apt-get install -y docker-ce docker-ce-cli containerd.io

	# Start and enable Docker service
	sudo systemctl start docker
	sudo systemctl enable docker

	# Check Docker status
	sudo systemctl status docker --no-pager

	# Print Docker version to verify installation
	docker --version

	# Install latest version of Docker Compose
	DOCKER_COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep -oP '"tag_name": "\K(.*)(?=")')
	sudo curl -L "https://github.com/docker/compose/releases/download/$DOCKER_COMPOSE_VERSION/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
	sudo chmod +x /usr/local/bin/docker-compose

	# Check Docker Compose version
	docker-compose --version

	# Run test Docker container
	sudo docker run hello-world

	echo "Docker and Docker Compose installed. If you need to run Docker without sudo, please run: sudo usermod -aG docker \$USER"


start:
	pdm run python app.py


commit:
	git add .
	git commit -m "update"
	git push


