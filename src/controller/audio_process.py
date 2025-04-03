import asyncio
import os

class AudioProcessor:
    def __init__(self):
        # 创建异步队列
        self.audio_task_queue = asyncio.Queue()
        # 启动后台任务处理音频队列
        asyncio.create_task(self.process_audio_queue())

    async def process_audio_queue(self):
        """后台任务，从队列中获取并处理音频任务。"""
        while True:
            recording_session, is_stream = await self.audio_task_queue.get()  # 获取任务
            await self.process_audio_task(recording_session, is_stream)       # 处理任务
            self.audio_task_queue.task_done()  # 标记任务完成

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
                    self.media_handler.send_data_channel("interrupt")
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

    async def analyze_recorded_audio(self, is_stream=False, recording_session=None):
        """将音频处理任务添加到队列中"""
        # 将任务加入队列
        await self.audio_task_queue.put((recording_session, is_stream))
        self.logger.log_info("\033[1;32m[任务加入队列] 音频处理任务已加入队列。\033[0m")

