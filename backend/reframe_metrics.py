"""Wall-clock stage accounting; nested measurements are reported separately."""
from collections import defaultdict
from time import perf_counter

class Timings:
    def __init__(self):self.seconds=defaultdict(float);self.calls=defaultdict(int)
    def call(self,name,fn,*args,**kwargs):
        stamp=perf_counter()
        try:return fn(*args,**kwargs)
        finally:self.seconds[name]+=perf_counter()-stamp;self.calls[name]+=1
    def export(self):return {name:{'seconds':round(value,6),'calls':self.calls[name]} for name,value in self.seconds.items()}
