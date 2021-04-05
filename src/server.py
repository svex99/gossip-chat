"""
Server that tracks when a new client join or left the network.
"""
import logging
import zmq


logging.basicConfig(
    format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s',
    level=logging.INFO
)


class Server:

    def __init__(self, interface, pport ,rport):
        self.clients = []
        self.ctx = zmq.Context()

        self.publisher = self.ctx.socket(zmq.PUB)        
        self.publisher.bind(f'tcp://{interface}:{pport}')
        
        self.receiver = self.ctx.socket(zmq.ROUTER)
        self.receiver.bind(f'{interface}:{rport}')
    

    def start(self):
        while True:
            cid = self.receiver.recv()
            data = self.receiver.recv_json()
            
            if cid not in self.clients:
                self.clients.append(cid)

            if data['online']:
                self.publisher.send_string(
                    '%s %s' % (
                        'update',
                        f'{data["ip"]}:{data["port"]}'
                    )
                )
            else: