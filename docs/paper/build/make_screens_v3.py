"""Fig. 2 for the revised paper: crop the phone frame and empty background from the two
app screenshots, place them side by side with (a)/(b) labels and numbered callouts.
python make_screens_v3.py <out.png>"""
import sys
from PIL import Image, ImageDraw, ImageFont
F = "C:/Windows/Fonts/arialbd.ttf"
def crop(p, box):
    return Image.open(p).convert("RGB").crop(box)
# inner screen without bezel and status bar; cut the empty lower background
a = crop("screen_signin.png", (30, 95, 905, 1530))
b = crop("screen_role.png", (30, 230, 905, 1600))
h = max(a.height, b.height)
gap, pad, top = 70, 20, 90
W = a.width + b.width + gap + 2 * pad
canvas = Image.new("RGB", (W, h + top + pad), "white")
canvas.paste(a, (pad, top))
canvas.paste(b, (pad + a.width + gap, top))
d = ImageDraw.Draw(canvas)
lab = ImageFont.truetype(F, 54)
d.text((pad, 15), "(a) Sign-in", font=lab, fill="#0b0b0b")
d.text((pad + a.width + gap, 15), "(b) Role selection", font=lab, fill="#0b0b0b")
num = ImageFont.truetype(F, 40)
def callout(x, y, n):
    r = 30
    d.ellipse((x - r, y - r, x + r, y + r), fill="#eb6834", outline="white", width=4)
    w = d.textlength(str(n), font=num)
    d.text((x - w / 2, y - 23), str(n), font=num, fill="white")
# (a) 1 = Google sign-in button
callout(pad + 95, top + (1285 - 95), 1)
# (b) 2-4 = the three roles
bx = pad + a.width + gap + 95
for n, y in ((2, 795), (3, 1080), (4, 1365)):
    callout(bx, top + (y - 230), n)
canvas.save(sys.argv[1], dpi=(600, 600))
print(canvas.size)
