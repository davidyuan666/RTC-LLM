# RTC-LLM

A prototype WebRTC service for real-time LLM (Large Language Model) communication.

## Description

This project implements a WebRTC-based service that enables real-time communication with Large Language Models. It provides low-latency, peer-to-peer connections for efficient AI model interactions, supporting both audio and video streaming capabilities.

## Features

- Real-time communication using WebRTC
- Integration with LLM services
- Low-latency responses
- Peer-to-peer architecture
- Audio and video streaming support
- Speech recognition using Whisper
- Noise reduction and audio processing
- Multi-language support with Jieba for Chinese text processing

## Getting Started

### Prerequisites

- Python 3.10 or higher
- Modern web browser with WebRTC support
- Required Python packages (installed via pip):
  - aiortc: WebRTC implementation
  - aiohttp: Async HTTP server
  - whisper: Speech recognition
  - torch: Deep learning framework
  - Additional audio processing libraries

### Installation

1. Clone the repository
2. Install dependencies:
```bash
pip install .
```

### Running the Server

Start the server with:
```bash
python app.py
```

By default, the server runs on `http://0.0.0.0:8080`. You can customize the host and port using command line arguments:
```bash
python app.py --host <HOST> --port <PORT>
```

## Development

For development, install additional dependencies:
```bash
pip install ".[dev]"
```

This includes:
- pytest for testing
- black for code formatting
- flake8 for linting

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

[MIT]

## Author

David Yuan (wu.xiguanghua2014@gmail.com)