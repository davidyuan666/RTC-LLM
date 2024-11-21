class RecordingSession:
    def __init__(self, session_id, temp_listen_path, wav_file, valid_audio=False):
        self.session_id = session_id
        self.temp_listen_path = temp_listen_path
        self.wav_file = wav_file
        self.valid_audio = valid_audio
