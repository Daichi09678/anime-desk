"""Split actual AGY-generated sheets and prepare consistent animation frames."""

import argparse
import json
from pathlib import Path
from collections import deque

from PIL import Image, ImageDraw, ImageFilter

ROOT=Path(__file__).resolve().parents[1]
POSES=("idle","reading","thinking","explaining","talking","happy","surprised","tea","working","signature","stretch","sleepy")


def key_magenta(image):
    pixels=[]
    for r,g,b in image.convert("RGB").getdata():
        alpha=255
        if r>100 and b>100 and min(r,b)-g>65:
            alpha=max(0,255-round((min(r,b)-g-60)*2))
        if alpha < 16:
            alpha=0
            r=g=b=0
        if 0<alpha<255:
            a=alpha/255
            r=max(0,min(255,round((r-255*(1-a))/a)))
            b=max(0,min(255,round((b-255*(1-a))/a)))
            g=min(255,round(g/a))
            g=min(g,max(r,b)+5)
        pixels.append((r,g,b,alpha))
    result=Image.new("RGBA",image.size)
    result.putdata(pixels)
    # Remove disconnected remnants from the previous row of a generator sheet.
    data=result.getchannel("A").tobytes()
    visited=bytearray(len(data))
    largest=[]
    for start,value in enumerate(data):
        if value<16 or visited[start]:
            continue
        group=[]
        pending=deque([start])
        visited[start]=1
        while pending:
            index=pending.popleft()
            group.append(index)
            x,y=index%result.width,index//result.width
            for nx,ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if 0<=nx<result.width and 0<=ny<result.height:
                    other=ny*result.width+nx
                    if not visited[other] and data[other]>=16:
                        visited[other]=1
                        pending.append(other)
        if len(group)>len(largest):
            largest=group
    mask=bytearray(len(data))
    for index in largest:
        mask[index]=255
    support=Image.frombytes("L",result.size,bytes(mask)).filter(ImageFilter.MaxFilter(3))
    from PIL import ImageChops
    result.putalpha(ImageChops.multiply(result.getchannel("A"),support))
    # Chroma spill can remain on opaque antialiased outlines. Restrict the
    # correction to the two-pixel boundary so purple clothing stays intact.
    interior=result.getchannel("A").filter(ImageFilter.MinFilter(5))
    corrected=[]
    for (r,g,b,a),inside in zip(result.getdata(),interior.getdata()):
        if a and inside<200 and min(r,b)>g+20:
            spill=min(r,b)-g-20
            r-=spill
            b-=spill
        corrected.append((r,g,b,a))
    result.putdata(corrected)
    return result


def eyes(image, fullbody=False):
    w,h=image.size
    groups=[]
    for left,right in ((int(w*.36),int(w*.5)),(int(w*.5),int(w*.65))):
        points=[]
        for y in range(int(h*(.22 if fullbody else .35)),int(h*(.39 if fullbody else .56))):
            for x in range(left,right):
                r,g,b,a=image.getpixel((x,y))
                if a>200 and b>r+18 and b>g+8 and b>70:
                    points.append((x,y))
        if len(points)<3:
            return []
        groups.append((min(x for x,y in points),min(y for x,y in points),max(x for x,y in points),max(y for x,y in points)))
    return groups


def skin_patch(image, box):
    x0,y0,x1,y1=box
    x0,y0=max(0,x0),max(0,y0)
    x1,y1=min(image.width-1,x1),min(image.height-2,y1)
    region=Image.new("RGBA",(x1-x0,y1-y0))
    pixels=region.load()
    for y in range(region.height):
        for x in range(region.width):
            # Use intact skin above/below each column, not the lips at either
            # side. Horizontal sampling smeared dark mouth corners into a face.
            top=image.getpixel((x0+x,max(0,y0-2)))
            bottom=image.getpixel((x0+x,min(image.height-1,y1+2)))
            t=y/max(1,region.height-1)
            pixels[x,y]=tuple(round(top[c]*(1-t)+bottom[c]*t) for c in range(4))
    mask=Image.new("L",region.size,255)
    mask=mask.filter(ImageFilter.GaussianBlur(.5))
    image.paste(region,(x0,y0),mask)


