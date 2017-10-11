from kapascan.logger import Logger

host = '192.168.254.174'
channel = 101

data_logger = DataLogger(host)

with data_logger:
    data_logger.configure(channel)
    data_logger.display("EXAMPLE")
    data = data_logger.get_data()

print(data)
