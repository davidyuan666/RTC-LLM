# Use an official Ubuntu runtime as a parent image
FROM ubuntu:22.04

# Set the working directory in the container to /app
WORKDIR /app

# Add the current directory contents into the container at /app
COPY aiortc_services/server_end /app/aiortc_services/server_end
COPY vagents /app/vagents
COPY knowledgebase /app/knowledgebase
COPY requirements.txt /app/requirements.txt
COPY app_rtc.py /app/app_rtc.py

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive

# Install sqlite3
RUN apt-get update && apt-get install -y sqlite3

# Install Python, pip, gcc, libgl1-mesa-glx, libglib2.0-0, ffmpeg, pkg-config, libhdf5-dev, cmake and other dependencies
RUN apt-get install -y \
    python3.10 \
    python3-pip \
    gcc \
    libgl1-mesa-glx \
    libglib2.0-0 \
    ffmpeg \
    pkg-config \
    libhdf5-dev \
    cmake

# Update pip
RUN python3 -m pip install --upgrade pip

# Install any needed packages specified in requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# Make port 8080 available to the world outside this container
EXPOSE 8080

# Run webrtc_app.py when the container launches
CMD ["python3", "app_rtc.py"]
