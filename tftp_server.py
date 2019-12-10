import threading
import socket
import argparse
import random
import asyncio

RRQ = 1
WRQ = 2
DATA = 3
ACK = 4
ERROR = 5

polling_rate = 0.010  # in seconds
default_timeout = 0.500  # in seconds
block_length = 512  # in Bytes


def main(loop, server_address, server_port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((server_address, server_port))
    sock.settimeout(0.0)  # non-blocking socket for udp. Only returns if data is available immediately.
    print('server started')
    coro_pool = []
    while True:
        try:
            (datagram, source) = sock.recvfrom(1024)
            try:
                pckt = unpack(datagram)
                if pckt.opcode == RRQ:
                    if pckt.filename == 'shutdown.txt':
                        break
                    else:
                        tmp = loop.create_task(RRQ_connection(pckt.filename, source))
                        coro_pool.append(tmp)
                elif pckt.opcode == WRQ:
                    tmp = loop.create_task(WRQ_connection(pckt.filename, source))
                    coro_pool.append(tmp)
                else:
                    sock.sendto(pack_error(5, "Target Port reserved for RRQ/WRQ. Errant packet?"), source)
            except TypeError as t:
                sock.sendto(pack_error(0, 'Malformed Packet'), source)
        except TimeoutError as t:
            await asyncio.sleep(polling_rate)  # I don't understand why sockets don't use this...
        except socket.timeout as t:
            await asyncio.sleep(polling_rate)  # ...
    ## Shutdown.txt has been reached. Time to die.
    for coro in coro_pool:
        pass  # I use this for todo.
        # shouldn't loop.run_until_complete perform the task completion on its own?
    sock.close()
    loop.stop()
    return


async def RRQ_connection(filename, address, mode='octet'):
    print("loop called. filename = " + filename)
    port = random.randrange(5000, 60000)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('127.0.0.1', port))  # system socket binding autocreation. I'm lazy.
    sock.settimeout(default_timeout)  # I should really write a wrapper for this...
    file = None
    block_number = 1
    block = 0
    is_binary = False
    timeouts = 0
    if mode == 'octet':
        fmode = 'rb'
        fcode = None
        is_binary = True
    elif mode == 'netascii':
        fmode = 'r'
        fcode = 'ascii'  # 'ascii'
    else:
        fmode = 'r'
        fcode = None
    try:
        file = open(filename, mode=fmode, encoding=fcode)
    except FileNotFoundError:
        print('Error: File Not Found: ' + filename)
        sock.sendto(pack_error(1, ''), address)
        sock.close()
        return
    # Now for the looop.
    print(str(address[0]) + ':' + str(address[1]))
    while True:
        datum = file.read(512)
        print('data len= ' + str(len(datum)))
        cow = pack_data(block_number, datum)
        print("sending file bit " + str(block_number))
        sock.sendto(cow, address)
        print("sent file with block=" + str(block_number))
        ack = None
        try:
            ack = await loop.sock_recv(sock, 1024)  # I wonder if timeout works like normal. I kinda need it to...
            block = unpack(ack).block
            print("received acknowledgement: " + str(block))
            timeouts = 0
            if block == block_number:
                block_number = block_number + 1
            else:
                # err... we got a previous ack.
                file.seek(-512, 1)  # so lazy, so bad... but I don't want to make an async state machine.
        except socket.timeout:
            if timeouts < 3:
                file.seek(-512, 1)
            else:
                sock.sendto(pack_error(0, "Timeout."), address)
        if len(datum) < 512:
            break
    #### End Loop ####
    file.close()
    sock.close()
    return


async def WRQ_connection(filename, address, mode='octet'):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', 0))  # system socket binding autocreation. I'm lazy.
    sock.settimeout(default_timeout)
    file = None
    block_number = 0
    if mode == 'octet':
        fmode = 'xb'
        fcode = None
    elif mode == 'netascii':
        fmode = 'x'
        fcode = 'ascii'
    else:
        fmode = 'x'
        fcode = None
    try:
        file = open(filename, mode=fmode, encoding=fcode)
    except:
        pass  # todo: error. Return.
    # Loopity Loop!
    ground_beef = 512  # how much data was last received. Loop control.
    timeout_count = 0
    while True:
        sock.sendto(pack_ack(block_number), address=address)  # Ack.
        if ground_beef < 512:
            break
        try:
            cow, buddy = sock.recvfrom(1024)
            beef = unpack(cow)

            file.write(beef.data)
            ground_beef = len(beef.data)
            block_number = block_number + 1
        except TimeoutError:
            if timeout_count < 3:
                pass
            else:
                break
    file.close()
    sock.close()
    return


class Packet:
    def __init__(self, opcode):
        self.opcode = opcode
        self.filename = None
        self.block = None
        self.data = None
        self.errorcode = None
        self.errmsg = None

    def to_bytes(self):
        tmp = None
        if self.opcode == WRQ or self.opcode == RRQ:
            tmp = b'' + self.opcode.to_bytes(2, byteorder='big') + b'\x00' + \
                  self.filename.encode('ascii') + b'\x00' + b'octet' + b'\x00'
            return tmp
        elif self.opcode == DATA:
            tmp = b'' + self.opcode.to_bytes(2, byteorder='big') + self.block.to_bytes(2, byteorder='big') + self.data
        elif self.opcode == ACK:
            tmp = b'' + self.opcode.to_bytes(2, byteorder='big') + self.block.to_bytes(2, byteorder='big')
        elif self.opcode == ERROR:
            pass
        else:
            raise Exception
        return tmp


def unpack(datagramaslamalam):  # returns a more useful packet object.
    try:
        opcode = int.from_bytes(datagramaslamalam[0:2], byteorder='big')
        pckt = Packet(opcode)
        if opcode == WRQ or opcode == RRQ:
            i = 2
            j = 2
            while datagramaslamalam[j] != 0:
                j = j + 1
            pckt.filename = datagramaslamalam[i:j].decode(encoding='ascii')
            i = j + 1
            j = i
            while datagramaslamalam[j] != 0:
                j = j + 1
            pckt.mode = datagramaslamalam[i:j].decode(encoding='ascii')
        elif opcode == ACK:
            pckt.block = int.from_bytes(datagramaslamalam[2:4], byteorder='big')
        elif opcode == DATA:
            pckt = Packet(opcode)
            pckt.block = int.from_bytes(datagramaslamalam[2:4], byteorder='big')
            pckt.data = datagramaslamalam[4:]
        elif opcode == ERROR:
            pckt.errorcode = int.from_bytes(datagramaslamalam[2:4], byteorder='big')
            i = 4
            j = 4
            while datagramaslamalam[j] != 0:
                j = j + 1
            pckt.errmsg = datagramaslamalam[i:j]
        return pckt
    except:
        raise TypeError


def pack_ack(seq):
    pckt = Packet(ACK)
    pckt.block = seq
    return pckt.to_bytes()


def pack_data(seq, data):
    tmp = b'\x00\x03' + seq.to_bytes(2, byteorder='big') + data
    return tmp


def pack_error(errorcode, errormessage):
    return (b'\x00\x05' + errorcode.to_bytes(2, byteorder='big') + errormessage.encode('ascii') + b'\x00')


parser = argparse.ArgumentParser(description='A server for TFTP, made by Scherza. Version 0.1 or something.')
parser.add_argument('-sp', type=int, required=False, default=69)

args = parser.parse_args()
server_port = args.sp

loop = asyncio.get_event_loop()
loop.call_soon(main, loop, '', server_port)
loop.run_forever()
loop.close()
