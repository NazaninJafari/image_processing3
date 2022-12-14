#!/usr/bin/python3
# -*- coding:utf-8 -*-

import numpy as np
import cv2
import tensorflow as tf
from functools import partial
from TFLiteFaceDetector import UltraLightFaceDetecion
import sys

#left: 35,36,33,37,39,42,40,41
#right: 89,90,87,91,93,96,94,95
#lip: 52,55,56,53,56,58,69,68,67,71,63,64

class CoordinateAlignmentModel():
    def __init__(self, filepath, marker_nums=106, input_size=(192, 192)):
        self._marker_nums = marker_nums
        self._input_shape = input_size
        self._trans_distance = self._input_shape[-1] / 2.0

        self.eye_bound = ([35, 41, 40, 42, 39, 37, 33, 36],
                          [89, 95, 94, 96, 93, 91, 87, 90])

        # tflite model init
        self._interpreter = tf.lite.Interpreter(model_path=filepath)
        self._interpreter.allocate_tensors()

        # model details
        input_details = self._interpreter.get_input_details()
        output_details = self._interpreter.get_output_details()

        # inference helper
        self._set_input_tensor = partial(self._interpreter.set_tensor,
                                         input_details[0]["index"])
        self._get_output_tensor = partial(self._interpreter.get_tensor,
                                          output_details[0]["index"])

        self.pre_landmarks = None

    def _calibrate(self, pred, thd, skip=6):
        if self.pre_landmarks is not None:
            for i in range(pred.shape[0]):
                if abs(self.pre_landmarks[i, 0] - pred[i, 0]) > skip:
                    self.pre_landmarks[i, 0] = pred[i, 0]
                elif abs(self.pre_landmarks[i, 0] - pred[i, 0]) > thd:
                    self.pre_landmarks[i, 0] += pred[i, 0]
                    self.pre_landmarks[i, 0] /= 2

                if abs(self.pre_landmarks[i, 1] - pred[i, 1]) > skip:
                    self.pre_landmarks[i, 1] = pred[i, 1]
                elif abs(self.pre_landmarks[i, 1] - pred[i, 1]) > thd:
                    self.pre_landmarks[i, 1] += pred[i, 1]  
                    self.pre_landmarks[i, 1] /= 2
        else:
            self.pre_landmarks = pred

    def _preprocessing(self, img, bbox, factor=3.0):
        """Pre-processing of the BGR image. Adopting warp affine for face corp.

        Arguments
        ----------
        img {numpy.array} : the raw BGR image.
        bbox {numpy.array} : bounding box with format: {x1, y1, x2, y2, score}.

        Keyword Arguments
        ----------
        factor : max edge scale factor for bounding box cropping.

        Returns
        ----------
        inp : input tensor with NHWC format.
        M : warp affine matrix.
        """

        maximum_edge = max(bbox[2:4] - bbox[:2]) * factor
        scale = self._trans_distance * 4.0 / maximum_edge
        center = (bbox[2:4] + bbox[:2]) / 2.0
        cx, cy = self._trans_distance - scale * center

        M = np.array([[scale, 0, cx], [0, scale, cy]])

        cropped = cv2.warpAffine(img, M, self._input_shape, borderValue=0.0)
        inp = cropped[..., ::-1].astype(np.float32)

        return inp[None, ...], M

    def _inference(self, input_tensor):
        self._set_input_tensor(input_tensor)
        self._interpreter.invoke()

        return self._get_output_tensor()[0]

    def _postprocessing(self, out, M):
        iM = cv2.invertAffineTransform(M)
        col = np.ones((self._marker_nums, 1))

        out = out.reshape((self._marker_nums, 2))

        out += 1
        out *= self._trans_distance

        out = np.concatenate((out, col), axis=1)

        return out @ iM.T  # dot product

    def get_landmarks(self, image, detected_faces=None):
        """Predict the landmarks for each face present in the image.

        This function predicts a set of 68 2D or 3D images, one for each image present.
        If detect_faces is None the method will also run a face detector.

        Arguments
        ----------
        image {numpy.array} : The input image.

        Keyword Arguments
        ----------
        detected_faces {list of numpy.array} : list of bounding boxes, one for each
        face found in the image (default: {None}, format: {x1, y1, x2, y2, score})
        """

        for box in detected_faces:
            inp, M = self._preprocessing(image, box)
            out = self._inference(inp)
            pred = self._postprocessing(out, M)

            # self._calibrate(pred, 1, skip=6)
            # yield self.pre_landmarks

            yield pred


