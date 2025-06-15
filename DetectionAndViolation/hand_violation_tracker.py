import cv2

class HandState:
    """Tracks the state of a hand to detect possible violations.""" 
    def __init__(self, hand_id):  # Fixed: __init__ not init
        self.hand_id = hand_id
        self.entered_roi = False
        self.left_roi = False
        self.touched_pizza = False
        self.had_scooper = False
        self.violation_recorded = False

def is_inside_roi(box, roi_list):
    """Check if a bounding box is inside any ROI."""
    x1, y1, w1, h1 = box
    for roi in roi_list:
        x2, y2, w2, h2 = roi
        if not (x1 > x2 + w2 or x1 + w1 < x2 or y1 > y2 + h2 or y1 + h1 < y2):
            return True
    return False  # Moved outside the loop

def are_boxes_close(box1, box2, threshold=50):
    """Check if two boxes are close based on their center points."""
    x1, y1, w1, h1 = box1
    x2, y2, w2, h2 = box2
    center1 = (x1 + w1 // 2, y1 + h1 // 2)
    center2 = (x2 + w2 // 2, y2 + h2 // 2)
    dx = abs(center1[0] - center2[0])
    dy = abs(center1[1] - center2[1])
    return dx < threshold and dy < threshold

# Initialize tracking state
hand_states = {}
violations = []

# Define ROIs
"""ROI_LIST = [(410, 262, 48, 45),
    (387, 300, 51, 44),
    (380, 334, 51, 45),
    (365, 384, 50, 49),
    (351, 430, 52, 45)]"""
ROI_LIST = []
PIZZA_AREA = []  # Update based on actual pizza position

def process_frame(tracked_hands, tracked_scoopers):
    global violations_count
    violations_count = 0
    violation_data = []
    """
    Processes each frame by checking interactions between hands and scooper/pizza areas.
    
    Parameters:
    - tracked_hands: List of tuples (hand_id, bounding_box)
    - tracked_scoopers: List of bounding boxes
    """
    for hand_id, hand_box in tracked_hands:
        if hand_id not in hand_states:
            hand_states[hand_id] = HandState(hand_id)

        state = hand_states[hand_id]

        # Track movement through ROI
        if is_inside_roi(hand_box, ROI_LIST):
            state.entered_roi = True
        else:
            if state.entered_roi:
                state.left_roi = True

        # Check if hand touched pizza
        if is_inside_roi(hand_box, PIZZA_AREA):
            state.touched_pizza = True

        # Check if scooper was nearby
        #for scooper_box in tracked_scoopers:
        for scooper in tracked_scoopers:
            _, scooper_box = scooper
            x2, y2, w2, h2=scooper_box
            if are_boxes_close(hand_box, scooper_box):
                state.had_scooper = True
                break

        # Determine violation
        if (
            state.entered_roi and state.left_roi and state.touched_pizza and
            not state.had_scooper and not state.violation_recorded
        ):
            print(f" Violation by hand ID: {hand_id}")
            violations.append(hand_id)
            state.violation_recorded = True
            violations_count += 1
            violation_data.append((hand_id,hand_box))
    return violations_count , violation_data
       
