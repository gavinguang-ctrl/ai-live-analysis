import socket

for port in range(8501, 8600):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", port)) != 0:
            print(port)
            break
else:
    print(8501)
