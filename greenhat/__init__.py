import enum
import socket
import logging


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
            self.buffer[offset_id * WSIZE : offset_id * WSIZE + 1] = \
                data[:WSIZE]
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
            print('Dropping packet')
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
