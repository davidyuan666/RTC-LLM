# -*- coding: utf-8 -*-
# @time: 2024/8/20 13:41
# @author: David Yuan
# @file: data_stream.py

import asyncio
from concurrent.futures import ThreadPoolExecutor
from rtc_service.configs.config import VAD_CONFIG
from rtc_service.controller.mq_handler import MQHandler
from rtc_service.api.handler_factory import Factory
from rtc_service.utils.logger_util import LoggerConfig
from rtc_service.controller.router_handler import RouterHandler
import spacy
import re

class DataStreamManager:
    def __init__(self,channels, remote):
        self.channels = channels
        self.remote = remote
        self.logger = LoggerConfig()
        self.loop = asyncio.get_event_loop()
        self.executor = ThreadPoolExecutor()
        self.vad_config = VAD_CONFIG['huawei_P20_pro']
        self.router_handler = Factory.get_instance(RouterHandler)
        self.mq_handler = Factory.get_instance(MQHandler)


        # 加载小型中文模型
        '''
        pip install spacy
        python -m spacy download zh_core_web_sm
        '''
        # self.nlp = spacy.load("zh_core_web_sm")
        # self.nlp = spacy.load("xx_ent_wiki_sm")
        self.accumulated_text = ''
        self.MIN_SENTENCE_LENGTH = 10
        self.MAX_SENTENCE_LENGTH = 100


    def send_message(self, message):
        channel = self.channels.get(self.remote)
        if channel:
            channel.send(message)

    def is_sentence_complete_by_model(self, text):
        # 结束标点符号列表
        end_punctuations = '.!?。！？'
        
        # 如果以结束标点符号结尾，直接返回True
        if text[-1] in end_punctuations:
            return True
        
        # 使用spaCy进行简单的语义分析
        doc = self.nlp(text)
        
        # 检查是否包含主谓结构
        has_subject = any(token.dep_ in ["nsubj", "csubj"] for token in doc)
        has_predicate = any(token.pos_ == "VERB" for token in doc)
        
              
        # 检查是否是完整的英文句子（首字母大写，包含主谓）
        is_complete_english = bool(re.match(r'^[A-Z].*[a-zA-Z]$', text)) and has_subject and has_predicate
        
        # 如果是完整的英文句子，或包含主语和谓语且长度超过一定阈值，认为句子可能完整
        if is_complete_english or (has_subject and has_predicate and len(text) > 10):
            return True
        
        
        return False
    
    def is_sentence_complete_by_regex(self, text):
        try:
            # 如果文本为空或者不是字符串，直接返回False
            if not text or not isinstance(text, str):
                return False

            # 结束标点符号列表（包括中英文）
            end_punctuations = '.!?。！？'
            
            # 如果以结束标点符号结尾，直接返回True
            if text[-1] in end_punctuations:
                return True
            
            # 检查文本长度
            if len(text) >= self.MAX_SENTENCE_LENGTH:
                return True
            
            # 检查是否包含完整的英文句子结构（简化版）
            english_sentence_pattern = r'\b[A-Z][^.!?]*[.!?]'
            if re.search(english_sentence_pattern, text):
                return True
            
            # 检查中文句子（简化版，检查是否包含主语和谓语）
            chinese_sentence_pattern = r'(.+[，。；：？！,;:?!].+)'
            if re.search(chinese_sentence_pattern, text):
                return True
            
            return False
        except Exception as e:
            self.logger.log_info(f"Error in is_sentence_complete_by_regex: {str(e)}")
            return False  # 如果发生任何错误，我们假设句子未完成
    


    async def process_transcription(self, text):
        try:
            # 检查是否包含停止指令
            if 'stop' in text.lower() or '停止' in text:
                self.logger.log_info(f'\033[33m====> Interrupt command detected: {text}\033[0m')
                self.send_message('interrupt')
                return 'interrupt'  # 立即返回，不再处理后续逻辑


            self.accumulated_text = getattr(self, 'accumulated_text', '') + text
            
            if not self.is_sentence_complete_by_regex(self.accumulated_text):
                return  # 句子未完成，继续累积
            
            complete_text = self.accumulated_text.strip()
            self.accumulated_text = ''  # 重置累积的文本
            
            if len(complete_text) <= self.MIN_SENTENCE_LENGTH:
                return  # 忽略过短的消息


            if self.vad_config['ENABLE_HTTP_AGENT']:
                return await self.send_http_request(complete_text)
            elif self.vad_config['ENABLE_MQ']:
                await self.mq_handler.send_to_queue(complete_text, routing_key='rtc_query_queue')
            else:
                self.logger.log_info(f'\033[33m====> {complete_text}\033[0m')
                response, status_code = await self.router_handler.run_query(complete_text)
                if status_code == 200:
                    res_message = response['message']
                    self.logger.log_info(f'\033[92m<==== {res_message}\033[0m')
                    self.send_message(message=res_message)
                    return res_message  # 返回处理后的消息
                else:
                    self.logger.log_info(f'Query failed with status code: {status_code}')
        except Exception as e:
            self.logger.log_info(f'Error in process_transcription: {str(e)}')
            # 可以选择在这里重置 accumulated_text，以防止错误状态持续
            self.accumulated_text = ''
        return None  # 如果发生错误或没有有效的响应，返回 None
            


    async def process_incoming_messages(self):
        while True:
            if self.vad_config['ENABLE_MQ']:
                query_msg = await self.mq_handler.receive_from_queue(routing_key='rtc_data_queue')
                response, status_code = await self.router_handler.run_query(query_msg)
                if status_code == 200:
                    message = response['message']
                    self.logger.log_info(f'<== {message}')
                    # self.send_message(message=message)
                await asyncio.sleep(1)  # Prevent busy waiting



    async def send_http_request(self, text):
        # Implement HTTP request logic here
        pass