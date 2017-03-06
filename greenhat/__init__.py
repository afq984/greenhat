import enum
import struct
import socket
import logging
import itertools


logger = logging.getLogger(__name__)


WSIZE = 1444


class Screen(enum.IntEnum):
    BOT = 0
    TOP = 1


class Frame:
    def __init__(self):
        self.buffer = bytearray(1440 * 140 * 3)
        self.reset()

    def reset(self):
        self.frame_id = None
        self.count = None
        self.received = 0
        self.size = 0

    @property
    def is_complete(self):
        if self.count is None:
            return False
        else:
            if self.received + 1 == 1 << self.count:
                return True
            else:
                return False

    def handle_packet(self, frame_id, is_last, format, offset_id, data):
        self.frame_id = frame_id
        if is_last:
            self.count = offset_id + 1
        bitmark = 1 << offset_id
        if not self.received & bitmark:
            self.received |= bitmark
            offset = offset_id * WSIZE
            self.buffer[offset:offset + WSIZE] = data[:WSIZE]
            self.size = len(data) + offset_id * WSIZE

    def id_diff(self, other_id):
        if self.frame_id is None:
            return 0
        return (other_id - self.frame_id) % 256

    def to_bytes(self):
        return bytes(self.buffer[:self.size])


class Channel:
    def __init__(self):
        self.last_frame = Frame()
        self.next_frame = Frame()

    def handle_packet(self, *args):
        frame_id, is_last, format, offset_id, data = args
        last_diff = self.last_frame.id_diff(frame_id)
        retval = None
        if last_diff == 0:
            self.last_frame.handle_packet(*args)
            if self.last_frame.is_complete:
                retval = self.last_frame.to_bytes()
                self.last_frame, self.next_frame = (
                    self.next_frame, self.last_frame)
                self.next_frame.reset()
        elif last_diff == 1:
            self.next_frame.handle_packet(*args)
            if self.next_frame.is_complete:
                retval = self.next_frame.to_bytes()
                self.last_frame.reset()
                self.next_frame.reset()
                self.last_frame.frame_id = frame_id + 1
        elif last_diff < 7:
            self.last_frame.reset()
            self.next_frame.reset()
            self.last_frame.handle_packet(*args)
        else:
            logging.warning('dropping packet %i-%i', frame_id, offset_id)
        return retval


class PacketHandler:
    buff_size = 8 * 1024 * 1024

    def __init__(self, *, timeout=None):
        '''
        timeout - timeout passed to the underlying socket
        '''
        self.socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
            socket.IPPROTO_UDP
        )
        self.socket.setsockopt(
            socket.SOL_SOCKET, socket.SO_RCVBUF, self.buff_size)
        self.socket.settimeout(timeout)
        self.socket.bind(('', 8001))
        self.buffer = bytearray(2000)
        self.view = memoryview(self.buffer)

        self.channels = [Channel(), Channel()]

    def recv_packet(self):
        '''
        Receive a packet and return a tuple of ``(screen, image)``

        ``screen`` will be either ``Screen.TOP`` or ``Screen.BOT``

        ``image`` will be the JPEG binary if a new image is available on
        the received frame, or ``None`` otherwise.

        Raises ``socket.timeout`` if no packet arrives on time.
        '''
        nbytes, address = self.socket.recvfrom_into(self.buffer)
        frame_id, last_top, format, offset_id = self.view[:4]
        is_top = Screen(last_top & 1)
        is_last = last_top & 0x10

        image = self.channels[is_top].handle_packet(
            frame_id, is_last, format, offset_id, self.view[4:])
        return is_top, image

    def close(self):
        self.socket.close()


def pad(iterable, value, count):
    return itertools.islice(
        itertools.chain(iterable, itertools.repeat(value)), count)


class Client:
    struct = struct.Struct('<' + 'I' * (5 + 16))
    port = 8000

    def __init__(self, ip):
        self.ip = ip
        self.socket = None
        self.current_seq = 0

    def send_packet(self, type, cmd, args, data_len):
        self.current_seq += 1000
        data = self.struct.pack(
            0x12345678,
            self.current_seq,
            type,
            cmd,
            *pad(args, 0, 16),
            data_len
        )
        self.socket.sendall(data)

    def send_empty_packet(self, cmd, *args):
        assert len(args) < 4, len(args)
        self.send_packet(0, cmd, args, 0)

    def send_write_mem_packet(self, addr, pid, buf):
        assert isinstance(buf, (bytes, bytearray))
        self.send_packet(1, 10, [pid, addr], len(buf))
        self.socket.sendall(buf)

    def connect(self):
        logger.info('connecting to tcp://%s:%d', self.ip, self.port)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.ip, 8000))
        logger.info('connected to tcp://%s:%d', self.ip, self.port)

    def disconnect(self):
        self.socket.close()
        logger.info('disconnect from tcp://%s:%d', self.ip, self.port)

    def remoteplay(
            self,
            screen_priority=1,
            priority_factor=5,
            quality=90,
            qos=101):
        self.connect()
        self.send_empty_packet(
            901, screen_priority << 8 | priority_factor,
            quality,
            int(qos * 1024 * 1024 / 8)
        )
        self.disconnect()

    def patch_wifi(self):
        self.connect()
        self.send_write_mem_packet(0x0105AE4, 0x1a, bytes((0x70, 0x47)))
        self.disconnect()
