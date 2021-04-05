import logging
import socket
import threading
import struct
import asyncio
import uuid
import random
import time

import zmq
import zmq.asyncio

from utils import ainput

logging.basicConfig(
    format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s',
    level=logging.INFO
)


class Client:

    def __init__(self, name: str, interface: str, port: str):
        self.name = name
        self.id = str(uuid.uuid4())
        self.pstop = 0.2

        self.spreading = True           # this client is spreading updates
        self.open_clients = {}          # clients awaiting for updates
        self.upd_received = []          # updates already received
        self.upd_not_acked = []         # updates sended by this client not acked
        self.queue = asyncio.Queue()    # queue for updates dispatching

        self.interface = interface
        self.port = port

        self.ctx = zmq.asyncio.Context()
        self.snder_sock = self.ctx.socket(zmq.DEALER)
        self.rcver_sock = self.ctx.socket(zmq.ROUTER)


    def discoverer(self):
        """
        Multicasting for network clients discovering.
        """
        MCAST_GRP = '224.1.1.1'
        MCAST_PORT = 2021
        IS_ALL_GROUPS = True
        MULTICAST_TTL = 2

        def notify_all():
            """
            Send multicast message.
            """
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, MULTICAST_TTL)

            try:
                sock.sendto(
                    f'open {self.id} {self.port}'.encode('utf8'),
                    (MCAST_GRP, MCAST_PORT)
                )
            except OSError as e:
                logging.error(e)

        def disc_receiver():
            """
            Receive multicast message.
            """
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            if IS_ALL_GROUPS:
                # on this port, receives ALL multicast groups
                sock.bind(('', MCAST_PORT))
            else:
                # on this port, listen ONLY to MCAST_GRP
                sock.bind((MCAST_GRP, MCAST_PORT))
            mreq = struct.pack("4sl", socket.inet_aton(MCAST_GRP), socket.INADDR_ANY)

            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

            while True:
                data, addr = sock.recvfrom(1024)
                state, id_, port = data.decode('utf8').split(' ')

                client = (addr[0], port)
                if id_ != self.id:
                    if state == 'open' and id_ not in self.open_clients:
                        self.open_clients[id_] = client
                    elif state == 'close' and id_ in self.open_clients:
                        self.open_clients.pop(id_)

        threading.Thread(target=disc_receiver, kwargs={}).start()
        while True:
            notify_all()
            time.sleep(1)

    async def dispatch(self):
        """
        Dispatch updates from the queue to all open clients.
        Posiblity pstop of stop updating clients.
        """
        while True:
            upd_id, name, text = await self.queue.get()
            logging.info(f'Dispatching update from {name}::{text}')

            self.spreading = True

            # logging.info(f'Open clients: {self.open_clients}')
            # logging.info(f'Updates received: {self.upd_received}')
            c = 0
            for oc_id in self.open_clients:
                oc = self.open_clients[oc_id]

                for _ in range(40):
                    if self.upd_not_acked:
                        await asyncio.sleep(0.1)
                    else:
                        break
                else:
                    # if the updates are not acked, remove all pendent
                    self.upd_not_acked = []

                if self.spreading:
                    self.snder_sock.connect('tcp://%s:%s' % oc)

                    self.upd_not_acked.append(upd_id)
                    await self.snder_sock.send_json(
                        {
                            'update': 1,
                            'cli_id': self.id,
                            'upd_id': upd_id,
                            'name': name,
                            'text': text
                        }
                    )

                    self.snder_sock.disconnect('tcp://%s:%s' % oc)
                    # logging.info(f'Dispatched to {oc}')
                    c += 1
                else:
                    break

            logging.info(f'Dispatched to {c}/{len(self.open_clients)} clients.')

            self.queue.task_done()
            self.upd_not_acked = []

    async def run_sender(self):
        """
        Receive input from console and put the update in queue for dispatching.
        """
        while True:
            text = (await ainput(''))[:-1]

            upd_id = str(uuid.uuid4())
            self.upd_received.append(upd_id)
            await self.queue.put((upd_id, self.name, text))

    async def run_receiver(self):
        """
        Await for messages from other clients.
        Message can be of two types: update or ack.
        If update -> respond with an ack acord to if update was new or not.
        If ack -> if ack is negative, try to stop updating
        """
        self.rcver_sock.bind('tcp://%s:%s' % (self.interface, self.port))
        logging.info(f'Listening in port {self.port}')

        while True:
            await self.rcver_sock.recv()
            data = await self.rcver_sock.recv_json()

            if 'update' in data and data['cli_id'] != self.id:    # is a potential update for this client
                url = 'tcp://%s:%s' % self.open_clients[data['cli_id']]
                self.snder_sock.connect(url)

                if data['upd_id'] in self.upd_received:  # already received this update
                    await self.snder_sock.send_json(
                        {
                            'ack': 0,
                            'upd_id': data['upd_id']
                        }
                    )
                else:   # update was new, make ack and put update in queue
                    print(f'[{data["name"]}] {data["text"]}')

                    await self.snder_sock.send_json(
                        {
                            'ack': 1,
                            'upd_id': data['upd_id']
                        }
                    )

                    if len(self.upd_received) > 200:
                        self.upd_received = self.upd_received[:100]
                    self.upd_received.append(data['upd_id'])

                    await self.queue.put((data['upd_id'], data['name'], data['text']))

                self.snder_sock.disconnect(url)
            elif 'ack' in data:   # is an ack for this client
                if not data['ack']:     # ack was negative
                    value = random.uniform(0, 1)
                    self.spreading = value > self.pstop
                    if not self.spreading:
                        logging.info(f'Updating stopped ({value})')

                if data['upd_id'] in self.upd_not_acked:
                    self.upd_not_acked.remove(data['upd_id'])

    def disconnect(self):
        """
        Close the client sockets
        """
        self.snder_sock.close()
        self.rcver_sock.close()

    def start(self, loop):
        loop.create_task(self.run_sender())
        loop.create_task(self.run_receiver())
        loop.create_task(self.dispatch())

        disc = threading.Thread(target=self.discoverer, kwargs={})
        disc.start()
        return disc

if __name__ == '__main__':
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument('--name', default='anon', help='This client name')
    parser.add_argument('--inter', default='all', help='Client interface. Use \'all\' for *')
    parser.add_argument('--port', help='Client port')
    args = parser.parse_args()

    args.inter = '*' if args.inter == 'all' else args.inter

    client = Client(
        name=args.name,
        interface=args.inter,
        port=args.port,
    )

    try:
        loop = asyncio.get_event_loop()
        disc = client.start(loop)
        loop.run_forever()
    except KeyboardInterrupt:
        disc._stop()
        client.disconnect()
        logging.info('Client stopped by user!')