def frames(image, mouth_box=None, fullbody=False):
    eye_boxes=eyes(image,fullbody)
    closed=image.copy()
    mouth=image.copy()
    if eye_boxes:
        for x0,y0,x1,y1 in eye_boxes:
            skin_patch(closed,(x0-4,y0-4,x1+5,y1+5))
            y=(y0+y1)/2+1
            points=[(x0-2,y),(x0+2,y+2),((x0+x1)/2,y+3),(x1-1,y+2),(x1+3,y-1)]
            ImageDraw.Draw(closed).line(points,fill="#493936",width=2,joint="curve")
        left,right=eye_boxes
        lx,ly=(left[0]+left[2])/2,(left[1]+left[3])/2
        rx,ry=(right[0]+right[2])/2,(right[1]+right[3])/2
        distance=rx-lx
        cx,cy=round((lx+rx)/2),round((ly+ry)/2+distance*.9)
        dark=[]
        for y in range(round((ly+ry)/2+distance*.45),min(image.height,round((ly+ry)/2+distance*1.35))):
            for x in range(max(0,cx-round(distance*.43)),min(image.width,cx+round(distance*.43))):
                r,g,b,a=image.getpixel((x,y))
                if a>200 and r>g+20 and r>b+5 and g<125 and b<150:
                    dark.append((x,y))
        candidates=[]
        remaining=set(dark)
        while remaining:
            start=remaining.pop()
            group=[start]
            queue=[start]
            while queue:
                x,y=queue.pop()
                for point in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                    if point in remaining:
                        remaining.remove(point)
                        group.append(point)
                        queue.append(point)
            x0,y0=min(x for x,y in group),min(y for x,y in group)
            x1,y1=max(x for x,y in group),max(y for x,y in group)
            if len(group)>5 and distance*.1 < x1-x0 < distance*.85 and y1-y0 < distance*.6:
                score=len(group)/(1+abs((x0+x1)/2-cx)/5)/(1+abs((y0+y1)/2-cy)/10)
                candidates.append((score,(x0,y0,x1,y1)))
        if mouth_box:
            x0,y0,x1,y1=mouth_box
            cx,cy=round((x0+x1)/2),round((y0+y1)/2)
            skin_patch(mouth,(x0,y0,x1,y1))
        elif candidates:
            x0,y0,x1,y1=max(candidates)[1]
            cx,cy=round((x0+x1)/2),round((y0+y1)/2)
            skin_patch(mouth,(x0-4,y0-4,x1+5,y1+5))
        else:
            skin_patch(mouth,(cx-round(distance*.4),cy-8,cx+round(distance*.4),cy+9))
        ImageDraw.Draw(mouth).arc((cx-5,cy-1,cx+5,cy+2),0,160,fill="#784c4b",width=1)
    mouth_blink=mouth.copy()
    for box in eye_boxes:
        x0,y0,x1,y1=box
        region=closed.crop((x0-5,y0-5,x1+6,y1+6))
        mouth_blink.paste(region,(x0-5,y0-5))
    # Facial edits never change silhouette/alpha or the body anchor.
    for frame in (closed,mouth,mouth_blink):
        frame.putalpha(image.getchannel("A"))
    return closed,mouth,mouth_blink


