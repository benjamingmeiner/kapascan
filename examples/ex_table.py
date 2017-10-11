from kapascan.table import Table

serial_port = '/dev/ttyACM0'

t = Table(serial_port)

with t:
    if t.get_status()[0] == 'Alarm':
        t.home()
    t.move(5, 5, 'absolute')
