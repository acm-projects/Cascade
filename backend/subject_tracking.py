"""Local COCO subject detection and conservative appearance/flow track association."""
import math
import re
from pathlib import Path
from functools import lru_cache
from threading import RLock

CATEGORIES=('person,bicycle,car,motorcycle,airplane,bus,train,truck,boat,traffic light,fire hydrant,stop sign,parking meter,bench,bird,cat,dog,horse,sheep,cow,elephant,bear,zebra,giraffe,backpack,umbrella,handbag,tie,suitcase,frisbee,skis,snowboard,sports ball,kite,baseball bat,baseball glove,skateboard,surfboard,tennis racket,bottle,wine glass,cup,fork,knife,spoon,bowl,banana,apple,sandwich,orange,broccoli,carrot,hot dog,pizza,donut,cake,chair,couch,potted plant,bed,dining table,toilet,tv,laptop,mouse,remote,keyboard,cell phone,microwave,oven,toaster,sink,refrigerator,book,clock,vase,scissors,teddy bear,hair drier,toothbrush').split(',')


def context_classes(text):
    text=' '+re.sub(r'[^a-z ]',' ',text.lower())+' '
    aliases={'person':['man','woman','people','speaker','friend','child','boy','girl','conversation'], 'dog':['puppy'], 'cat':['kitten'], 'sports ball':['ball'], 'car':['vehicle']}
    return {name for name in CATEGORIES if any(re.search(r'\b'+re.escape(word)+r's?\b',text) for word in [name,*aliases.get(name,[])])}


@lru_cache(maxsize=2)
def _object_model(path,mtime,size):
    import cv2 as cv
    # OpenCV Net is mutable; serialized inference also protects future parallel workers.
    return cv.dnn.readNet(path),RLock()


