"""Contact sheets: sampled frames on one labelled image, for the AI models that watch the clip."""
import base64
import io


def contact_sheet(frames):
    """One labeled image avoids runtime-dependent merging of adjacent video frames."""
    if not frames: return []
    from PIL import Image, ImageDraw
    sheet=Image.new('RGB',(768,240*((len(frames)+1)//2)),(245,238,218))
    draw=ImageDraw.Draw(sheet)
    for i, frame in enumerate(frames):
        image=Image.open(io.BytesIO(base64.b64decode(frame['data']))).convert('RGB')
        image.thumbnail((384,216))
        x=(i%2)*384;y=(i//2)*240
        draw.text((x+6,y+5),f'Frame {i} | SOURCE {frame["at"]:.3f}s',fill=(45,30,20))
        sheet.paste(image,(x+(384-image.width)//2,y+24))
    output=io.BytesIO();sheet.save(output,format='JPEG',quality=80)
    return [base64.b64encode(output.getvalue()).decode()]
