
import cv2
import pika
import pickle
from ultralytics import YOLO
import time
from hand_violation_tracker import HandState , process_frame , hand_states , violations ,ROI_LIST,PIZZA_AREA 
from roi import ROI
from violation_database import init_db , save_violation
# List of ROI areas (x, y, width, height)

class Detect:
    def __init__(self, yolo_path):
        self.model = YOLO(yolo_path)
        self.roi_init = False

    def draw_rois(self, frame):
        for roi in ROI_LIST:
            x, y, w, h = roi
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 255), 2)
            cv2.putText(frame, "ROI", (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    
    def is_inside_roi(self,box, roi):
        x1, y1, w1, h1 = box
        x2, y2, w2, h2 = roi
        return not (x1 > x2 + w2 or x1 + w1 < x2 or y1 > y2 + h2 or y1 + h1 < y2)

    def frame_detect(self):
        init_db()
        # Connect to RabbitMQ
        connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
        channel = connection.channel()
        channel.queue_declare(queue="video_frames")
        channel.queue_declare(queue="detected_frames")

        print("Waiting for first frame to select ROI...")
        while True:
            method_frame, header_frame, body = channel.basic_get(queue="video_frames", auto_ack=True)
            if method_frame:
                data = pickle.loads(body)
                frame = data['frame']
                roi_tool = ROI(frame)
                roi_list = roi_tool.pound_inters()
                ROI_LIST.clear()
                ROI_LIST.extend(roi_list)
                print(f" ROI Selected: {ROI_LIST}")
                break
        


        def callback(ch, method, properties, body):
            global roi_init 
            data = pickle.loads(body)
            frame = data['frame']
            frame_number = data['frame_number']

            # Run YOLO detection
            results = self.model.track(source=frame, persist=True, tracker="bytetrack.yaml")[0]
            tracked_hand = []
            tracked_scooper = []
            tracked_pizza = []

            for box in results.boxes:
                cls_id = int(box.cls[0])
                label = results.names[cls_id]
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                w, h = x2 - x1, y2 - y1
                box_coords = (x1, y1, w, h)
                if hasattr(box , 'id'):
                    object_id = int(box.id[0])
                else:
                    continue
                color = (0, 255, 0)
                if label == "hand" :
                    tracked_hand.append((object_id , box_coords))
                    if object_id in violations:
                       color = (0, 0, 255)
                elif label == "scooper":
                    tracked_scooper.append((object_id , box_coords))
                    color = (255, 255, 0)
                elif label == 'pizza':
                    tracked_pizza.append((object_id,box_coords))
                    color = (255, 100, 180)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, f"{label}-{object_id}", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            PIZZA_AREA.clear()
            for _, pizza_box in tracked_pizza:
                PIZZA_AREA.append(pizza_box)
                
            violation_count , violation_found = process_frame(tracked_hands=tracked_hand , tracked_scoopers=tracked_scooper)
            ## for database
            for hand_id_ , hand_box in violation_found:
                save_violation(frame , hand_id_ , hand_box)

            for roi in ROI_LIST:
                x, y, w, h = roi
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 255), 2)
                cv2.putText(frame, "ROI", (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            for pz in PIZZA_AREA:
                    x, y, w, h = pz
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (150, 50, 255), 2)
                    cv2.putText(frame, "PIZZA", (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 50, 255), 1)

            cv2.putText(frame, f"Violations: {violation_count}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

            send_data = {
                'frame': frame,
                'timestamp':time.time(),
                'number_of_violation' : violation_count
            }
            send_body = pickle.dumps(send_data)
            channel.basic_publish(exchange='', routing_key='detected_frames', body=send_body)

        # Start consuming frames
        channel.basic_consume(queue='video_frames', on_message_callback=callback, auto_ack=True)
        print(" Detection service is running (with tracking)...")
        channel.start_consuming()



