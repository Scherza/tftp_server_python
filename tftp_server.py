import asyncio
import socket
import argparse

RRQ = 1
WRQ = 2
DATA = 3
ACK = 4
ERROR = 5

polling_rate = 0.010 # in seconds
default_timeout = 0.500 # in seconds
block_length = 512 # in Bytes




async def main(server_address, server_port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((server_address, server_port))
    sock.settimeout(0.0) # non-blocking socket for udp. Basically, polling.
    while True:
        try:
            (datagram, source) = sock.recvfrom(1024)
            pckt = unpack(datagram)
            if pckt.opcode == RRQ:
                if pckt.filename == 'shutdown.txt':
                    break
                    pass
                else:
                    asyncio.create_task(RRQ_connection(pckt.filename, source))
            elif pckt.opcode == WRQ:
                asyncio.create_task(WRQ_connection(pckt.filename, source))
            else:
                sock.sendto(pack_error(5, "Target Port reserved for RRQ/WRQ. Errant packet?"), source)
        except TimeoutError as t:
            await asyncio.sleep(polling_rate)
        except TypeError as t:
            sock.sendto(pack_error(0, 'Malformed Packet'), source)
    ## Shutdown.txt has been reached. Time to die.
    sock.close()
    done, undone = await asyncio.wait(asyncio.all_tasks(), return_when=asyncio.ALL_COMPLETED) #finish up, before returning.
    return

async def RRQ_connection(filename, address, mode='octet'):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', 0)) #system socket binding autocreation. I'm lazy.
    sock.settimeout(0.0)
    file = None
    block_number = 1
    block = 0
    if mode == 'octet':
        fmode = 'rb'
        fcode = None
    elif mode == 'netascii':
        fmode = 'r'
        fcode = 'ascii'
    else:
        fmode = 'r'
        fcode = None
    try:
        file = open(filename, mode=fmode, encoding=fcode)
    except FileNotFoundError:
        pass #todo: Error. Return.
    # Now for the looop.
    while True:
        datum = file.read(512)
        cow = pack_data(block_number, datum)
        sock.sendto(cow, address=address)
        ack = None
        polls = 0
        while ack is None and polls < default_timeout:
            try:
                ack, frenchman = sock.recvfrom(1024)
                block = unpack(ack).block
            except TimeoutError:
                await asyncio.sleep(polling_rate)
                polls = polls + polling_rate
        if block == block_number:
            block_number = block_number + 1
        elif ack is None:
            file.seek(-512, 1) # we're just going to quit. Reason below.
            ## raise TimeoutError
        else:
            #err... we got a previous ack.
            file.seek(-512, 1) # so lazy, so bad... but I don't want to make an async state machine.
            return
        if len(datum) < 512:
            break
    #### End Loop ####
    file.close()
    sock.close()
    return

async def WRQ_connection(filename, address, mode='octet'):
    sock =socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', 0))  # system socket binding autocreation. I'm lazy.
    sock.settimeout(0.0)
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
        pass #todo: error. Return.
    # Loopity Loop!
    ground_beef = 512 # how much data was last received. Loop control.
    while True:
        sock.sendto(pack_ack(block_number), address=address) #Ack.
        block_number = block_number + 1
        if ground_beef < 512:
            break
        cow = None
        beef = None
        polls = 0
        while cow is None and polls < default_timeout:
            try:
                cow, buddy = sock.recvfrom(1024)
                beef = unpack(cow)
            except TimeoutError:
                await asyncio.sleep(polling_rate)
                polls = polls + polling_rate

        if beef is not None:
            file.write(beef.data)
            ground_beef = len(beef.data)
        elif beef is None:
            file.close()
            sock.close()
            return # Timeout. Wait...
            # raise TimeoutError
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
            tmp = b'' + self.opcode.to_bytes(2, byteorder='big') + b'\x00' +\
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

def unpack(datagramaslamalam): #returns a more useful packet object.
    try:
        opcode = int.from_bytes( datagramaslamalam[0:2], byteorder='big' )
        pckt = Packet(opcode)
        if opcode == WRQ or opcode == RRQ:
            i = 2
            j = 2
            while datagramaslamalam[j] != 0:
                j = j + 1
            pckt.filename = datagramaslamalam[i:j]
            i = j + 1
            j = i
            while datagramaslamalam[j] != 0:
                j = j + 1
            pckt.mode = datagramaslamalam[i:j]
        elif opcode == ACK:
            pckt.block = int.from_bytes( datagramaslamalam[2:4] , byteorder='big' )
        elif opcode == DATA:
            pckt = Packet(opcode)
            pckt.block = int.from_bytes( datagramaslamalam[2:4], byteorder='big' )
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

def pack_ack( seq ):
    pckt = Packet(ACK)
    pckt.block = seq
    return pckt.to_bytes()

def pack_data(seq, data):
    pckt = Packet(DATA)
    pckt.block = seq
    pckt.data = data
    return pckt.to_bytes()

def pack_error(errorcode, errormessage):
    return ( b'\x00\x05' + errorcode.to_bytes(2, byteorder='big') + errormessage.encode('ascii') + b'\x00' )


parser = argparse.ArgumentParser(description='A server for TFTP, made by Scherza. Version 0.1 or something.')
parser.add_argument('-sp', type=int, required=False, nargs=1, default=69)

args = parser.parse_args()
server_port = args.sp
asyncio.run(main('', server_port))
