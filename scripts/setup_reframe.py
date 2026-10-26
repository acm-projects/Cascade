"""Download public inference weights only; never executes downloaded Python code."""
import hashlib
import os
from pathlib import Path
import urllib.request

MODELS={
    'yolox.onnx':('https://media.githubusercontent.com/media/opencv/opencv_zoo/47534e27c9851bb1128ccc0102f1145e27f23f98/models/object_detection_yolox/object_detection_yolox_2022nov.onnx','c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063'),
    'yunet.onnx':('https://media.githubusercontent.com/media/opencv/opencv_zoo/47534e27c9851bb1128ccc0102f1145e27f23f98/models/face_detection_yunet/face_detection_yunet_2023mar.onnx','8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4'),
    'light_asd.model':('https://raw.githubusercontent.com/Junhua-Liao/Light-ASD/ed38c232de5efe0261dbd68627c0ade7cdfe14eb/weight/finetuning_TalkSet.model','efc375833887eefa9d209dc92810e18519b04c3c73ea35a549f2a7f40b7d94d5'),
}

def main():
    folder=Path(os.environ.get('CASCADE_REFRAME_MODELS',Path.home()/'.cache/cascade/reframe'))
    folder.mkdir(parents=True,exist_ok=True)
    for name,(url,digest) in MODELS.items():
        data=urllib.request.urlopen(url,timeout=120).read()
        if len(data)<100_000:raise RuntimeError('Model download was incomplete: '+name)
        actual=hashlib.sha256(data).hexdigest()
        if digest and actual!=digest:raise RuntimeError('Model checksum mismatch: '+name)
        temporary=folder/(name+'.tmp');temporary.write_bytes(data);temporary.replace(folder/name)
        print(name+' ready (SHA256 '+actual+')')

if __name__=='__main__':main()
