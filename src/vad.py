# -*- coding = utf-8 -*-
# @time:2024/8/12 13:34
# Author:david yuan
# @File:config.py



VAD_CONFIG = {
    "iphone12": {
        "RECORD_DURATION": 2,
        "SPEECH_START_RATIO": 0.5,
        "SPEECH_STOP_RATIO": 0.5,
        "SPEECH_RATIO_THRESHOLD": 0.3,
        "NO_SPEECH_RATIO_THRESHOLD": 0.1,
        "OPENAI_WHISPER": True
    },
    "samsungS10": {
        "RECORD_DURATION": 3,
        "SPEECH_START_RATIO": 0.5,
        "SPEECH_STOP_RATIO": 0.5,
        "SPEECH_RATIO_THRESHOLD": 0.35,
        "NO_SPEECH_RATIO_THRESHOLD": 0.15,
        "OPENAI_WHISPER": False
    },
     "huawei_P20_pro": {
        "MIN_RECORD_DURATION": 1.0,
        "MAX_RECORD_DURATION": 10.0,
        "QUEUE_RATIO_INTERRUPT_THRESHOLD": 0.3,
        "QUEUE_RATIO_START_THRESHOLD": 0.2,
        "QUEUE_RATIO_STOP_THRESHOLD": 0.02,
        "OPENAI_WHISPER": True,
        "OPENAI_TTS_ENABLE":False,
        "ENABLE_STREAM_TTS":False,
        "ENABLE_HTTP_AGENT":False,
        "RECIPE_URL":'http://127.0.0.1:9090/recipe/process/instruct',
        "INTERRUPT_URL":'http://127.0.0.1:9090/session/determine/interrupt',
        "NUTRITION_URL":'http://127.0.0.1:9090/nutrition/food/recommendt',
        "ENABLE_DIRECTLY_INTERRUPT":True,
        "ENABLE_MQ":False,
    }
}



