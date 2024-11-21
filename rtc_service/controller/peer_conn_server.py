# -*- coding = utf-8 -*-
# @time:2024/8/20 13:44
# Author:david yuan
# @File:peer_conn_server.py

'''
参考用的
https://stackoverflow.com/questions/77787620/quality-problems-in-aiortc-communication
'''
from PyQt5 import QtCore, QtGui, QtWidgets
from calls import Ui_Dialog
from aiohttp import web
from aiortc.mediastreams import MediaStreamTrack
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder, MediaRelay
from pydub import AudioSegment
import av
import pyaudio
import asyncio
import json
import os
from multiprocessing import Process, Queue, Pipe, freeze_support
from queue import Queue as Av_Queue
import sys
import threading
from time import sleep
import fractions
import time

from PyQt5.QtCore import pyqtSignal, QThread, Qt
from datetime import datetime, timedelta
from pydub import AudioSegment, effects, utils, generators
from pydub.utils import which

AudioSegment.converter = which("ffmpeg")

from pydub.playback import play
from io import BytesIO


class Run_me:
    def __init__(self):
        self.app = QtWidgets.QApplication(sys.argv)
        self.Dialog = QtWidgets.QDialog()
        self.ui = Ui_Dialog()
        self.ui.setupUi(self.Dialog)

        self.server_child_process = Server()
        self.server_child_process.start()

        self.Dialog.show()

        self.ui.label.hide()
        self.ui.pushButton.hide()
        self.ui.pushButton_2.hide()
        self.ui.pushButton_3.hide()

        self.Dialog.closeEvent = lambda event: self.closeEvent(event)

        sys.exit(self.app.exec_())

    def microphone_slice_ready(self, slice):
        packet = av.Packet(slice.raw_data)
        frame = self.codec.decode(packet)[0]
        frame.pts = self.audio_samples
        frame.time_base = fractions.Fraction(1, self.codec.sample_rate)
        self.audio_samples += frame.samples
        q.put(frame)

    def closeEvent(self, event):
        event.accept()


class CustomRadioStream(MediaStreamTrack):
    kind = "audio"

    def __init__(self):
        super().__init__()  # don't forget this!

        self.q = Av_Queue()
        self._start = None

    async def recv(self):
        frame = self.q.get()
        return frame


class Server(Process):
    def __init__(self):
        super().__init__()
        self.ROOT = os.path.dirname(__file__)
        self.pcs = []
        self.channels = []
        self.stream_offer = None

    def run(self):
        self.app = web.Application()
        self.app.on_shutdown.append(self.on_shutdown)
        self.app.router.add_get("/", self.index)
        self.app.router.add_get("/telephone_calls.js", self.javascript)
        self.app.router.add_post("/offer", self.offer)
        threading.Thread(target=self.fill_the_queues).start()
        web.run_app(self.app, access_log=None, host="192.168.1.188", port=8080, ssl_context=None)

    def fill_the_queues(self):
        self.sample_rate = 44800
        self.AUDIO_PTIME = 0.744
        self.samples = int(self.AUDIO_PTIME * self.sample_rate)
        self.packet_time = 20

        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 2
        self.RATE = self.sample_rate
        self.CHUNK = int(44100 * 0.744)

        # self.file_segment = AudioSegment.from_file(r"ΑΓΙΑ ΚΥΡΙΑΚΗ.mp3").set_frame_rate(self.sample_rate)
        # self.duration_milliseconds = len(self.file_segment)
        # self.chunk_number = 0

        self.silence = AudioSegment.silent(duration=self.packet_time)

        self.codec = av.CodecContext.create('pcm_s16le', 'r')
        self.codec.sample_rate = 8000
        self.codec.channels = 2

        self.audio_samples = 0

        self.p = pyaudio.PyAudio()
        self.input_stream = self.p.open(format=pyaudio.paInt16, channels=2, rate=8000, input=True,
                                        frames_per_buffer=int(8000 * 0.020))
        self.input_stream.start_stream()

        while (True):
            in_data = self.input_stream.read(int(8000 * 0.020), exception_on_overflow=False)
            slice = AudioSegment(in_data, sample_width=2, frame_rate=8000, channels=2)
            # slice = AudioSegment.from_mono_audiosegments(slice, slice)
            # slice = slice.set_frame_rate(44800)

            packet = av.Packet(slice.raw_data)
            frame = self.codec.decode(packet)[0]
            frame.pts = self.audio_samples
            frame.time_base = fractions.Fraction(1, self.codec.sample_rate)
            self.audio_samples += frame.samples
            if self.stream_offer is not None:
                self.stream_offer.q.put(frame)

    async def index(self, request):
        content = open(os.path.join(self.ROOT, "index.html"), encoding="utf8").read()
        return web.Response(content_type="text/html", text=content)

    async def javascript(self, request):
        content = open(os.path.join(self.ROOT, "telephone_calls.js"), encoding="utf8").read()
        return web.Response(content_type="application/javascript", text=content)

    async def offer(self, request):
        params = await request.json()
        offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
        name = params["name"]
        surname = params["surname"]
        # print(name+" "+surname)
        pc = RTCPeerConnection()
        self.pcs.append(pc)

        # prepare epalxeis media
        self.stream_offer = CustomRadioStream()
        pc.addTrack(self.stream_offer)

        @pc.on("datachannel")
        def on_datachannel(channel):
            self.channels.append(channel)
            self.send_channel_message(str(len(self.pcs)))

        @pc.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange():
            if pc.iceConnectionState == "failed":
                self.pcs.remove(pc)
                print("Current peer connections:" + str(len(self.pcs)))

        @pc.on("track")
        async def on_track(track):
            micTrack = ClientTrack(track)
            blackHole = MediaBlackhole()
            blackHole.addTrack(micTrack)
            await blackHole.start()

        # handle offer
        await pc.setRemoteDescription(offer)

        # send answer
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        return web.Response(content_type="application/json",
                            text=json.dumps({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}))

    async def on_shutdown(self, app):
        # close peer connections
        if self.pcs:
            coros = [pc.close() for pc in self.pcs]
            await asyncio.gather(*coros)
            self.pcs = []
            self.channels = []
            self.stream_offers = []

    def send_channel_message(self, message):
        for channel in self.channels:
            channel.send(message)


class ClientTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self, track):
        super().__init__()
        self.track = track
        self.p = pyaudio.PyAudio()
        self.output_stream = self.p.open(format=pyaudio.paInt16, channels=2, rate=44800, output=True,
                                         frames_per_buffer=int(16384 / 4))
        self.output_stream.start_stream()


    async def recv(self):
        # Get a new PyAV frame
        frame = await self.track.recv()

        packet_bytes = frame.to_ndarray().tobytes()
        self.output_stream.write(packet_bytes)


if __name__ == "__main__":
    if os.path.exists("ip_call_1.mp3"):
        os.remove("ip_call_1.mp3")
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        freeze_support()
    program = Run_me()