# -*- coding = utf-8 -*-
# @time:2024/8/20 13:41
# Author:david yuan
# @File:radio_stream.py


import wave
import os
from aiortc import MediaStreamTrack
from rtc_service.utils.logger_util import LoggerConfig
import time
from enum import Enum
from rtc_service.configs.config import VAD_CONFIG
from aiortc.contrib.media import AudioFrame
import webrtcvad
from datetime import datetime,timedelta
from pathlib import Path
from termcolor import colored
from collections import deque
import asyncio
from concurrent.futures import ThreadPoolExecutor
import uuid
from vagents.vagentic.transcribe.speech import Speech
import requests
import aiohttp
import json
from tqdm import tqdm  # 导入 tqdm
import jieba
from backend_services.http_backend.controller.mq_handler import MQHandler
from backend_services.http_backend.api.handler_factory import Factory
import time
import whisper
from pathlib import Path
from colorama import init, Fore, Style
init(autoreset=True)
from rtc_service.controller.record_session import RecordingSession
from rtc_service.controller.audio_process import AudioProcessor

'''
only pass audio to the router_handler
'''
class RadioStreamTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self, track,channels,remote):
        super().__init__()
        self.track = track
        # self.media_handler = media_handler
        self.channels = channels
        self.remote = remote

        self.logger = LoggerConfig()

        # Initialize directories and temporary paths
        self.ensure_audio_temp_directory()
        self.temp_listen_dir = os.path.join(os.getcwd(), 'temp_listen')

        # Configure VAD and audio settings
        self.vad = webrtcvad.Vad(3)  # Set aggressiveness level (0-3)
        self.sample_rate = 8000  # Audio sample rate
        self.frame_duration = 10  # VAD frame duration in ms
        self.frame_samples = int(self.sample_rate * (self.frame_duration / 1000))
        self.frame_size = self.frame_samples * 2  # Size in bytes
        self.frames_to_analyze = 100


        # Initialize recording state and buffers
        self.recording = False
        self.record_flag = False
        self.wav_file = None
        self.frame_buffer = bytearray()

        # Configure transcribe detection queue
        self.window_size = 10
        self.speech_queue = deque(maxlen=self.window_size)

        # Initialize asyncio settings
        self.loop = asyncio.get_event_loop()
        self.executor = ThreadPoolExecutor()

        # Speech-to-Text and Text-to-Speech services
        self.speech = Speech()

        # Load VAD configurations
        self.vad_config = VAD_CONFIG['huawei_P20_pro']
        if not self.vad_config['OPENAI_WHISPER']:
            self.model_size = 'medium'
            self.device = 'cpu'
            # self.init_model()

        # Conditional handlers based on configuration
        if not self.vad_config['ENABLE_HTTP_AGENT']:
            from backend_services.http_backend.controller.router_handler import RouterHandler
            from backend_services.http_backend.controller.interrupt_handler import InterruptHandler
            self.router_handler = RouterHandler()
            self.interrupt_handler = InterruptHandler()


        self.mq_handler = Factory.get_instance(MQHandler)  # Get the singleton instance
        self.estimated_time = 0
        self.last_response_time = 0
        self.valid_audio = True
        self.current_recording_session = None
        self.record_start_time = 0 

        # 创建异步队列
        self.audio_task_queue = asyncio.Queue()
        # 启动后台任务处理音频队列
        asyncio.create_task(self.process_audio_queue())



    def send_data_channel(self,message):
        channel = self.channels[self.remote]
        if channel:
            channel.send(message)


    def ensure_audio_temp_directory(self):
        """
         Ensure that the temporary directory for storing audio files exists.
         If it does not exist, create it.
         """
        temp_listen_dir = "temp_listen"
        if not os.path.exists(temp_listen_dir):
            os.makedirs(temp_listen_dir, exist_ok=True)

    
    def save_listen_audio(self, listen_audio_path):
        """Initialize a WAV file for saving audio data."""
        try:
            wav_file = wave.open(listen_audio_path, "wb")
            wav_file.setnchannels(2)  # 1 代表单声道
            wav_file.setsampwidth(2)  # 2 字节（16 位）样本宽度
            wav_file.setframerate(44100)  # 使用 self.sample_rate 确保采样率一致
            return wav_file
        except Exception as e:
            self.logger.log_info(f"\033[1;31m[错误] 无法创建音频文件: {e}\033[0m")
            return None

     

    def update_queue(self, speech_ratio):
        self.speech_queue.append(speech_ratio)

    def calculate_ratios(self):
        if len(self.speech_queue) > 0:
            queue_ratio = sum(self.speech_queue) / len(self.speech_queue)
        else:
            queue_ratio = 0

        return queue_ratio

    async def recv(self):
        frame = await self.track.recv()

        if isinstance(frame, AudioFrame):
            await self.analyze_frame(frame)

        return frame

    
    async def analyze_frame(self, frame):
        """
        Process audio frames to detect transcribe and handle recording based on voice activity.
        """
        frame_bytes = frame.to_ndarray(format="s16le").tobytes()  # 转换音频帧为 16 位小端序字节
        self.frame_buffer.extend(frame_bytes)
        
        # 确保在录音标志开启并且 wav_file 存在时写入音频数据
        if self.record_flag and self.current_recording_session and self.current_recording_session.wav_file:
            self.current_recording_session.wav_file.writeframes(frame_bytes)

        await self.process_buffer()


    async def process_buffer(self):
        """
        Continuously process the buffer to detect transcribe and manage recording states.
        """
        while len(self.frame_buffer) >= self.frame_size * self.frames_to_analyze:
            await self.process_frame_segment()



    async def process_frame_segment(self):
        """
        Analyze a segment of frames for transcribe activity and adjust recording accordingly.
        """
        segment = self.frame_buffer[:self.frame_size * self.frames_to_analyze]
        frame_size_duration = len(segment) / (self.sample_rate * 2)
        speech_frames = sum(
            self.vad.is_speech(segment[i:i + self.frame_size], self.sample_rate)
            for i in range(0, len(segment), self.frame_size)
        )
        speech_ratio = speech_frames / self.frames_to_analyze

        # Update buffer and queues
        self.frame_buffer = self.frame_buffer[len(segment):]
        self.update_queue(speech_ratio)

        # Log analysis and check recording triggers
        await self.log_and_trigger_recording(speech_ratio, frame_size_duration)



    async def log_and_trigger_recording(self, speech_ratio, frame_size_duration):
        """
        Log frame analysis results and handle recording state based on VAD ratios.
        """
        queue_ratio = self.calculate_ratios()
        
        # 使用 tqdm 显示进度条
        with tqdm(total=10, bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]') as pbar:
            for _ in range(10):  # 假设有 10 个步骤
                arrows = '\033[92m' + '↑' * (int(speech_ratio * 10) if speech_ratio > 0 else 1) + '\033[0m'
                log_message = (
                    f'{arrows} Analyzed transcribe frame buffer: Length = {frame_size_duration * self.sample_rate * 2}, '
                    f'Last duration = {frame_size_duration:.2f} seconds, '
                    f'Speech frames ratio = {speech_ratio:.2f} '
                    f'| \033[94m Queue transcribe ratio = {queue_ratio:.2f}\033[0m'
                )
                pbar.set_description(log_message)  # 更新进度条描述
                pbar.update(1)  # 更新进度条



        await self.check_recording_state(queue_ratio)


    def interrupt_by_speech_threald(self,queue_ratio):
        '''
        一旦监听到说话就立即打断
        '''
        if  self.vad_config['ENABLE_DIRECTLY_INTERRUPT']:
            if queue_ratio > self.vad_config['QUEUE_RATIO_INTERRUPT_THRESHOLD'] and not self.record_flag:
                self.logger.log_info(colored('===> send directly interrupt signal', 'yellow'))
                self.send_data_channel("interrupt")

    

    def begin_audio_capture(self):
        """Start audio recording and initialize necessary paths."""
        # 生成新的 session_id（使用当前的时间戳）
        session_id = datetime.now().strftime("%Y%m%d%H%M%S")
        # 使用 session_id 作为文件名
        temp_listen_path = os.path.join(self.temp_listen_dir, f"{session_id}.wav")
        # 开始录音，返回 wav_file 对象
        wav_file = self.save_listen_audio(temp_listen_path)
        self.logger.log_info(f'START recording: {temp_listen_path}')
        # 创建新的 RecordingSession 对象
        recording_session = RecordingSession(session_id, temp_listen_path, wav_file)
        return recording_session


    def end_audio_capture(self, recording_session):
        """Stop audio recording, release resources, and ensure the audio file is valid."""
        
        if recording_session.wav_file:
            recording_session.wav_file.close()  # 关闭文件句柄
            self.logger.log_info(f'STOP recording: {recording_session.temp_listen_path}')
            
            # 检查音频文件是否成功生成且大小大于 0
            if os.path.exists(recording_session.temp_listen_path):
                file_size = os.path.getsize(recording_session.temp_listen_path)
                if file_size > 0:
                    self.logger.log_info(f"\033[1;32m[成功] 音频文件生成成功，大小为 {file_size} 字节。\033[0m")
                    return True  # 文件成功生成
                else:
                    self.logger.log_info("\033[1;31m[错误] 音频文件生成失败，文件大小为 0。\033[0m")
                    return False  # 文件生成失败
            else:
                self.logger.log_info("\033[1;31m[错误] 音频文件未找到。\033[0m")
                return False  # 文件不存在
        else:
            self.logger.log_info()


    async def check_for_interruption(self, transcribed_text):
        """
        Check if the transcribed text requires an interruption.
        
        Args:
            transcribed_text (str): The transcribed text to analyze.
        
        Returns:
            dict: A dictionary containing 'should_interrupt' flag.
        """
        url = self.vad_config['INTERRUPT_URL']
        payload = {"text": transcribed_text}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        self.logger.log_info(f"[是否需要打断?]Received interrupt response: {response_data}")
                        should_interrupt = False
                        if isinstance(response_data, dict) and 'message' in response_data:
                            # The 'message' value is expected to be a boolean string
                            should_interrupt = response_data['message'].lower() == 'true'
                            is_noise = response_data['message'].lower() == 'noise'
                        else:
                            # If the response is not in the expected format, assume no interruption
                            should_interrupt = False
                            is_noise = False
                        
                        return {'should_interrupt': should_interrupt, 'is_noise': is_noise}
                    else:
                        self.logger.log_info(f"Unexpected status code: {response.status}")
                        return {'should_interrupt': False, 'is_noise': False}
        except Exception as e:
            self.logger.log_info(f"Error checking for interruption: {e}")
            return {'should_interrupt': False, 'is_noise': False}
    

    def calculate_tokens_count(self,transcribed_text):
        try:
            if len(transcribed_text.strip()) > 0:  # 先去除空格
                    # 计算字数
                if any('\u4e00' <= char <= '\u9fff' for char in transcribed_text):  # 检查是否包含中文字符
                    word_count = len(jieba.lcut(transcribed_text))  # 中文分词
                else:
                    word_count = len(transcribed_text.split())  # 英文分词
                return word_count
        except Exception as e:
            self.logger.log_info(f"Error calculating tokens count: {e}")
            return 0



    async def check_recording_state(self, queue_ratio):
        """
        Start or stop recording based on detected transcribe ratios.
        """
        current_time = time.time()  # 获取当前时间

             # 如果当前未在录音状态且达到了启动录音的队列阈值
        if not self.record_flag and queue_ratio > self.vad_config['QUEUE_RATIO_START_THRESHOLD']:
            '''
            始终开始录制音频，以监测打断
            '''
            # 开始新的录音会话
            self.current_recording_session = self.begin_audio_capture()
            self.record_flag = True
            self.record_start_time = current_time  # 记录录音开始时间


        # 如果录音已经开启，并且一致处于阈值上，那么就检查录音时间
        elif self.record_flag and queue_ratio > self.vad_config['QUEUE_RATIO_STOP_THRESHOLD']:
            delta_time = current_time - self.record_start_time
            # 如果录音时间超过了最大允许时间，强制结束录音并重新开始
            if delta_time > self.vad_config['MAX_RECORD_DURATION']:
                self.logger.log_info(f"\033[1;33m[警告] 录音时间超过 {self.vad_config['MAX_RECORD_DURATION']} 秒，强制重新开始录音。\033[0m")
                # 结束当前录音
                if self.end_audio_capture(self.current_recording_session):
                    self.logger.log_info("\033[1;34m[状态] 停止录制，准备处理录制的音频。\033[0m")
                    await self.analyze_recorded_audio_by_queue(
                        is_stream=self.vad_config["ENABLE_STREAM_TTS"],
                        recording_session=self.current_recording_session
                    )
                else:
                    self.logger.log_info("\033[1;31m[错误] 音频文件生成失败，跳过音频处理。\033[0m")

                # 重置录音状态
                self.record_flag = False
                self.current_recording_session = None
            
            # 如果录音时间没有超过最大时长，则继续录音
            return

        # 检查队列比例以决定是否结束录音
        elif self.record_flag and queue_ratio < self.vad_config['QUEUE_RATIO_STOP_THRESHOLD']:
            # 结束录音，并检查音频文件是否成功生成
            if self.end_audio_capture(self.current_recording_session):
                self.logger.log_info("\033[1;34m[状态] 停止录制，准备处理录制的音频。\033[0m")
                # 在调用 analyze_recorded_audio 时，传递当前的 recording_session

                # 检查当前时间是否在预估的等待时间内
                if current_time < self.last_response_time + self.estimated_time:
                    self.current_recording_session.valid_audio = False
                    self.logger.log_info("\033[1;33m[提示] 当前上一个语音输出处于工作状态，当前新录制音频将被标记为无效。\033[0m")
                else:
                    self.current_recording_session.valid_audio = True
                    self.logger.log_info("\033[1;32m[信息] 当前录制的音频被认为有效。\033[0m")


                await self.analyze_recorded_audio_by_queue(
                    is_stream=self.vad_config["ENABLE_STREAM_TTS"],
                    recording_session=self.current_recording_session
                )
            else:
                self.logger.log_info("\033[1;31m[错误] 音频文件生成失败，跳过音频处理。\033[0m")

            # 重置录音状态
            self.record_flag = False
            self.current_recording_session = None  # 重置当前录音会话




    async def analyze_recorded_audio_directly(self, is_stream=False, recording_session=None):
        """Process recorded audio by checking its duration and potentially transcribing it."""
        if not recording_session or not recording_session.temp_listen_path:
            self.logger.log_info("\033[1;31m[警告] 没有可用的录音会话或临时音频文件路径。\033[0m")
            return

        try:
            record_status = await self.calculate_audio_duration(recording_session.temp_listen_path)
            if not record_status["status"]:
                self.logger.log_info("\033[1;31m[删除] 不在范围内音频文件，已删除。\033[0m")
                os.remove(recording_session.temp_listen_path)
            else:
                self.logger.log_info(f"\033[1;32m[保存] {recording_session.temp_listen_path}\033[0m")
                transcribed_text = await self.transcribe_audio(recording_session.temp_listen_path)
                
                '''
                一旦监听到打断内容就立即打断，并停止后续处理
                '''
                if transcribed_text and any(phrase in transcribed_text for phrase in ['stop', '停止', '闭嘴', '好的，可以了', '好的，我知道了']):
                    self.logger.log_info("\033[1;33m[打断] 检测到打断指令，发送打断信号。\033[0m")
                    self.send_data_channel("interrupt")

                    # 重置 last_response_time 和 estimated_time，以避免干扰后续的音频处理
                    self.last_response_time = 0
                    self.estimated_time = 0

                    # 清理当前正在进行的录音会话，防止其干扰后续处理
                    if self.current_recording_session:
                        self.logger.log_info("\033[1;34m[状态] 重置当前录音会话，清除未完成的录音。\033[0m")
                        self.end_audio_capture(self.current_recording_session)  # 结束当前录音
                        self.current_recording_session = None  # 清空当前会话
                        self.record_flag = False  # 重置录音标志

                    return


                # 如果 transcribed_text 存在，并且 token 数 > 5，并且 valid_audio 为 True，才进行后续处理
                if transcribed_text and self.calculate_tokens_count(transcribed_text) > 5 and recording_session.valid_audio:
                    self.logger.log_info("\033[1;33m=======> 进入业务处理流程。\033[0m")
                    await self.process_speech_response(transcribed_text, is_stream=is_stream)
                elif not recording_session.valid_audio:
                    self.logger.log_info("\033[1;31m[提示] 无效音频，跳过处理。\033[0m")
                else:
                    self.logger.log_info("\033[1;31m[提示] 转录文本过短，跳过处理。\033[0m")
                    self.send_data_channel('没听清，请在安静环境下重试')
                    


        except Exception as e:
            self.logger.log_info(f"\033[1;31m[错误] 在 analyze_recorded_audio 中发生错误：{str(e)}\033[0m")
        finally:
            # 确保删除临时音频文件，释放资源
            if os.path.exists(recording_session.temp_listen_path):
                os.remove(recording_session.temp_listen_path)


    '''
    Send audio record to queue
    '''
    async def analyze_recorded_audio_by_queue(self, is_stream=False, recording_session=None):
        """将音频处理任务添加到队列中"""
        # 将任务加入队列
        await self.audio_task_queue.put((recording_session, is_stream))
        self.logger.log_info("\033[1;32m[任务加入队列] 音频处理任务已加入队列。\033[0m")


    '''
    Retrive audio record from queue
    '''
    async def process_audio_queue(self):
        """后台任务，从队列中获取并处理音频任务。"""
        while True:
            recording_session, is_stream = await self.audio_task_queue.get()  # 获取任务
            await self.process_audio_task(recording_session, is_stream)       # 处理任务
            self.audio_task_queue.task_done()  # 标记任务完成

    '''
    Process audio record
    '''
    async def process_audio_task(self, recording_session, is_stream):
        """处理队列中的单个音频任务。"""
        if not recording_session or not recording_session.temp_listen_path:
            self.logger.log_info("\033[1;31m[警告] 没有可用的录音会话或临时音频文件路径。\033[0m")
            return

        try:
            record_status = await self.calculate_audio_duration(recording_session.temp_listen_path)
            if not record_status["status"]:
                self.logger.log_info("\033[1;31m[删除] 不在范围内音频文件，已删除。\033[0m")
                os.remove(recording_session.temp_listen_path)
            else:
                self.logger.log_info(f"\033[1;32m[保存] {recording_session.temp_listen_path}\033[0m")
                transcribed_text = await self.transcribe_audio(recording_session.temp_listen_path)
                
                # 检查是否有打断指令            
                if transcribed_text and any(phrase in transcribed_text for phrase in ['stop', '停止', '闭嘴', '好的，可以了', '好的，我知道了']):
                    self.logger.log_info("\033[1;33m[打断] 检测到打断指令，发送打断信号。\033[0m")
                    self.send_data_channel("interrupt")

                    # 重置 last_response_time 和 estimated_time，以避免干扰后续的音频处理
                    self.last_response_time = 0
                    self.estimated_time = 0

                    # 清理当前正在进行的录音会话，防止其干扰后续处理
                    if self.current_recording_session:
                        self.logger.log_info("\033[1;34m[状态] 重置当前录音会话，清除未完成的录音。\033[0m")
                        self.end_audio_capture(self.current_recording_session)  # 结束当前录音
                        self.current_recording_session = None  # 清空当前会话
                        self.record_flag = False  # 重置录音标志

                    return


                # 如果 transcribed_text 存在，并且 token 数 > 5，并且 valid_audio 为 True，才进行后续处理
                if transcribed_text and self.calculate_tokens_count(transcribed_text) > 5 and recording_session.valid_audio:
                    self.logger.log_info("\033[1;33m=======> 进入业务处理流程。\033[0m")
                    await self.process_speech_response(transcribed_text, is_stream=is_stream)
                elif not recording_session.valid_audio:
                    self.logger.log_info("\033[1;31m[提示] 无效音频，跳过处理。\033[0m")
                else:
                    self.logger.log_info("\033[1;31m[提示] 转录文本过短，跳过处理。\033[0m")

        except Exception as e:
            self.logger.log_info(f"\033[1;31m[错误] 在 analyze_recorded_audio 中发生错误：{str(e)}\033[0m")
        finally:
            # 确保删除临时音频文件，释放资源
            if os.path.exists(recording_session.temp_listen_path):
                os.remove(recording_session.temp_listen_path)




    async def transcribe_audio(self, audio_path):
        """Transcribe audio using either OpenAI's Whisper or a local Whisper implementation."""
        try:
            if self.vad_config['OPENAI_WHISPER']:
                transcribed_text = await self.speech.listen(audio_path)
            else:
                transcribed_text = await self.transcribe_with_local_whisper(audio_path)

            # 进行后处理，纠正常见的误转录
            transcribed_text = self.postprocess_transcription(transcribed_text)

            # 美化日志输出
            self.logger.log_info(f"\033[1;33m[Whisper STT Result]\033[0m {transcribed_text}")
            return transcribed_text

        except Exception as e:
            self.logger.log_info("\033[1;31m[错误] 网络问题，请重试。\033[0m")  # Log network issue
            return None  # Return network issue message



    def postprocess_transcription(self, text):
        # 定义常见的误转录和正确词的映射
        corrections = {
            'thank you': 'stop',
            'tank you': 'stop',
            'stop it': 'stop',
            'thanks': 'stop',
            'thank': 'stop',
            # 添加更多误转录情况
        }

        # 将文本转换为小写，方便匹配
        text_lower = text.lower()
        for wrong, correct in corrections.items():
            if wrong in text_lower:
                text_lower = text_lower.replace(wrong, correct)

        # 如果需要，还可以处理中文的情况
        chinese_corrections = {
            '坦克': '停止',
            '挺住': '停止',
            # 添加更多误转录情况
        }

        for wrong, correct in chinese_corrections.items():
            if wrong in text_lower:
                text_lower = text_lower.replace(wrong, correct)

        return text_lower


    async def transcribe_with_local_whisper(self, audio_path):
        """Transcribe audio using a local Whisper model. Log segment details and aggregate results."""
        try:

            # 如果模型尚未加载，则加载模型
            if not hasattr(self, 'local_whisper_model'):
                self.local_whisper_model = whisper.load_model("base")

            # 指定语言参数，提高准确性
            result = self.local_whisper_model.transcribe(audio_path, language='en', beam_size=5)

            # 获取转录结果和语言信息
            segments = result.get('segments', [])
            detected_language = result.get('language', 'unknown')
            language_probability = result.get('language_probability', 0.0)

            # 美化语言检测日志输出
            language_log = f"\033[1;34m[语言检测]\033[0m 检测到的语言：'{detected_language}'，概率：{language_probability:.2f}"
            self.logger.log_info(language_log)

            # 拼接所有段落的文本
            result_string = ", ".join(segment['text'] for segment in segments)

            # 日志输出每个段落的信息
            for segment in segments:
                segment_log = f"\033[1;33m[转录片段]\033[0m [{segment['start']:.2f}s -> {segment['end']:.2f}s] {segment['text']}"
                self.logger.log_info(segment_log)

            # 进行后处理，纠正常见的误转录
            result_string = self.postprocess_transcription(result_string)

            return result_string.strip(', ')
        except Exception as e:
            self.logger.log_info(f"\033[1;31m[错误] 本地 Whisper 转录时发生错误：{e}\033[0m")
            return None
        

    def estimate_reading_time(self,text, language='zh'):
        """
        根据文本长度和平均阅读速度预估阅读时间。

        参数：
        - text: 要阅读的文本内容。
        - language: 语言类型，'zh' 表示中文，'en' 表示英文。

        返回：
        - estimated_time: 预估的阅读时间（秒）。
        """
        if language == 'zh':
            # 中文平均阅读速度：250 字/分钟
            average_reading_speed = 250
            text_length = len(text.replace(' ', ''))  # 去除空格后的字数
        elif language == 'en':
            # 英文平均阅读速度：200 词/分钟
            average_reading_speed = 200
            text_length = len(text.split())  # 单词数
        else:
            # 默认使用中文
            average_reading_speed = 250
            text_length = len(text.replace(' ', ''))
        
        estimated_time = (text_length / average_reading_speed) * 60  # 转换为秒
        return estimated_time


    async def process_speech_response(self, transcribed_text, is_stream=False):
        if not transcribed_text:
            self.logger.log_info("\033[1;31m[警告] 转录文本为空或太短，无法处理。\033[0m")
            return

        try:
            response_dict, status_code = await self.handle_transcription(transcribed_text)
            chat_response = response_dict.get('message', '')

            # Check for network issues
            if status_code != 200:  # Assuming a non-200 status indicates a network issue
                chat_response = "网络故障，请重试"  # Update chat_response for network issues

            if chat_response:  # Check if chat_response is not empty
                # 预估阅读时间
                self.estimated_time = self.estimate_reading_time(chat_response, language='zh')  # 假设是中文
                self.logger.log_info(f"\033[1;34m[信息] 预估阅读时间：{self.estimated_time:.2f} 秒\033[0m")
                # 在此可以使用 estimated_time 来控制下一轮的开始和停止标志

                if self.vad_config['OPENAI_TTS_ENABLE']:
                    speech_audio_path = await self.speech.speak(chat_response)
                    print(f"\033[1;34m[信息] 发送语音音频路径：\033[0m {speech_audio_path}")
                else:
                    self.logger.log_info(f"\033[1;32m[TTS 消息]\033[0m {chat_response}")
                    self.send_data_channel(chat_response)
                    self.last_response_time = time.time()

            if is_stream:
                await self.process_streamed_responses(transcribed_text)

        except Exception as e:
            self.logger.log_info(f"\033[1;31m[错误] 处理转录文本时出错：\033[0m {e}")



    
    async def handle_transcription(self, text):
        if self.vad_config['ENABLE_HTTP_AGENT']:
            return await self.send_http_request(text)
        else:
            if self.vad_config['ENABLE_MQ']:
                result = await self.mq_handler.send_to_queue(text,routing_key='rtc_query_queue')
                print('send to queue result', result)
            else:
                return await self.router_handler.run_query(text)
            

    # async def receive_transcription(self):
    #     transcription_text = await self.mq_handler.receive_from_queue(routing_key='rtc_query_queue')  # 从队列中获取消息
    #     print(f'receive query from rabbitmq: {transcription_text}')  # 打印或处理响应
    #     response, status_code = await self.r.run_query(user_text)  # 处理查询
    #     print(f'receive response from rabbitmq: {response["message"]}')  # 打印或处理响应



    async def send_http_request(self, text):
        url = self.vad_config['RECIPE_URL']
        payload = {"text": text}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                return await response.json(), None

    async def process_streamed_responses(self, transcribed_text):
        for response_chunk_dict in self.cooking_handler.run(transcribed_text):
            response_chunk_msg = response_chunk_dict.get('message', '')
            if self.vad_config['OPENAI_TTS_ENABLE'] and response_chunk_msg:
                speech_audio_path = await self.speech.speak(response_chunk_msg)
                print('send speech audio path', speech_audio_path)
            elif response_chunk_msg:
                self.logger.log_info(f'TTS chunk message: {response_chunk_msg}')
                self.send_data_channel(response_chunk_msg)

        
    
    async def calculate_audio_duration(self, file_path):
        """Calculate the duration of an audio file in seconds and validate it against minimum and maximum duration thresholds."""
        audio_file = Path(file_path)
        if audio_file.exists():
            try:
                # 异步执行获取音频帧数和采样率
                frames, rate = await asyncio.get_running_loop().run_in_executor(
                    self.executor, self.get_audio_frames_and_rate, file_path)
                
                # 确保 frames 和 rate 都有效
                if frames is None or rate is None or rate == 0:
                    self.logger.log_info("\033[1;31m[错误] 无法计算音频时长，帧数或采样率无效。\033[0m")
                    return {"status": False, "message": "Invalid frames or rate for audio duration calculation."}
                
                # 计算音频时长
                duration = frames / float(rate)
                self.logger.log_info(f"\033[1;33m[音频时长]\033[0m 音频文件时长：{duration:.2f} 秒")

                # 验证音频时长是否在规定范围内
                if duration < self.vad_config['MIN_RECORD_DURATION']:
                    self.logger.log_info("\033[1;31m[警告] 音频时长过短。\033[0m")
                    return {"status": False, "message": "Record duration is too short."}
                elif duration > self.vad_config['MAX_RECORD_DURATION']:
                    self.logger.log_info("\033[1;31m[警告] 音频时长过长。\033[0m")
                    return {"status": False, "message": "Record duration is too long."}
                else:
                    self.logger.log_info("\033[1;32m[信息] 音频时长有效。\033[0m")
                    return {"status": True, "message": "Record duration is valid."}
            except Exception as e:
                self.logger.log_info(f"\033[1;31m[错误] 计算音频时长时发生错误：{e}\033[0m")
                return {"status": False, "message": f"Error calculating audio duration: {e}"}
        else:
            self.logger.log_info(f"\033[1;31m[错误] 文件不存在：{file_path}\033[0m")
            return {"status": False, "message": "File path does not exist."}


    def get_audio_frames_and_rate(self, file_path):
        """
        Extract the total number of audio frames and the frame rate from an audio file.
        Returns the frame count and frame rate if successful, otherwise logs an error and returns None.
        """
        try:
            with wave.open(file_path, 'rb') as audio:
                frames = audio.getnframes()
                rate = audio.getframerate()
                if frames <= 0 or rate <= 0:
                    raise ValueError("Invalid frame count or rate")
                self.logger.log_info(f"Frames: {frames}, Rate: {rate}")
            return frames, rate
        except wave.Error as e:
            self.logger.log_info(f"\033[1;31m[错误] 无法打开音频文件 {file_path}: {e}\033[0m")
            return None, None
        except FileNotFoundError:
            self.logger.log_info(f"\033[1;31m[错误] 音频文件未找到：{file_path}\033[0m")
            return None, None
        except ValueError as ve:
            self.logger.log_info(f"\033[1;31m[错误] 无效的帧数或采样率：{ve}\033[0m")
            return None, None
        except Exception as e:
            self.logger.log_info(f"\033[1;31m[错误] 读取音频文件时发生意外错误 {file_path}: {e}\033[0m")
            return None, None
        





