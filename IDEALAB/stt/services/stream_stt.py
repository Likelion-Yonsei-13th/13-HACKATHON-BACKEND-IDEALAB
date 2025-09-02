import os
import time
import queue
import logging
import grpc
import pyaudio
from requests import Session
from dotenv import load_dotenv

# Audio configuration constants
SAMPLE_RATE = 16000
CHUNK = 1024
CHANNELS = 1
FORMAT = pyaudio.paInt16

# API configuration
API_BASE = "https://openapi.vito.ai"
GRPC_SERVER_URL = "grpc-openapi.vito.ai:443"

# Import protobuf modules
import vito_stt_client_pb2_grpc as pb_grpc
import vito_stt_client_pb2 as pb

class MicrophoneStream:
    """
    Ref[1]: https://cloud.google.com/speech-to-text/docs/transcribe-streaming-audio

    Recording Stream을 생성하고 오디오 청크를 생성하는 제너레이터를 반환하는 클래스.
    """

    def __init__(self: object, rate: int = SAMPLE_RATE, chunk: int = CHUNK, channels: int = CHANNELS, format = FORMAT) -> None:
        self._rate = rate
        self._chunk = chunk
        self._channels = channels
        self._format = format

        # Create a thread-safe buffer of audio data
        self._buff = queue.Queue()
        self.closed = True

        self._audio_interface = pyaudio.PyAudio()
        self._audio_stream = self._audio_interface.open(
            format=pyaudio.paInt16,
            channels=self._channels,
            rate=self._rate,
            input=True,
            frames_per_buffer=self._chunk,
            stream_callback=self._fill_buffer,
        )

        self.closed = False

    def terminate(
        self: object,
    ) -> None:
        """
        Stream을 닫고, 제너레이터를 종료하는 함수
        """
        self._audio_stream.stop_stream()
        self._audio_stream.close()
        self.closed = True
        self._buff.put(None)
        self._audio_interface.terminate()

    def _fill_buffer(
        self: object,
        in_data: object,
        frame_count: int,
        time_info: object,
        status_flags: object,
    ) -> object:
        """
        오디오 Stream으로부터 데이터를 수집하고 버퍼에 저장하는 콜백 함수.

        Args:
            in_data: 바이트 오브젝트로 된 오디오 데이터
            frame_count: 프레임 카운트
            time_info: 시간 정보
            status_flags: 상태 플래그

        Returns:
            바이트 오브젝트로 된 오디오 데이터
        """
        self._buff.put(in_data)
        return None, pyaudio.paContinue

    def generator(self: object) -> object:
        """
        Stream으로부터 오디오 청크를 생성하는 Generator.

        Args:
            self: The MicrophoneStream object

        Returns:
            오디오 청크를 생성하는 Generator
        """
        while not self.closed:
            chunk = self._buff.get()
            if chunk is None:
                return
            data = [chunk]

            while True:
                try:
                    chunk = self._buff.get(block=False)
                    if chunk is None:
                        return
                    data.append(chunk)
                except queue.Empty:
                    break

            yield b"".join(data)

class RTZROpenAPIClient:
    def __init__(self, client_id, client_secret):
        super().__init__()
        self._logger = logging.getLogger(__name__)
        self.client_id = client_id
        self.client_secret = client_secret
        self._sess = Session()
        self._token = None

        self.stream = MicrophoneStream(SAMPLE_RATE, CHUNK, CHANNELS, FORMAT) # 마이크 입력을 오디오 인터페이스 사용하기 위한 Stream 객체 생성

    @property
    def token(self):
        if self._token is None or self._token["expire_at"] < time.time():
            resp = self._sess.post(
                API_BASE + "/v1/authenticate",
                data={"client_id": self.client_id, "client_secret": self.client_secret},
            )
            resp.raise_for_status()
            self._token = resp.json()
        return self._token["access_token"]

    def transcribe_streaming_grpc(self, config):
        base = GRPC_SERVER_URL
        print(f"Connecting to gRPC server: {base}")
        print(f"Using token: {self.token[:20]}...")
        
        with grpc.secure_channel(
            base, credentials=grpc.ssl_channel_credentials()
        ) as channel:
            stub = pb_grpc.OnlineDecoderStub(channel)
            cred = grpc.access_token_call_credentials(self.token)

            audio_generator = self.stream.generator() # (1). 마이크 스트림 Generator 

            # 결과 저장 파일 준비 (stt/scripts 아래에 세션별 파일 생성)
            scripts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            session_id = time.strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(scripts_dir, f"stt_{session_id}.txt")
            print(f"Saving transcripts to: {output_path}")

            def req_iterator():
                yield pb.DecoderRequest(streaming_config=config)
                
                for chunk in audio_generator: # (2). yield from Stream Generator
                    yield pb.DecoderRequest(audio_content=chunk) # chunk를 넘겨서, 스트리밍 STT 수행
                

            req_iter = req_iterator()
            resp_iter = stub.Decode(req_iter, credentials=cred)

            with open(output_path, "a", encoding="utf-8") as out_f:
                for resp in resp_iter:
                    # resp: pb.DecoderResponse
                    for res in resp.results:
                        # 실시간 출력 형태를 위해서 캐리지 리턴 이용
                        if not res.is_final:
                            print("\033[K"+"Text: {}".format(res.alternatives[0].text), end="\r", flush=True) # \033[K: clear line Escape Sequence
                        else:
                            final_text = res.alternatives[0].text
                            print("\033[K" + "Text: {}".format(final_text), end="\n")
                            out_f.write(final_text + "\n")
                            out_f.flush()

    def __del__(self):
        self.stream.terminate()


if __name__ == "__main__":
    load_dotenv()

    client_id = os.getenv("RTZR_CLIENT_ID")
    client_secret = os.getenv("RTZR_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise RuntimeError(
            "환경변수 RTZR_CLIENT_ID / RTZR_CLIENT_SECRET 이 설정되지 않았습니다. "
            ".env를 만들고 값을 채운 뒤 다시 실행하세요."
        )

    print(f"CLIENT_ID: {client_id}")

    client = RTZROpenAPIClient(client_id, client_secret)
    try:
        # Create streaming config
        config = pb.DecoderConfig(
            sample_rate=SAMPLE_RATE,
            encoding=pb.DecoderConfig.AudioEncoding.LINEAR16,
            language="ko",
            use_itn=True,
            use_disfluency_filter=True,
            use_punctuation=True,
            stream_config=pb.RuntimeStreamConfig(
                max_utter_duration=30,
                epd_time=0.8,
            ),
        )
        client.transcribe_streaming_grpc(config)

    except KeyboardInterrupt:
        print("Program terminated by user.")
        del client
