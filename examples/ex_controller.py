from kapascan.controller import Controller

sensors = ['1739']
host = '192.168.254.173'

data_points = 10
mode = 'continuous'
sampling_time = 0.256

c = Controller(sensors, host)
with c:
    c.start_acquisition(data_points, mode, sampling_time)
    data = c.stop_acquisition()

print(data)
