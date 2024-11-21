# -*- coding = utf-8 -*-
# @time:2024/8/13 14:58
# Author:david yuan
# @File:peer_connection_manager.py


from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription,RTCRtpSender
import asyncio
import json
from rtc_service.utils.logger_util import LoggerConfig
from rtc_service.controller.media_handler import MediaHandler
from rtc_service.controller.radio_stream import RadioStreamTrack


class PeerConnectionManager:
    def __init__(self):
        self.pcs = set()
        self.logger = LoggerConfig()
        self.media_handler = MediaHandler()  # Singleton instance
        self.channels = {}  # 新增的channels字典





    '''
    close peer connections
    '''
    async def on_shutdown(self):
        coros = [pc.close() for pc in self.pcs]
        await asyncio.gather(*coros)
        self.pcs.clear()

    async def offer(self, request, connection_type):
        params = await request.json()
        offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
        pc = RTCPeerConnection()
        self.pcs.add(pc)

        self.logger.log_info("Created %s connection for %s", connection_type, request.remote)

        @pc.on("datachannel")
        def on_datachannel(channel):
            # @channel.on("message")
            # def on_message(message):
            #     self.logger.log_info(f'====>{connection_type} received message from flutter: {message}')
            #     response = self.media_handler.process_reply_by_agent(message,self.channels,request.remote)
            #     channel.send(f'{response}')
            #     self.channels[request.remote] = channel  # 将channel对象存储到channels字典中

            @channel.on("message")
            async def on_message(message):
                self.logger.log_info(f'┌─────────────────────────────────────────────────────────────────────────┐')
                self.logger.log_info(f'│ {connection_type}: {message}')
                self.logger.log_info(f'│')
                self.channels[request.remote] = channel  # Store the channel object in the channels dictionary
                await self.media_handler.process_agent_response(message, self.channels, request.remote)
                self.logger.log_info(f'│')
                self.logger.log_info(f'└─────────────────────────────────────────────────────────────────────────┘')

            @channel.on("open")
            def on_open():
                self.logger.log_info('===> Client Data channel is open')

            @channel.on("close")
            def on_close():
                self.logger.log_info('===> Data channel is closed')

            @channel.on("error")
            def on_error(error):
                self.logger.log_info('====> Data channel error: %s' % error)



        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            if connection_type == "sender":
                self.logger.log_info("===> Sender connection state is %s", pc.connectionState)
            if connection_type == "receiver":
                self.logger.log_info("===> Receiver connection state is %s", pc.connectionState)
            if connection_type == "video":
                self.logger.log_info("===> Video connection state is %s", pc.connectionState)
            if connection_type == "whole":
                self.logger.log_info("===> whole connection state is %s", pc.connectionState)
            if connection_type == "data":
                self.logger.log_info("===> data connection state is %s", pc.connectionState)

            if pc.connectionState == "failed":
                await pc.close()
                self.pcs.discard(pc)
                self.pcs.remove(pc)
                self.logger.log_info("Current peer connections:" + str(len(self.pcs)))


        @pc.on("track")
        async def on_track(track):
            self.logger.log_info("===================>Async Track %s received", track.kind)
            if track.kind == "audio":
                if connection_type == 'sender':
                    await self.media_handler.init_radio_track_async(track,self.channels,request.remote)
 

            @track.on("ended")
            async def on_ended():
                self.logger.log_info("Async Track %s ended", track.kind)


        @pc.on("track")
        def on_track(track):
            self.logger.log_info("===================>Sync Track %s received", track.kind)
            if track.kind == "audio":
                if connection_type == 'receiver':
                    self.media_handler.init_receiver_audio_track_sync(pc,track,self.channels,request.remote)

            if track.kind == "video":
                if connection_type == 'video' or connection_type == 'whole' or connection_type == 'sender':
                    self.media_handler.init_video_track_sync(pc, track, params)

            @track.on("ended")
            def on_ended():
                self.logger.log_info("Sync Track %s ended", track.kind)



        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        return web.Response(
            content_type="application/json",
            text=json.dumps({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})
        )

