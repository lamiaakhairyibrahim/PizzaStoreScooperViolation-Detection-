import cv2
import pika
import time
import pickle

class read_frames:
    def __init__(self , path_video):
        self.path_video = path_video

    def read(self):

        connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
        channel = connection.channel()
        channel.queue_declare(queue="video_frames")


        video_path = self.path_video
        cap = cv2.VideoCapture(video_path)

        fram_count = 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            messag = {
                'frame':frame ,
                'frame_number': fram_count , 
                'timestamp':time.time()
            }

            data = pickle.dumps(messag)

            channel.basic_publish(exchange='',routing_key='video_frames',body=data)

            print(f"sent fram {fram_count}")

            fram_count+=1

        cap.release()
        connection.close()
        print("frame reader finished sending all frames")

