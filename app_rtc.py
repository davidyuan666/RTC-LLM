# -*- coding = utf-8 -*-
# @time:2024/8/13 15:24
# Author:david yuan
# @File:video_app.py


import os
import argparse
import aiohttp_cors
from aiohttp import web
from rtc_service.controller.peer_connection_manager import PeerConnectionManager
import logging
import os
import argparse
import aiohttp_cors
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription
import json
import logging
import asyncio

class WebRTCServer:
    def __init__(self):
        self.ROOT = os.path.dirname(__file__)
        self.app = web.Application()
        self.cors = aiohttp_cors.setup(self.app)
        self.connection_manager = PeerConnectionManager()
        self.app.on_shutdown.append(self.on_shutdown)
        self.app.router.add_get("/", self.index)
        self.app.router.add_get("/client.js", self.javascript)
        self.app.router.add_post("/receiver/offer", self.receiver_offer)
        self.app.router.add_post("/sender/offer", self.sender_offer)
        self.app.router.add_post("/video/offer", self.video_offer)
        self.app.router.add_post("/whole/offer", self.offer)
        self.app.router.add_post("/offer", self.data_offer)


        for route in list(self.app.router.routes()):
            self.cors.add(route, {
                "*": aiohttp_cors.ResourceOptions(
                    allow_credentials=True,
                    expose_headers="*",
                    allow_headers="*",
                    allow_methods="*"
                )
            })


    async def index(self, request):
        content = open(os.path.join(self.ROOT, "static/index.html"), "r").read()
        return web.Response(content_type="text/html", text=content)

    async def javascript(self, request):
        content = open(os.path.join(self.ROOT, "static/client.js"), "r").read()
        return web.Response(content_type="application/javascript", text=content)

    async def receiver_offer(self, request):
        return await self.connection_manager.offer(request, "receiver")

    async def sender_offer(self, request):
        return await self.connection_manager.offer(request, "sender")

    async def video_offer(self, request):
        return await self.connection_manager.offer(request, "video")
    
    async def offer(self, request):
        return await self.connection_manager.offer(request, "whole")
    
    async def data_offer(self, request):
        return await self.connection_manager.offer(request, "data")
    
    
    async def on_shutdown(self):
        await self.connection_manager.on_shutdown()




    def run(self):
        parser = argparse.ArgumentParser(
            description="WebRTC audio / video / data-channels demo"
        )
        parser.add_argument("--cert-file", help="SSL certificate file (for HTTPS)")
        parser.add_argument("--key-file", help="SSL key file (for HTTPS)")
        parser.add_argument(
            "--host", default="0.0.0.0", help="Host for HTTP rtc_backend (default: 0.0.0.0)"
        )
        parser.add_argument(
            "--port", type=int, default=8080, help="Port for HTTP rtc_backend (default: 8080)"
        )
        parser.add_argument("--record-to", help="Write received media to a file."),
        parser.add_argument("--verbose", "-v", action="count")
        args = parser.parse_args()

        if args.verbose:
            logging.basicConfig(level=logging.DEBUG)
        else:
            logging.basicConfig(level=logging.INFO)

        ssl_context = None

        web.run_app(
            self.app, access_log=None, host=args.host, port=args.port, ssl_context=ssl_context
        )


if __name__ == '__main__':
    server = WebRTCServer()
    server.run()