class Subjects:
    def __init__(self,model_path,metrics=None):
        import cv2 as cv
        import numpy as np
        if not Path(model_path).is_file():raise ValueError('Subject model is missing. Run python3 scripts/setup_reframe.py and retry.')
        self.cv,self.np=cv,np
        path=Path(model_path);self.net,self.net_lock=_object_model(str(path.resolve()),path.stat().st_mtime_ns,path.stat().st_size);self.metrics=metrics;self.tracks={};self.next_id=0;self.previous=None;self.scene=0
        grids=[];strides=[]
        for stride in (8,16,32):
            x,y=np.meshgrid(np.arange(640//stride),np.arange(640//stride));grids.append(np.stack((x,y),-1).reshape(-1,2));strides.append(np.full((x.size,1),stride))
        self.grid=np.concatenate(grids);self.strides=np.concatenate(strides)

    def detect(self,image):
        cv,np=self.cv,self.np;h,w=image.shape[:2];scale=min(640/w,640/h)
        padded=np.full((640,640,3),114,dtype=np.float32)
        padded[:int(h*scale),:int(w*scale)]=cv.resize(cv.cvtColor(image,cv.COLOR_BGR2RGB),(int(w*scale),int(h*scale)))
        with self.net_lock:
            self.net.setInput(padded.transpose(2,0,1)[None]);out=self.net.forward()[0].copy()
        scores=out[:,4,None]*out[:,5:];classes=scores.argmax(1);confidence=scores.max(1)
        xy=(out[:,:2]+self.grid)*self.strides;wh=np.exp(out[:,2:4])*self.strides
        boxes=np.concatenate((xy-wh/2,wh),1)/scale
        indices=cv.dnn.NMSBoxesBatched(boxes.tolist(),confidence.tolist(),classes.tolist(),.4,.45)
        result=[]
        for i in indices:
            x,y,bw,bh=boxes[i];x0=max(0,int(x));y0=max(0,int(y));x1=min(w,int(x+bw));y1=min(h,int(y+bh))
            if x1<=x0 or y1<=y0:continue
            hist=cv.calcHist([cv.cvtColor(image[y0:y1,x0:x1],cv.COLOR_BGR2HSV)],[0,1],None,[16,8],[0,180,0,256]);cv.normalize(hist,hist)
            result.append({'box':[x0/w,y0/h,(x1-x0)/w,(y1-y0)/h],'label':CATEGORIES[classes[i]],'confidence':float(confidence[i]),'hist':hist})
        return result

    def update(self,image,index):
        from backend.reframe import iou
        cv,np=self.cv,self.np;gray=cv.cvtColor(image,cv.COLOR_BGR2GRAY);h,w=gray.shape
        # A strong whole-frame discontinuity drops identity rather than guessing across cuts.
        cut=self.previous is not None and float(np.mean(cv.absdiff(cv.resize(gray,(64,36)),cv.resize(self.previous,(64,36)))))>48
        if cut:self.tracks.clear();self.scene+=1
        # Keep the same feature selection and detector cadence, but compute pyramids
        # once for all subjects rather than twice per subject on each frame.
        if self.previous is not None and not cut:
            bundles=[];all_points=[];offset=0
            for track in self.tracks.values():
                x,y,bw,bh=track['box'];left=max(0,int(x*w));top=max(0,int(y*h));right=min(w,int((x+bw)*w));bottom=min(h,int((y+bh)*h))
                # Three pixels of context preserve the Sobel/block neighborhood at mask edges.
                rx=max(0,left-3);ry=max(0,top-3);rr=min(w,right+3);rb=min(h,bottom+3)
                if right<=left or bottom<=top:continue
                roi=self.previous[ry:rb,rx:rr];mask=np.zeros_like(roi);mask[top-ry:bottom-ry,left-rx:right-rx]=255
                points=cv.goodFeaturesToTrack(roi,30,.03,5,mask=mask)
                if points is not None:points+=np.array([rx,ry],dtype=np.float32)
                if points is None or len(points)<4:continue
                bundles.append((track,offset,len(points)));all_points.append(points);offset+=len(points)
            if all_points:
                points=np.concatenate(all_points)
                moved,status,_=cv.calcOpticalFlowPyrLK(self.previous,gray,points,None)
                if moved is not None:
                    back,bs,_=cv.calcOpticalFlowPyrLK(gray,self.previous,moved,None)
                    if back is not None:
                        valid=(status.ravel()==1)&(bs.ravel()==1)&(np.linalg.norm(back-points,axis=2).ravel()<1.5)
                        for track,start,count in bundles:
                            ok=valid[start:start+count]
                            if ok.sum()<4:continue
                            dx,dy=np.median((moved-points)[start:start+count][ok],axis=0).ravel()
                            x,y,bw,bh=track['box'];track['box']=[max(0,min(1-bw,x+float(dx)/w)),max(0,min(1-bh,y+float(dy)/h)),bw,bh]
        if index%5==0 or cut:
            detections=self.metrics.call('object_detection',self.detect,image) if self.metrics else self.detect(image);used=set()
            for d in detections:
                choices=[]
                for ident,tr in self.tracks.items():
                    if ident in used or tr['label']!=d['label'] or index-tr['seen']>25:continue
                    overlap=iou(tr['box'],d['box']);distance=math.dist([tr['box'][0],tr['box'][1]],[d['box'][0],d['box'][1]])
                    similarity=cv.compareHist(tr['hist'],d['hist'],cv.HISTCMP_CORREL)
                    if overlap>.12 or (distance<.15 and similarity>.75):choices.append((overlap+.25*similarity,ident))
                ident=max(choices)[1] if choices else self.next_id
                if not choices:self.next_id+=1
                self.tracks[ident]={**d,'seen':index};used.add(ident)
        self.previous=gray
        self.tracks={i:t for i,t in self.tracks.items() if index-t['seen']<=20}
        return [{'id':i,'label':t['label'],'box':t['box'][:],'confidence':t['confidence']*(.94**(index-t['seen'])),'scene':self.scene} for i,t in self.tracks.items()],cut


class RegionTracker:
    """User-seeded MIL tracking. Appearance checks stop drift; no semantic claim."""
    def __init__(self,selection):self.selection=selection;self.tracker=None;self.template=None;self.lost=False;self.last_region=None
    def update(self,image,t,cut):
        import cv2 as cv
        import numpy as np
        if t+1e-4<self.selection['t'] or self.lost:return None
        h,w=image.shape[:2]
        if cut and self.tracker is not None:self.lost=True;return None
        if self.tracker is None:
            x,y,bw,bh=self.selection['box'];box=(int(x*w),int(y*h),max(4,int(bw*w)),max(4,int(bh*h)))
            self.tracker=cv.TrackerMIL_create();self.tracker.init(image,box);x,y,bw,bh=box
            self.template=cv.calcHist([cv.cvtColor(image[y:y+bh,x:x+bw],cv.COLOR_BGR2HSV)],[0,1],None,[16,8],[0,180,0,256]);cv.normalize(self.template,self.template)
        else:
            if cut:self.lost=True;return None
            ok,box=self.tracker.update(image)
            if not ok:self.lost=True;return None
            x,y,bw,bh=box
            crop=image[max(0,y):min(h,y+bh),max(0,x):min(w,x+bw)]
            if not crop.size:self.lost=True;return None
            hist=cv.calcHist([cv.cvtColor(crop,cv.COLOR_BGR2HSV)],[0,1],None,[16,8],[0,180,0,256]);cv.normalize(hist,hist)
            if cv.compareHist(self.template,hist,cv.HISTCMP_CORREL)<.35:self.lost=True;return None
        self.last_region={'id':-1,'label':'selected region','box':[max(0,x/w),max(0,y/h),min(bw/w,1-x/w),min(bh/h,1-y/h)],'confidence':.8}
        return self.last_region
