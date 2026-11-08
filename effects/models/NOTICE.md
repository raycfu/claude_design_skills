# Models

- `yunet.onnx`: YuNet face detector (face_detection_yunet_2023mar) from https://github.com/opencv/opencv_zoo, MIT licence.
- `selfie_segmenter.tflite`: MediaPipe Selfie Segmenter from https://ai.google.dev/edge/mediapipe/solutions/vision/image_segmenter, Apache License 2.0.

- `rvm_mobilenetv3_fp32.onnx` (not included): Robust Video Matting from https://github.com/PeterL1n/RobustVideoMatting, GPL-3.0. `scripts/setup.sh` downloads it on first run. If it is missing, the effects fall back to the MediaPipe segmenter.
