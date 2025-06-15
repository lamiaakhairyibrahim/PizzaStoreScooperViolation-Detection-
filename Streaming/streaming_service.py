
import cv2
import pika
import pickle


# Connect to RabbitMQ
connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()
channel.queue_declare(queue='detected_frames')

def callback(ch, method, properties, body):
    data = pickle.loads(body)
    frame = data['frame']
    timeofdetect = data['timestamp']
    numberofvaiolation = data['number_of_violation'] 

    cv2.imshow("Object Detection after", frame)
    if cv2.waitKey(10) & 0xFF == ord('q'):
        cv2.destroyAllWindows()
        exit()

# Start consuming frames
channel.basic_consume(queue='detected_frames', on_message_callback=callback, auto_ack=True)
print("✅ Detection service is running (without tracking)...")
channel.start_consuming()
