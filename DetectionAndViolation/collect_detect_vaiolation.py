#from detect_serv import Detect
#from tracking_with_deep_sort import Detect

#path_model = r"../models\yolov8\best.pt"
#r"../dataset\Sah w b3dha ghalt (2).mp4"
#detector = Detect(path_model) 
#detector.frame_detect()
import cv2
from ultralytics import YOLO
import math
import pika
import pickle
import time

from violation_database import init_db , save_violation

class HandState:
    def __init__(self, hand_id):
        self.hand_id = hand_id
        self.entered_roi_at_least_once = False
        self.currently_in_roi = False
        self.exited_roi_after_entry = False
        self.touched_pizza_after_roi_exit = False
        self.had_scooper_when_needed = False
        self.violation_recorded = False
        self.last_seen_frame = 0 


def is_inside_roi(box, roi_list):

    if not roi_list:
        return False
    
    x1, y1, w1, h1 = box
    for roi in roi_list:
        x2, y2, w2, h2 = roi
     
        inter_x1 = max(x1, x2)
        inter_y1 = max(y1, y2)
        inter_x2 = min(x1 + w1, x2 + w2)
        inter_y2 = min(y1 + h1, y2 + h1)

        inter_width = max(0, inter_x2 - inter_x1)
        inter_height = max(0, inter_y2 - inter_y1)
        inter_area = inter_width * inter_height

        if inter_area > 0:
            return True
    return False


