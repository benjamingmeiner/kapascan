from kapascan.logger import Logger

host = '192.168.254.51'
channel = 101

l = Logger(host)

with l:
    l.configure(channel)
    l.display("EXAMPLE")
    data = l.get_data()

print(data)