def instagram_effect(img, landmarks):
   
    x,y,w,h=cv2.boundingRect(landmarks)
    #creat mask
    mask = np.zeros(img.shape , dtype='uint8')
    
    #draw contours on mask
    cv2.drawContours(mask, [landmarks], -1, (255, 255, 255), -1)
    
    #for resized orginal image & mask (x*2)  
    grand_frame = cv2.resize(img, None, fx=2, fy=2)
    grand_mask = cv2.resize(mask, None, fx=2, fy=2)

    #for convert pixels between 0 and 1
    grand_frame = grand_frame / 255
    grand_mask = grand_mask / 255

    #put landmarks on mask
    mask_landmarks = cv2.multiply(grand_mask, grand_frame)

    #mokhtasate landmark va ykam atrafe landmark ra dar rect frame beriz
    rect_frame = img[int(y - (h * 0.5)) : int(y + h + (h * 0.5)), int(x - (w * 0.5)):int(x + w + (w * 0.5))]
    rect_frame = rect_frame / 255

    gmask_invers = 1 - grand_mask[y * 2:(y + h) * 2 , x * 2:(x + w) * 2]
    background = cv2.multiply(rect_frame , gmask_invers )
    
    #mettre les grands landmarks sur le backg
    newpic = cv2.add(background, mask_landmarks[y * 2:(y + h) * 2, x * 2:(x + w) * 2])

    #put new pic on orginal image
    img[int(y - (h * 0.5)) : int(y + h + (h * 0.5)), int(x - (w * 0.5)):int(x + w + (w * 0.5))] = newpic * 255
        
    return img


if __name__ == '__main__':

    fd = UltraLightFaceDetecion("weights/RFB-320.tflite", conf_threshold=0.88)
    fa = CoordinateAlignmentModel("weights/coor_2d106.tflite")
    
    cap = cv2.VideoCapture(0)
    #frame = cv2.imread('mypic.jpg')
    
    while True:

        ret, frame = cap.read()
        if not ret:
            break

        #be tedade chehre tu tasvir bo va sc daryaft mikone
        boxes, scores = fd.inference(frame)
        #be tedade chehreha
        for pred in fa.get_landmarks(frame, boxes):
            pred_int = np.round(pred).astype(np.int)

            landmark_lefteye = []
            for i in [35,36,33,37,39,42,40,41]:
                landmark_lefteye.append(tuple(pred_int[i]))

            landmark_righteye = []
            for i in [89,90,87,91,93,96,94,95]:
                landmark_righteye.append(tuple(pred_int[i]))

            landmark_lips = []
            for i in [52,55,56,53,56,58,69,68,67,71,63,64]:
                landmark_lips.append(tuple(pred_int[i]))    
        
            landmark_lefteye = np.array([landmark_lefteye])
            landmark_righteye = np.array([landmark_righteye])
            landmark_lips = np.array([landmark_lips])
        

            result = instagram_effect(frame, landmark_lefteye)
            result = instagram_effect(frame, landmark_righteye)
            result = instagram_effect(frame, landmark_lips)
    
            cv2.imshow("webcam", result)
        
        key = cv2.waitKey(1)
        if key == 27: #ESC
            break
        
    
cap.release()
cv2.destroyAllWindows()    
