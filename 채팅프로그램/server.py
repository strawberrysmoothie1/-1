from socket import *
from threading import Thread
import cv2
import pickle
import struct
import imutils
import tkinter as tk
from tkinter import scrolledtext
from PIL import Image, ImageTk


class MultiChatVideoServer:
    def __init__(self):
        self.clients = []
        self.emoji_map = {
            ":smile:": "emoji/smile.png",
            ":heart:": "emoji/heart.png",
            ":thumbsup:": "emoji/thumbsup.png"
        }

        # 채팅 소켓 설정
        self.chat_socket = socket(AF_INET, SOCK_STREAM)
        self.chat_port = 2500
        self.chat_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        self.chat_socket.bind(('', self.chat_port))
        self.chat_socket.listen(100)

        # 비디오 소켓 설정
        self.video_socket = socket(AF_INET, SOCK_STREAM)
        self.video_port = 9000
        self.video_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        self.video_socket.bind(('', self.video_port))
        self.video_socket.listen(5)

        print("채팅 및 비디오 서버 실행 중...")

        self.vid = cv2.VideoCapture(0)
        if not self.vid.isOpened():
            print("카메라를 열 수 없습니다.")
            exit()

        self.initialize_gui()

        Thread(target=self.accept_chat_clients, daemon=True).start()
        Thread(target=self.accept_video_clients, daemon=True).start()

        self.root.mainloop()

    def initialize_gui(self):
        self.root = tk.Tk()
        self.root.title("Multi-Chat Video Server")

        self.chat_width = 640

        self.video_label = tk.Label(self.root, bg="black", width=470, height=350)
        self.video_label.pack(pady=10)

        self.chat_transcript_area = scrolledtext.ScrolledText(self.root, height=15, width=int(self.chat_width / 10),
                                                              state=tk.DISABLED)
        self.chat_transcript_area.pack(pady=5)
        self.chat_transcript_area.tag_configure("server", foreground="red")  # 서버 메시지 스타일 추가

        input_frame = tk.Frame(self.root)
        input_frame.pack(pady=5)

        self.name_label = tk.Label(input_frame, text="이름:")
        self.name_label.pack(side=tk.LEFT, padx=5)
        self.name_entry = tk.Entry(input_frame, width=15)
        self.name_entry.pack(side=tk.LEFT, padx=5)
        self.name_entry.insert(0, "서버")  # 기본값 설정

        self.text_entry = tk.Entry(input_frame, width=30)
        self.text_entry.pack(side=tk.LEFT, padx=5)
        self.text_entry.bind("<Return>", lambda event: self.send_chat_message())

        self.send_button = tk.Button(input_frame, text="전송", command=self.send_chat_message)
        self.send_button.pack(side=tk.LEFT, padx=5)

        # 이모티콘 버튼 추가
        emoji_frame = tk.Frame(self.root)
        emoji_frame.pack(pady=5)
        for code, img_path in self.emoji_map.items():
            emoji_img = Image.open(img_path)
            emoji_img.thumbnail((30, 30))
            emoji_icon = ImageTk.PhotoImage(emoji_img)
            button = tk.Button(emoji_frame, image=emoji_icon, command=lambda c=code: self.add_emoji_to_input(c))
            button.image = emoji_icon  # 가비지 컬렉션 방지
            button.pack(side=tk.LEFT, padx=5)

        self.update_video_feed()

    def add_emoji_to_input(self, code):
        """텍스트 입력창에 이모티콘 코드를 추가"""
        current_text = self.text_entry.get()
        self.text_entry.delete(0, tk.END)
        self.text_entry.insert(0, current_text + " " + code)

    def update_video_feed(self):
        ret, frame = self.vid.read()
        if ret:
            frame = cv2.flip(frame, 1)
            frame = imutils.resize(frame, width=self.chat_width)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = ImageTk.PhotoImage(Image.fromarray(frame))
            self.video_label.configure(image=img)
            self.video_label.image = img
        self.root.after(10, self.update_video_feed)

    def send_chat_message(self):
        """텍스트와 이모티콘을 서버에서 전송"""
        name = self.name_entry.get().strip()
        message = self.text_entry.get().strip()

        if name and message:
            full_message = f"{name}: {message}"
            self.update_chat_window(full_message, "server")
            self.broadcast_chat_message(full_message)
            self.text_entry.delete(0, tk.END)

    def update_chat_window(self, message, tag=None):
        """채팅 메시지를 GUI에 업데이트하며 이모티콘 렌더링"""
        self.chat_transcript_area.config(state=tk.NORMAL)
        parts = message.split(" ")

        for part in parts:
            if part in self.emoji_map:
                # 이모티콘 이미지 삽입
                img_path = self.emoji_map[part]
                try:
                    emoji_img = Image.open(img_path)
                    emoji_img.thumbnail((20, 20))
                    emoji_icon = ImageTk.PhotoImage(emoji_img)
                    self.chat_transcript_area.image_create(tk.END, image=emoji_icon)

                    # 참조 유지
                    if not hasattr(self, "emoji_refs"):
                        self.emoji_refs = []
                    self.emoji_refs.append(emoji_icon)
                except Exception as e:
                    print(f"[ERROR] Failed to load emoji image: {e}")
            else:
                # 일반 텍스트 삽입
                self.chat_transcript_area.insert(tk.END, part + " ", tag)

        self.chat_transcript_area.insert(tk.END, '\n')  # 줄바꿈 추가
        self.chat_transcript_area.yview(tk.END)
        self.chat_transcript_area.config(state=tk.DISABLED)

    def broadcast_chat_message(self, message):
        """채팅 메시지를 모든 클라이언트로 브로드캐스트"""
        for client in self.clients:
            try:
                client.sendall(message.encode('utf-8'))
            except Exception as e:
                print(f"[ERROR] Failed to send message to a client: {e}")
                self.clients.remove(client)

    def accept_chat_clients(self):
        while True:
            client_socket, addr = self.chat_socket.accept()
            print(f"채팅 클라이언트 연결됨: {addr}")
            self.clients.append(client_socket)
            Thread(target=self.handle_chat_client, args=(client_socket,), daemon=True).start()

    def handle_chat_client(self, client_socket):
        while True:
            try:
                message = client_socket.recv(256).decode('utf-8')
                if not message:
                    break
                self.update_chat_window(message)
                self.broadcast_chat_message(message)
            except ConnectionError:
                break
        client_socket.close()

    def accept_video_clients(self):
        while True:
            client_socket, addr = self.video_socket.accept()
            print(f"비디오 클라이언트 연결됨: {addr}")
            Thread(target=self.handle_video_client, args=(client_socket,), daemon=True).start()

    def handle_video_client(self, client_socket):
        try:
            while True:
                ret, frame = self.vid.read()
                if not ret:
                    break
                frame = imutils.resize(frame, width=self.chat_width)
                frame_bytes = pickle.dumps(frame)
                message = struct.pack("Q", len(frame_bytes)) + frame_bytes
                client_socket.sendall(message)
        except:
            pass
        finally:
            client_socket.close()


if __name__ == "__main__":
    MultiChatVideoServer()
