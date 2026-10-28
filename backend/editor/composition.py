"""Editor composition; extracted without changing media behavior."""
import math
from .models import Effects

def composition_geometry(source_width, source_height, settings):
    # Keep this rounding identical to editor_state.js. Ratios use even integer units.
    def even(value): return max(2, 2*math.floor(value/2+.5))
    width,height=even(source_width),even(source_height)
    if settings.ratio!='original':
        a,b=map(int,settings.ratio.split(':'))
        unit=even(max(source_width,source_height)/max(a,b)); width,height=a*unit,b*unit
    scale=(max if settings.mode=='fill' else min)(width/source_width,height/source_height)
    sw,sh=even(source_width*scale),even(source_height*scale)
    if settings.mode=='fill':
        sw,sh=max(width,sw),max(height,sh)
        x,y=2*math.floor((sw-width)*settings.x/2+.5),2*math.floor((sh-height)*settings.y/2+.5)
    else:
        sw,sh=min(width,sw),min(height,sh)
        x,y=2*math.floor((width-sw)/4),2*math.floor((height-sh)/4)
    return {'width':width,'height':height,'scaledWidth':sw,'scaledHeight':sh,'x':x,'y':y}


def composition_filter(geometry, settings):
    g=geometry
    filters=f"scale={g['scaledWidth']}:{g['scaledHeight']}:flags=lanczos,setsar=1"
    if settings.mode=='fill':
        return filters+f",crop={g['width']}:{g['height']}:{g['x']}:{g['y']}"
    return filters+f",pad={g['width']}:{g['height']}:{g['x']}:{g['y']}:color=0x{settings.background[1:]}"


def effects_filter(effects):
    # RGB LUT matches CSS brightness -> contrast -> saturate -> grayscale.
    if effects == Effects():
        return 'null'
    def lut(expression):
        return f"lutrgb=r='{expression}':g='{expression}':b='{expression}'"
    def saturation_matrix(amount):
        weights = [.213, .715, .072]
        names = ['r', 'g', 'b']
        matrix = ':'.join(f'{names[i]}{names[j]}={weights[j]*(1-amount)+(amount if i==j else 0)}' for i in range(3) for j in range(3))
        return 'colorchannelmixer=' + matrix
    filters = ['format=gbrp', lut(f'clip(val*{effects.brightness},0,255)'),
               lut(f'clip((val-127.5)*{effects.contrast}+127.5,0,255)'),
               saturation_matrix(effects.saturation)]
    if effects.grayscale:
        filters.append(saturation_matrix(0))
    return ','.join(filters)


def resolution_filter(width, height, resolution):
    """Cap the composed short side, preserving aspect ratio without upscaling."""
    if resolution == 'original':
        return 'null'
    factor = min(1, int(resolution[:-1]) / min(width, height))
    w, h = max(2, int(width * factor) // 2 * 2), max(2, int(height * factor) // 2 * 2)
    return f'scale={w}:{h}:flags=lanczos,setsar=1'
