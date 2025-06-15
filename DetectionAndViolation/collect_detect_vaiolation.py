from detect_serv import Detect
#from tracking_with_deep_sort import Detect

path_model = r"../models\yolov8\best.pt"
#r"../dataset\Sah w b3dha ghalt (2).mp4"
detector = Detect(path_model) 
detector.frame_detect()