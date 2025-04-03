#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/8/17
# @Author  : david
# @Software: MUST
# @File    : media_handler.py


from aiortc.contrib.media import MediaRelay,MediaBlackhole
from rtc_service.controller.video_stream import VideoTransformTrack
from rtc_service.controller.receiver_audio_stream import ReceiverAudioTransformTrack
from rtc_service.controller.sender_audio_stream import SenderAudioTransformTrack
from concurrent.futures import ThreadPoolExecutor
from rtc_service.utils.logger_util import LoggerConfig
from rtc_service.controller.radio_stream import RadioStreamTrack
from rtc_service.controller.data_stream import DataStreamManager



class MediaHandler:
    _instance = None  # Class level instance reference


    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MediaHandler, cls).__new__(cls)
            cls._instance.initialize()
        return cls._instance

    def initialize(self):
        self.relay = MediaRelay()
        self.executor = ThreadPoolExecutor(max_workers=5)
        self.logger = LoggerConfig()
        self.receiver_track = None  # Initialize receiver_track as None


    async def process_agent_response(self, message, channels, remote):
        try:
            data_manager = DataStreamManager(channels, remote)
            response = await data_manager.process_transcription(message)
            return response
        except Exception as e:
            self.logger.log_info(f'Error processing agent response: {e}')
            return 'error'



    def init_receiver_audio_track_sync(self, pc, track, channels, remote):
        self.logger.log_info('=====> receiver track is working')
        try:
            audio_track = ReceiverAudioTransformTrack(self.relay.subscribe(track))
            sender = pc.addTrack(audio_track)
            audio_track.set_sender(sender)
            audio_track.set_pc(pc)
            audio_track.set_channels(channels)
            audio_track.set_remote(remote)
            self.receiver_track = audio_track
        except Exception as e:
            self.logger.log_info(f'Error initializing receiver audio track: {e}')



    async def init_radio_track_async(self, track, channels, remote):
        self.logger.log_info('=====> radio track is working')
        try:
            micTrack = RadioStreamTrack(track, channels, remote)
            blackHole = MediaBlackhole()
            blackHole.addTrack(micTrack)
            await blackHole.start()
        except Exception as e:
            self.logger.log_info(f'Error initializing radio track: {e}')


    def init_sender_audio_track_sync(self, pc, track, params):
        try:
            audio_track = SenderAudioTransformTrack(self.relay.subscribe(track), params['audio_transform'], self)
            pc.addTrack(audio_track)
        except Exception as e:
            self.logger.log_info(f'Error initializing sender audio track: {e}')

    def init_video_track_sync(self, pc, track, params):
        try:
            video_track = VideoTransformTrack(self.relay.subscribe(track), params['video_transform'])
            pc.addTrack(video_track)
        except Exception as e:
            self.logger.log_info(f'Error initializing video track: {e}')


    def play_receiver_audio(self):
        if self.receiver_track is not None:
            self.receiver_track.play_audio()

    def play_receiver_audio_from_path(self,audio_path):
        if self.receiver_track is not None:
            self.receiver_track.play_audio_from_path(audio_path)

