#!/usr/bin/python

import Image, ImageFont, ImageDraw
import os

(FILENAME, RES, BETATEXT, POSITION, FONTSIZE, TEMPLATE) = range(0,6)

class AnacondaImages:
    fontfile = None
    color = (255,255,255)

    mintextheight = 15
    textwidthbuffer = 2

    indir = None
    outdir = None

    image = None
    draw = None
    font = None
    text = None

    images = [
         #filename                  resolution      Beta?   position    size    template
        ["anaconda_header.png",     (800,58),       False,  (10,3),     30,     "background-800x58.png"],
        ["first-lowres.png",        (640,480),      True,   0.60,       40,     "background-640x480.png"],
        ["first.png",               (800,600),      True,   1.0,       40,     "background-800x600.png"],
        ["progress_first-375.png",  (353,170),      False,  0.80,       20,     "background-353x170.png"],
        ["progress_first.png",      (500,325),      False,  0.80,       40,     "background-500x325.png"],
        ["splash.png",              (400,420),      True,   1.0,       40,     "background-400x420.png"],
        ["syslinux-splash.png",     (640,300),      True,   (10,140),   20,     "background-640x300.png"]
    ]

    def __init__(self, text, indir='', outdir='', fontfile=''):
        self.text = text
        self.indir = indir
        self.outdir = outdir
        self.fontfile = fontfile

    def scaledSize(self, available, image):
        (ix, iy) = image.size
        (x,y) = available
        x = x - 2 * self.textwidthbuffer
        assert(y > self.mintextheight)
        if x < ix:
            #scale proportionally
            scalefactor = x / float(ix)
            if int(scalefactor * iy) < self.mintextheight:
                #Figure out the scale factor that would fit to max height
                scalefactor = self.mintextheight / float(iy)
            resimg = image.resize((int(ix*scalefactor), int(iy*scalefactor)), Image.BILINEAR)
            if resimg.size[0] > x:
                resimg = resimg.crop((0,0,x,resimg.size[1]))
            return resimg
        else:
            return image

    def centerInTopSection(self, topfraction, fill=None):
        if not fill:
            fill = self.color
        txtimage = self.font.getmask(self.text)
        x, y = self.image.size
        y = int(topfraction * y)
        im = self.image._new(self.scaledSize((x,y), txtimage))
        (tx, ty) = im.size
        posx = int((x - tx) / 2.0)
        posy = int((y - ty) / 2.0)
        self.image.paste(fill, (posx, posy, posx+im.size[0], posy+im.size[1]), mask=im)

    def processImages(self):
        for image in self.images:
            self.image = Image.open(os.path.join(self.indir,image[TEMPLATE]))
            if self.image.mode == 'P':
                color = 15 
            else:
                color = self.color
 
            self.draw = ImageDraw.Draw(self.image)
            self.font = ImageFont.truetype(self.fontfile, image[FONTSIZE])
            if(type(image[POSITION]) == tuple):
                self.draw.text(image[POSITION], self.text, font=self.font, fill=color)
            elif(type(image[POSITION]) == float):
                self.centerInTopSection(image[POSITION])
            self.image.save(os.path.join(self.outdir, image[FILENAME]))