def build(identifier, fullbody=False):
    source=(ROOT/"assets/generated/beatrice_reference/beatrice_poses_v2.png" if fullbody else
            ROOT/"assets/generated/production"/("waguri_poses.png" if identifier=="waguri_kaoruko" else "beatrice_poses.png"))
    sheet=Image.open(source).convert("RGB")
    folder=ROOT/"assets/characters"/identifier/("production_reference" if fullbody else "production")
    folder.mkdir(parents=True,exist_ok=True)
    preview=Image.new("RGB",(1152,1792),"#252330")
    for index,name in enumerate(POSES):
        col,row=index%3,index//3
        bounds=(round(col*sheet.width/3),round(row*sheet.height/4),round((col+1)*sheet.width/3),round((row+1)*sheet.height/4))
        image=key_magenta(sheet.crop(bounds)).resize((352,352),Image.Resampling.LANCZOS)
        canvas=Image.new("RGBA",(384,448))
        canvas.alpha_composite(image,(16,80))
        if fullbody and name == "idle":
            portrait=key_magenta(Image.open(ROOT/"assets/generated/beatrice_reference/beatrice_fullbody.png"))
            portrait=portrait.crop(portrait.getbbox())
            portrait.thumbnail((320,288),Image.Resampling.LANCZOS)
            canvas=Image.new("RGBA",(384,448))
            canvas.alpha_composite(portrait,((384-portrait.width)//2,396-portrait.height))
        # Calibrated on the generated illustrations, not the reference portraits.
        mouth_boxes={
            "beatrice":{"talking":(178,209,200,225),"explaining":(180,209,203,225)},
            "waguri_kaoruko":{"talking":(177,205,204,225),"explaining":(169,207,197,222)},
        }
        blink,mouth,mouth_blink=frames(canvas,None if fullbody else mouth_boxes.get(identifier,{}).get(name),fullbody)
        if fullbody and name == "talking":
            # Calibrated at the final canvas size; edit just the lips, leaving
            # the face, gown and hand anchors untouched.
            mouth=canvas.copy()
            skin_patch(mouth,(190,156,202,164))
            ImageDraw.Draw(mouth).arc((192,159,199,161),0,160,fill="#78504a",width=1)
            mouth.putalpha(canvas.getchannel("A"))
            mouth_blink=mouth.copy()
        for suffix,frame in (("",canvas),("_blink",blink),("_mouth",mouth),("_mouth_blink",mouth_blink)):
            frame.save(folder/f"{name}{suffix}.png",optimize=True)
        preview.paste(canvas,(col*384,row*448),canvas)
    preview.save(folder/"preview.png",optimize=True)
    (folder/"manifest.json").write_text(json.dumps({"production":True,"source":str(source.relative_to(ROOT)).replace("\\","/"),
        "poses":list(POSES),"size":[384,448],"method":"new AGY image-generator illustration; chroma key and animation-frame preparation"},indent=2)+"\n",encoding="utf-8")
    print(identifier,len(POSES),"new illustrated poses prepared")


def build_frieren():
    folder=ROOT/"assets/characters/frieren/production"
    folder.mkdir(parents=True,exist_ok=True)
    idle=Image.open(ROOT/"assets/sprites/idle.png").convert("RGBA")
    mask=Image.new("L",idle.size)
    ImageDraw.Draw(mask).ellipse((205,153,244,179),fill=255)
    mask=mask.filter(ImageFilter.GaussianBlur(.7))
    for state in ("talking","talking_explain"):
        base=Image.open(ROOT/"assets/sprites"/f"{state}.png").convert("RGBA")
        blink_path=ROOT/"assets/characters/frieren/blink"/f"{state}.png"
        blink=Image.open(blink_path).convert("RGBA") if blink_path.is_file() else base.copy()
        for suffix,frame in (("_mouth",base.copy()),("_mouth_blink",blink)):
            frame.paste(idle,(0,0),mask)
            frame.putalpha(base.getchannel("A"))
            frame.save(folder/f"{state}{suffix}.png",optimize=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("character",choices=("beatrice","waguri_kaoruko","frieren"))
    parser.add_argument("--fullbody",action="store_true")
    args=parser.parse_args()
    build_frieren() if args.character=="frieren" else build(args.character,args.fullbody)