def get_center(box):
 
    x, y, w, h = box
    return (x + w // 2, y + h // 2)


def are_boxes_close(box1, box2, threshold=50):

    center1 = get_center(box1)
    center2 = get_center(box2)
    
    dx = (center1[0] - center2[0])**2
    dy = (center1[1] - center2[1])**2
    
    distance = math.sqrt(dx + dy)
    
    return distance < threshold

class ROI:
    def __init__(self, frame):
        self.frame = frame

    def pound_inters(self):
        if self.frame is None:
            print("No frame provided for ROI selection.")
            return []

        print("Please select ROIs on the displayed frame. Press ENTER after selecting each ROI, then 'c' to confirm all, or 'q' to cancel.")
        rois = cv2.selectROIs("Select Multiple ROIs", self.frame, showCrosshair=True)
        cv2.destroyWindow("Select Multiple ROIs")

        roi_list = [tuple(map(int, roi)) for roi in rois]
        if not roi_list:
            print("No ROIs were selected. Using an empty list.")
        else:
            print("Selected ROIs:")
            for i, roi in enumerate(roi_list):
                print(f"ROI {i+1}: {roi}")

        return roi_list


hand_states = {} 
violations_set = set() 

ROI_LIST = [] 

PIZZA_AREA = []

def process_frame(tracked_hands, tracked_scoopers, current_frame_number, current_frame):

    current_frame_hand_ids = set()
    for hand_id, hand_box in tracked_hands:
        current_frame_hand_ids.add(hand_id)
        if hand_id not in hand_states:
            hand_states[hand_id] = HandState(hand_id)

        state = hand_states[hand_id]
        state.last_seen_frame = current_frame_number 

        was_currently_in_roi = state.currently_in_roi
        state.currently_in_roi = is_inside_roi(hand_box, ROI_LIST)

        if state.currently_in_roi:
            state.entered_roi_at_least_once = True
        
        if was_currently_in_roi and not state.currently_in_roi and state.entered_roi_at_least_once:
            state.exited_roi_after_entry = True
            
        if is_inside_roi(hand_box, PIZZA_AREA):
            if state.exited_roi_after_entry: 
                state.touched_pizza_after_roi_exit = True
            
        hand_has_scooper_now = False
        for scooper_id, scooper_box in tracked_scoopers:
            if are_boxes_close(hand_box, scooper_box):
                hand_has_scooper_now = True
                break
        state.had_scooper_when_needed = hand_has_scooper_now

        if (
            state.entered_roi_at_least_once and
            state.exited_roi_after_entry and
            state.touched_pizza_after_roi_exit and
            not state.had_scooper_when_needed and
            not state.violation_recorded
        ):
            print(f"A violation of the hand ID was created: {hand_id} In frame No.{current_frame_number}")
            violations_set.add(hand_id)
            state.violation_recorded = True
            save_violation(current_frame, hand_id, hand_box)

    keys_to_delete = [
        hand_id for hand_id, hand_state in hand_states.items()
        if current_frame_number - hand_state.last_seen_frame > 30 
    ]
    for key in keys_to_delete:
        if key in hand_states:
            del hand_states[key]

    violation_count = len(violations_set)
    
    violation_data = [
        (hand_id, hand_states[hand_id].__dict__) for hand_id in violations_set
        if hand_id in hand_states 
    ]

    return violation_count, violation_data

class Detect:
    def __init__(self, yolo_path):
        self.model = YOLO(yolo_path)
        self.connection = None
        self.channel = None
        self.frame_count = 0 

        self.video_writer = None
        self.output_video_path = "output_video.mp4" 
        self.frame_width = 0
        self.frame_height = 0
        self.fps = 20 

    def connect_rabbitmq(self):
        self.connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue="video_frames")
        self.channel.queue_declare(queue="detected_frames")
        print("RabbitMQ queues called: video_frames, detected_frames")

        method_frame, header_frame, body = self.channel.basic_get(queue="video_frames", auto_ack=False)
        if method_frame:
            data = pickle.loads(body)
            temp_frame = data['frame']
            self.frame_height, self.frame_width, _ = temp_frame.shape
            
            fourcc = cv2.VideoWriter_fourcc(*'mp4v') 
            self.video_writer = cv2.VideoWriter(self.output_video_path, fourcc, self.fps, (self.frame_width, self.frame_height))

            self.channel.basic_publish(exchange='', routing_key='video_frames', body=body)
            self.channel.basic_ack(method_frame.delivery_tag)
            print(f"The video writer is formatted with the dimensions: {self.frame_width}x{self.frame_height}")
        else:
            print("The first frame of the video writer initialization was not retrieved. The resulting video may not be generated.")
            self.video_writer = None 

    def disconnect_rabbitmq(self):
        if self.connection and self.connection.is_open:
            self.connection.close()
            print("RabbitMQ has been disconnected.")

        if self.video_writer:
            self.video_writer.release()
            print(f"The resulting video was saved to: {self.output_video_path}")

    def select_roi_initial(self):

        global ROI_LIST 

        print("Waiting for the first frame from the 'video_frames' queue to perform ROI determination...")
        first_frame_body = None
        method_frame = None

        while True:
            method_frame, header_frame, body = self.channel.basic_get(queue="video_frames", auto_ack=False) 
            if method_frame:
                data = pickle.loads(body)
                frame_for_roi = data['frame']
                first_frame_body = body 
                break
            time.sleep(0.1) 

        if first_frame_body:
            roi_tool = ROI(frame_for_roi)
            selected_rois = roi_tool.pound_inters()
            
            ROI_LIST.clear() 
            ROI_LIST.extend(selected_rois)
            
            self.channel.basic_publish(exchange='', routing_key='video_frames', body=first_frame_body)
            self.channel.basic_ack(method_frame.delivery_tag)
        else:
            ROI_LIST = [] 


    def process_rabbitmq_frame(self, ch, method, properties, body):

        self.frame_count += 1
        data = pickle.loads(body)
        frame = data['frame'] 
        
        results = self.model.track(source=frame, persist=True, tracker="bytetrack.yaml")[0]
        
        tracked_hand = []
        tracked_scooper = []
        tracked_pizza = []
        PIZZA_AREA.clear() 

        if results.boxes is not None and results.boxes.id is not None:
            for box in results.boxes:
                cls_id = int(box.cls[0])
                label = results.names[cls_id]
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                w, h = x2 - x1, y2 - y1
                box_coords = (x1, y1, w, h)
                
                object_id = int(box.id[0])
                
                color = (0, 255, 0) 

                if label == "hand":
                    tracked_hand.append((object_id, box_coords))
                    if object_id in violations_set: 
                        color = (0, 0, 255) 
                elif label == "scooper":
                    tracked_scooper.append((object_id, box_coords))
                    color = (255, 255, 0)
                elif label == 'pizza':
                    PIZZA_AREA.append(box_coords)
                    color = (255, 100, 180)
                
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, f"{label}-{object_id}", (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        violation_count, violation_data = process_frame(
            tracked_hands=tracked_hand, 
            tracked_scoopers=tracked_scooper,
            current_frame_number=self.frame_count,
            current_frame=frame 
        )
        
        for roi in ROI_LIST:
            x, y, w, h = roi
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 255), 2)
            cv2.putText(frame, "ROI", (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        
        for pz_box in PIZZA_AREA:
            x, y, w, h = pz_box
            cv2.rectangle(frame, (x, y), (x + w, y + h), (150, 50, 255), 2)
            cv2.putText(frame, "PIZZA", (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 50, 255), 1)

        cv2.putText(frame, f"Violations: {violation_count}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        send_data = {
            'frame': frame,
            'timestamp': time.time(),
            'number_of_violation': violation_count
        }
        send_body = pickle.dumps(send_data)
        self.channel.basic_publish(exchange='', routing_key='detected_frames', body=send_body)
  
        ch.basic_ack(method.delivery_tag)

        if self.video_writer:
            if len(frame.shape) == 2: 
                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            elif frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
            self.video_writer.write(frame)


    def start_detection_service(self):
        init_db() 
        self.connect_rabbitmq() 
        self.select_roi_initial() 

        self.channel.basic_consume(queue='video_frames', on_message_callback=self.process_rabbitmq_frame, auto_ack=False) 
        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            print("The detection service has been stopped by the user.")
        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            self.disconnect_rabbitmq()
            cv2.destroyAllWindows()

if __name__ == "__main__":
    yolo_model_path = r"..\models\my_training\best.pt"
    #path_model = r"../models\yolov8\best.pt"
    #D:\my_projects\pizza\lastpizza\src\models\my_training\best.pt
    #r"../dataset\Sah w b3dha ghalt.mp4"
    
    detector = Detect(yolo_model_path)
    detector.start_detection_service()