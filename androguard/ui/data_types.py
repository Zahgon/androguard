import datetime

from androguard.message import Message, MessageEvent, MessageSystem


class DisplayTransaction:

    def __init__(self, block: Message) -> None:
        self.block: Message = block
        self.timestamp = (datetime.datetime.now().strftime('%H:%M:%S'),)

    @property
    def index(self) -> int:
        return self.block.index









    def type(self) -> str:
        """Gets the type of the Block as a simple short string for use in pattern matching"""
        pass
