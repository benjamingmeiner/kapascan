from kapascan.measurement import Measurement

host_controller = '192.168.254.173'
serial_port = '/dev/ttyACM0'
host_logger = '192.168.254.174'
settings = {
    'sensors': ['1739'],
    'logger_channel': 101,
    'sampling_time': 0.256,
    'data_points': 100,
    'mode': 'absolute',
    'direction': ('x', 'y'),
    'change_direction': True,
    'extent': ((4, 6, 0.5), (4, 5, 0.5))
    }

m = Measurement(host_controller, serial_port, host_logger, settings)

with m:
    x, y, z, T, t = m.scan()

print(x, y)
print(z)
print(T)
