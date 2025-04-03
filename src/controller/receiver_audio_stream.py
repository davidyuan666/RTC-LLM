import logging
import time
from aiortc import MediaStreamTrack
from src.utils.logger_util import LoggerConfig
import os
from aiortc.contrib.media import MediaPlayer, MediaRecorder, AudioFrame
from pydub import AudioSegment
import asyncio

class ReceiverAudioTransformTrack(MediaStreamTrack):
    """
    An audio stream track that transforms frames from another track.
    """

    kind = "audio"

    def __init__(self, track):
        super().__init__()  # don't forget this!
        self.track = track
        self.logger = LoggerConfig()
        self.pc = None
        self.sender = None
        self.channels = None
        self.remote = None

    def set_sender(self,sender):
        self.sender = sender

    def set_channels(self, channels):
        self.channels = channels

    def set_remote(self,remote):
        self.remote = remote

    def set_pc(self,pc):
        self.pc = pc

    def reset_original_track(self):
        if self.sender:
            self.sender.replaceTrack(self)

    async def recv(self):
        frame = await self.track.recv()
        return frame

    def get_audio_duration(self,file_path):
        try:
            audio = AudioSegment.from_file(file_path)
            return len(audio) / 1000.0  # Convert from milliseconds to seconds
        except Exception as e:
            print(f"Error obtaining duration: {e}")
            return None


    def add_silence_to_wav(self,input_path, output_path, silence_duration=1000*60):  # silence_duration in 60 seconds
        from pydub import AudioSegment
        import os
        try:
            original_audio = AudioSegment.from_mp3(input_path)

            silence = AudioSegment.silent(duration=silence_duration)

            combined_audio = original_audio + silence

            combined_audio.export(output_path, format="wav")
            print(f"Successfully added silence. New file saved at: {output_path}")
        except Exception as e:
            print(f"Error processing audio file: {e}")


    def play_audio(self):
        default_path = os.path.join(os.getcwd(), 'controller', 'init-audio-channel.wav')

        try:
            input_speech_file = os.path.join(os.getcwd(), 'audio_response', 'temp_speech.wav')
            if input_speech_file is None:
                input_speech_file = default_path
            output_speech_file = os.path.join(os.getcwd(), 'audio_response', 'extended_temp_speech.wav')
            self.add_silence_to_wav(input_speech_file, output_speech_file)

            if output_speech_file is not None:

                player = MediaPlayer(output_speech_file)
                new_track = player.audio

                if self.sender:
                    self.logger.log_info(
                        f'=====> current track: {self.sender.track}')

                    if self.sender.track is None:
                        pass
                        # self.sender = self.pc.addTrack(new_track)
                        # self.logger.log_info(
                        #     f'=====> new current track: {self.sender.track}')
                    else:
                        self.sender.replaceTrack(new_track)
                else:
                    self.logger.log_error('No sender available to replace track.')
        except Exception as e:
            self.logger.log_error(f'Failed to play audio : {e}')

    def play_audio_from_path(self,audio_path):
        try:
            output_speech_file = os.path.join(os.getcwd(), 'audio_response', 'extended_temp_speech.wav')
            self.add_silence_to_wav(audio_path, output_speech_file)

            if output_speech_file is not None:

                player = MediaPlayer(output_speech_file)
                new_track = player.audio

                if self.sender:
                    self.logger.log_info(
                        f'=====> current track: {self.sender.track}')

                    if self.sender.track is None:
                        pass
                        # self.sender = self.pc.addTrack(new_track)
                        # self.logger.log_info(
                        #     f'=====> new current track: {self.sender.track}')
                    else:
                        self.logger.log_info(f'开始播放new track:{new_track}')
                        self.sender.replaceTrack(new_track)
                else:
                    self.logger.log_error('No sender available to replace track.')
        except Exception as e:
            self.logger.log_error(f'Failed to play audio : {e}')


    def play_audio_from_data_channel(self,message):
        channel = self.channels[self.remote]
        if channel:
            self.logger.log_info(f'======> 发送: {message}')
            channel.send(message)
