from socket import *
from tkinter import *
from tkinter.scrolledtext import ScrolledText
from threading import Thread
import cv2
import pickle
import struct
from PIL import Image, ImageTk

class ChatVideoClient:
    def __init__(self, chat_ip, chat_port, video_ip, video_port):
        # 채팅 및 비디오 소켓 초기화
        self.chat_socket = socket(AF_INET, SOCK_STREAM)
        self.video_socket = socket(AF_INET, SOCK_STREAM)
        self.chat_socket.connect((chat_ip, chat_port))
        self.video_socket.connect((video_ip, video_port))

        # 이모티콘 데이터 초기화
        self.emoji_map = {
            ":smile:": "emoji/smile.png",
            ":heart:": "emoji/heart.png",
            ":thumbsup:": "emoji/thumbsup.png"
        }

        # GUI 초기화
        self.initialize_gui()

        # 스레드 시작
        self.start_threads()

    def initialize_gui(self):
        self.root = Tk()
        self.root.title("Chat & Video Client")

        # 비디오 화면
        self.video_label = Label(self.root, bg="black", width=470, height=350)
        self.video_label.pack(pady=10)

        # 채팅 창
        self.chat_transcript_area = ScrolledText(self.root, height=15, width=70, state=DISABLED)
        self.chat_transcript_area.pack(pady=5)
        self.chat_transcript_area.tag_configure("server", foreground="red")  # 서버 메시지 스타일 추가

        # 입력 창과 전송 버튼
        input_frame = Frame(self.root)
        input_frame.pack(pady=5)

        self.name_label = Label(input_frame, text="이름:")
        self.name_label.pack(side=LEFT, padx=5)
        self.name_entry = Entry(input_frame, width=15)
        self.name_entry.pack(side=LEFT, padx=5)

        self.text_entry = Entry(input_frame, width=30)
        self.text_entry.pack(side=LEFT, padx=5)
        self.text_entry.bind("<Return>", lambda event: self.send_chat_message())  # 엔터키 이벤트 바인딩
        self.send_button = Button(input_frame, text="전송", command=self.send_chat_message)
        self.send_button.pack(side=LEFT, padx=5)

        # 이모티콘 버튼 추가
        emoji_frame = Frame(self.root)
        emoji_frame.pack(pady=5)
        for code, img_path in self.emoji_map.items():
            emoji_img = Image.open(img_path)
            emoji_img.thumbnail((30, 30))
            emoji_icon = ImageTk.PhotoImage(emoji_img)
            button = Button(emoji_frame, image=emoji_icon, command=lambda c=code: self.send_emoji(c))
            button.image = emoji_icon  # 가비지 컬렉션 방지
            button.pack(side=LEFT, padx=5)

        # 메인 루프 종료 버튼
        self.exit_button = Button(self.root, text="종료", command=self.close_connection)
        self.exit_button.pack(pady=5)

    def start_threads(self):
        # 채팅 수신 스레드
        chat_thread = Thread(target=self.receive_chat_messages, daemon=True)
        chat_thread.start()

        # 비디오 수신 스레드
        video_thread = Thread(target=self.receive_video_stream, daemon=True)
        video_thread.start()

    def send_chat_message(self):
        """사용자가 입력한 텍스트와 이모티콘을 서버로 전송"""
        name = self.name_entry.get().strip()
        message = self.text_entry.get().strip()

        if name and message:
            full_message = f"{name}: {message}"
            self.chat_socket.sendall(full_message.encode('utf-8'))
            self.text_entry.delete(0, END)

    def send_emoji(self, code):
        """사용자가 이모티콘 버튼을 눌렀을 때 텍스트 입력창에 추가"""
        current_text = self.text_entry.get()
        self.text_entry.delete(0, END)
        self.text_entry.insert(0, current_text + " " + code)

    def receive_chat_messages(self):
        """서버로부터 채팅 메시지를 수신"""
        while True:
            try:
                message = self.chat_socket.recv(256).decode('utf-8')
                self.update_chat_window(message)
            except ConnectionError:
                break

    def receive_video_stream(self):
        """서버로부터 비디오 스트림을 수신"""
        data = b""
        payload_size = struct.calcsize("Q")

        while True:
            try:
                while len(data) < payload_size:
                    packet = self.video_socket.recv(4 * 1024)
                    if not packet:
                        return
                    data += packet

                packed_msg_size = data[:payload_size]
                data = data[payload_size:]
                msg_size = struct.unpack("Q", packed_msg_size)[0]

                while len(data) < msg_size:
                    data += self.video_socket.recv(4 * 1024)

                frame_data = data[:msg_size]
                data = data[msg_size:]

                frame = pickle.loads(frame_data)
                frame = cv2.flip(frame, 1)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = ImageTk.PhotoImage(Image.fromarray(frame))
                self.video_label.config(image=img)
                self.video_label.image = img

            except Exception as e:
                print("비디오 수신 중 오류 발생:", e)
                break

    def update_chat_window(self, message):
        """텍스트와 이모티콘을 동시에 렌더링"""
        self.chat_transcript_area.config(state=NORMAL)

        # 서버 메시지인지 확인
        is_server_message = message.startswith("서버:")  # 서버 메시지일 경우
        parts = message.split(" ")
        for part in parts:
            if part in self.emoji_map:
                # 이모티콘 코드일 경우 이미지 삽입
                img_path = self.emoji_map[part]
                try:
                    emoji_img = Image.open(img_path)
                    emoji_img.thumbnail((20, 20))
                    emoji_icon = ImageTk.PhotoImage(emoji_img)
                    self.chat_transcript_area.image_create(END, image=emoji_icon)

                    # 참조 유지
                    if not hasattr(self, "emoji_refs"):
                        self.emoji_refs = []
                    self.emoji_refs.append(emoji_icon)
                except Exception as e:
                    print(f"[ERROR] Failed to load emoji image: {e}")
            else:
                # 일반 텍스트는 그대로 삽입
                if is_server_message:
                    self.chat_transcript_area.insert(END, part + " ", "server")
                else:
                    self.chat_transcript_area.insert(END, part + " ")

        self.chat_transcript_area.insert(END, '\n')  # 줄바꿈
        self.chat_transcript_area.yview(END)
        self.chat_transcript_area.config(state=DISABLED)

    def close_connection(self):
        """클라이언트 연결 종료"""
        self.chat_socket.close()
        self.video_socket.close()
        self.root.destroy()


if __name__ == "__main__":
    chat_ip = input("채팅 서버 IP (기본값: 127.0.0.1): ") or "127.0.0.1"
    chat_port = 2500
    video_ip = input("비디오 서버 IP (기본값: 127.0.0.1): ") or "127.0.0.1"
    video_port = 9000

    client = ChatVideoClient(chat_ip, chat_port, video_ip, video_port)
    client.root.mainloop()
