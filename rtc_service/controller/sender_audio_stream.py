from aiortc import MediaStreamTrack
import webrtcvad
from rtc_service.utils.logger_util import LoggerConfig
from rtc_service.utils.vad_util import rewrite_wav,VoiceActivityDetector
import wave
from pathlib import Path
from termcolor import colored
from datetime import datetime
import asyncio
from aiortc.contrib.media import MediaRecorder, AudioFrame
from pydub import AudioSegment
import os
from enum import Enum
from brtc_service.configs.config import VAD_CONFIG
from collections import deque
import numpy as np
import av
import time
from rtc_service.controller.conversation_handler import ConversationHandler

vad_config = VAD_CONFIG['huawei_P20_pro']

class SpeechStatus(Enum):
    RECOGNIZE_SPEECH = 1
    NO_RECOGNIZE_SPEECH = 2
    HOLDING_FRAME = 3


class SenderAudioTransformTrack(MediaStreamTrack):
    """
    An audio stream track that transforms frames from another track.
    """

    kind = "audio"

    def __init__(self, track,transform,media_handler):
        super().__init__()  # don't forget this!
        self.track = track
        self.transform = transform
        self.vad = webrtcvad.Vad(3)  # Set aggressiveness from 0 to 3.
        self.logger = LoggerConfig()
        self.recording = False
        self.recorder = None
        self.frame_buffer = bytearray()

        self.frame_duration = 10  # VAD frame duration in ms
        self.sample_rate = 8000  # Audio sample rate 16000 Hz or 44100 Hz
        self.frame_samples = self.sample_rate * (self.frame_duration / 1000)  # counts of sample frames
        self.frame_size = int(self.frame_samples * 2)  # Size of each audio frame
        self.frames_to_analyze = 100  # Number of frames to analyze at a time
        self.input_audio_file_path = None
        self.input_audio_file_name = None
        self.frames_recorded = 0

        self.is_slient = True

        self.ensure_audio_temp_directory()

        self.no_recog_speech_counter = 0  # Add this line
        self.recog_speech_counter = 0  # Add this line

        self.frame_queue = deque()

        self.conversation_handler = ConversationHandler()

        self.media_handler = media_handler

   
        # 使用 'spleeter:2stems' 预训练模型，它将音频分离成 'vocals'（人声）和 'accompaniment'（伴奏）
        # self.separator = Separator('spleeter:2stems')

        from faster_whisper import WhisperModel

        model_size = "large-v3"
        # model_size = "large-v1"
        # model_size = 'medium'

        # Run on GPU with FP16
        # model = WhisperModel(model_size, device="cuda", compute_type="float16")
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")

        


    def ensure_audio_temp_directory(self):
        audio_temp_dir = "audio_temp"
        if not os.path.exists(audio_temp_dir):
            os.makedirs(audio_temp_dir, exist_ok=True)

    async def process_audio_frame_without_vad(self, frame):
        """
        Process an audio frame.

        Args:
            frame (AudioFrame): The audio frame to process.

        Returns:
            None
        """
        self.frame_buffer.extend(frame.to_ndarray().tobytes())

        # Start recording immediately
        await self.start_recording()
            
        # Increment the count of frames recorded
        self.frames_recorded += 1
        # self.logger.log_info(f'frame record... {self.frames_recorded}')

        # Stop recording after 10 seconds worth of frames
        if self.frames_recorded >= self.sample_rate * 50 / self.frame_size:
            await self.stop_recording()
            self.frames_recorded = 0  # Reset the frames recorded count

    async def recv(self):
        frame = await self.track.recv()

        if self.transform == "echo":
            pass
        elif self.transform == "reverse":
            pass
        else:
            if isinstance(frame, AudioFrame):
                await self.process_audio_frame(frame)

        return frame


    async def process_audio_frame(self, frame):
        """
        Process an audio frame.

        Args:
            frame (AudioFrame): The audio frame to process.

        Returns:
            None
        """
        speech_status = self.analyze_speech_in_frame(frame)
        if speech_status == SpeechStatus.RECOGNIZE_SPEECH:
            self.no_recog_speech_counter = 0  # Reset the no_recog_speech_counter
            self.recog_speech_counter += 1  # Increment the recog_speech_counter
            if self.recog_speech_counter >= vad_config['SPEECH_START_COUNT']:  # Check the recog_speech_counter
                await self.start_recording()
        elif speech_status == SpeechStatus.NO_RECOGNIZE_SPEECH:
            self.no_recog_speech_counter += 1  # Increment the no_recog_speech_counter
            self.recog_speech_counter = 0  # Reset the recog_speech_counter
            if self.no_recog_speech_counter >= vad_config['SPEECH_STOP_COUNT']:  # Check the no_recog_speech_counter
                await self.stop_recording()
        elif speech_status == SpeechStatus.HOLDING_FRAME:
            pass  # do nothing and wait for more frames


    def analyze_speech_in_frame(self, frame):
        self.frame_buffer.extend(frame.to_ndarray().tobytes())
        while len(self.frame_buffer) >= self.frame_size * self.frames_to_analyze:
            frame_size_duration = len(self.frame_buffer[:self.frame_size * self.frames_to_analyze]) / (
                        self.sample_rate * 2)
            speech_frames = sum(self.vad.is_speech(self.frame_buffer[i:i + self.frame_size], self.sample_rate) for i in
                                range(0, self.frame_size * self.frames_to_analyze, self.frame_size))
            speech_ratio = speech_frames / self.frames_to_analyze
            # self.logger.log_info(
            #     f'Analyzed transcribe frame buffer: Length = {len(self.frame_buffer[:self.frame_size * self.frames_to_analyze])}, Analyzed Last duration = {frame_size_duration} seconds, Speech frames ratio = {speech_ratio}')
            self.frame_buffer = self.frame_buffer[self.frame_size * self.frames_to_analyze:]
            if speech_ratio > vad_config['SPEECH_RATIO_THRESHOLD']:
                return SpeechStatus.RECOGNIZE_SPEECH
            else:
                return SpeechStatus.NO_RECOGNIZE_SPEECH
        return SpeechStatus.HOLDING_FRAME



    '''
    pip install spleeter
    https://github.com/nomadkaraoke/python-audio-separator
    pip install "audio-separator[cpu]"
    pip install noisereduce
    '''
    def extract_human_speech(self,input_raw_audio):
        # 使用 separator.separate 方法分离音频
        audio_descriptor = input_raw_audio
        self.separator.separate_to_file(audio_descriptor, 'separator_output')


    async def start_recording(self):
        if not self.recording:
            self.recording = True
            current_time = datetime.now().strftime("%Y%m%d%H%M%S")
            self.input_audio_file_path = os.path.join("audio_temp", f"temp_speech_record_{current_time}.wav")
            self.input_audio_file_name = os.path.basename(self.input_audio_file_path)
            self.recorder = MediaRecorder(self.input_audio_file_path)
            self.recorder.addTrack(self.track)
            await self.recorder.start()
            self.logger.log_info(f'******* Starting new recording: {self.input_audio_file_name} *******')

    async def stop_recording(self):
        if self.recording:
            self.recording = False
            await self.recorder.stop()
            self.logger.log_info(f'****** Stopping recording {self.input_audio_file_name}. *******')
            if self.input_audio_file_path:
                record_status = await self.check_record_duration(self.input_audio_file_path)
                if not record_status["status"]:
                    self.logger.log_info('delete short duration wav')
                    os.remove(self.input_audio_file_path)
                    if self.media_handler:
                        self.media_handler.play_receiver_audio_from_path(os.path.join(os.getcwd(),'controller',
                                                                                      '../audios', 'default_response_speech.wav'))
                else:
                    self.logger.log_info(f'save {self.input_audio_file_name}')
                    # self.extract_human_speech(self.input_audio_file_path)
                    chat_response = await self.transcribe_and_process(self.input_audio_file_path)
                    self.input_audio_file_path = None
                    speech_file_path = await self.text_to_speech_by_openai(chat_response)
                    if self.media_handler and speech_file_path:
                        self.media_handler.play_receiver_audio()

    

    async def transcribe_and_process(self, audio_file_path):
        """
        Transcribe the audio file and process the resulting text.

        Args:
            audio_file_path (str): The path to the audio file to transcribe.

        Returns:
            None
        """
        start_time = time.time()
        chat_response = None

        record_status = await self.check_record_duration(audio_file_path)
        if record_status["status"]:
            # transcribe_speech_text = self.speech_to_text_by_google(audio_file_path) # speech_to_text_by_fast_whisper
            transcribe_speech_text = self.speech_to_text_by_fast_whisper(audio_file_path)  # speech_to_text_by_fast_whisper
            self.logger.log_info(f'==============> stt: {transcribe_speech_text}')
            # if transcribe_speech_text is None or len(transcribe_speech_text.strip()) <1:
                # transcribe_speech_text = await self.speech_to_text_by_openai(audio_file_path)
                # self.logger.log_info(f'==============> transcribe: {transcribe_speech_text}')

            # if transcribe_speech_text and len(transcribe_speech_text)>5:
            #     try:
            #         chat_response = self.conversation_handler.chat(transcribe_speech_text)
            #         self.logger.log_info(f'===> start send chat response message to data channel : {chat_response} <===')
            #     except Exception as e:
            #         self.logger.log_error(f"Error processing transcribed text: {e}")
            # else:
            #     self.logger.log_info("No transcribed text available to process.")

        else:
            self.logger.log_info(record_status["message"])
            return None

        end_time = time.time()
        elapsed_time = end_time - start_time
        self.logger.log_info(f"Transcription and processing took {elapsed_time} seconds")
        return chat_response


    async def check_record_duration(self, file_path):
        path = Path(file_path)
        if path.exists():
            with wave.open(file_path, 'rb') as audio:
                frames = audio.getnframes()
                rate = audio.getframerate()
                duration = frames / float(rate)
                self.logger.log_info(colored(f"File {file_path} duration is {duration} seconds", 'green'))

            if duration < vad_config['RECORD_DURATION']:
                return {"status": False, "message": "Record duration is too short."}
            else:
                return {"status": True, "message": "Record duration is valid."}
        else:
            return {"status": False, "message": "File path does not exist."}



    async def speech_to_text_by_openai(self,file_path):
        path = Path(file_path)
        if path.exists():
            speech_text = await async_speech_to_text(file_path)
            self.logger.log_info(colored(f'=====>Transcribed text: {speech_text}', 'yellow'))
            return speech_text
        else:
            self.logger.log_info(f"File {file_path} does not exist.")
            return None


    def speech_to_text_by_google(self,file_path):
        from pyasr import ASR
        asr = ASR()
        path = Path(file_path)
        if path.exists():
            speech_text = asr.recognize_audio(file_path)
            self.logger.log_info(colored(f'=====>Transcribed text by google: {speech_text}', 'yellow'))
            return speech_text
        else:
            self.logger.log_info(f"File {file_path} does not exist.")
            return None
    

    def speech_to_text_by_fast_whisper(self, file_path):
        # segments, info = self.model.transcribe(file_path, beam_size=5, language="zh", condition_on_previous_text=False)
        segments, info = self.model.transcribe(file_path, beam_size=5)
        self.logger.log_info("Detected language '%s' with probability %f" % (info.language, info.language_probability))

        result_string = ""
        for segment in segments:
            self.logger.log_info("[%.2fs -> %.2fs] %s" % (segment.start, segment.end, segment.text))
            result_string += "%s, " % segment.text  # Only append the text of each segment

        return result_string



    async def text_to_speech_by_openai(self, text):
        if text is None or len(text) < 10:
            return None
        try:
            speech_file_path = await async_text_to_speech(text)
            self.logger.log_info(colored(f'tts output path: {speech_file_path}', 'yellow'))
            return speech_file_path
        except Exception as e:
            self.logger.log_info(colored(f'An error occurred in text_to_speech: {e}', 'yellow'))
            return None


