from msvcrt import getch
import os, sys
sys.path.append(os.getcwd())

import table

t = table.Table()
t.connect()

s=0.06
f=100

while True:
    key = ord(getch())
    if key == 27: #ESC
        break
    elif key == 13: #Enter
        break
    elif key == 224: #Special keys (arrows, f keys, ins, del, etc.)
        key = ord(getch())
        if key == 80: #Down arrow
            t.jog(y=s, f=f)
        elif key == 72: #Up arrow
            t.jog(y=-s, f=f)
        elif key == 75: #Lef arrow
            t.jog(x=s, f=f)
        elif key == 77: #Right arrow
            t.jog(x=-s, f=f)

t.disconnect()
