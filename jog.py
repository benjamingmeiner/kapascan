from msvcrt import getch
import os, sys
sys.path.append(os.getcwd())

import table

t = table.Table()
t.connect()

step=0.06
feed=100

while True:
    key = ord(getch())
    if key == 27: #ESC
        break
    elif key == 13: #Enter
        break
    elif key == 224: #Special keys (arrows, f keys, ins, del, etc.)
        key = ord(getch())
        if key == 80: #Down arrow
            t.jog(y=step, feed=feed)
        elif key == 72: #Up arrow
            t.jog(y=-step, feed=feed)
        elif key == 75: #Lef arrow
            t.jog(x=step, feed=feed)
        elif key == 77: #Right arrow
            t.jog(x=-step, feed=feed)

t.disconnect()
