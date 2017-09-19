from kapascan.controller import Controller

sensors = ['1739']
host = '192.168.254.173'

data_points = 10
mode = 'continuous'
sampling_time = 0.256

c = Controller(sensors, host)
with c:
    data = c.acquire(data_points, mode, sampling_time)

print(data)
