import cv2

class ROI:
    def __init__(self, frame):
        self.frame = frame

    def pound_inters(self):
        if self.frame is None:
            print("No frame provided.")
            return []

        rois = cv2.selectROIs("Select Multiple ROIs", self.frame, showCrosshair=True)
        cv2.destroyWindow("Select Multiple ROIs")

        roi_list = [tuple(map(int, roi)) for roi in rois]
        print("Selected ROIs:")
        for i, roi in enumerate(roi_list):
            print(f"ROI {i+1}: {roi}")

        return roi_list
