import json
from typing import Optional

from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (
    AnyContainer,
    Dimension,
    FormattedTextControl,
    HSplit,
    Window,
)
from prompt_toolkit.layout.dimension import AnyDimension

from androguard.ui.data_types import DisplayTransaction
from androguard.ui.selection import SelectionViewList
from androguard.ui.widget.frame import SelectableFrame


class DetailsFrame:
    def __init__(
        self, transactions: SelectionViewList, max_lines: int
    ) -> None:
        self.transactions = transactions
        self.max_lines = max_lines

        self.transactions.on_selection_change += self.update_content

        self.offset = 0

        self.container = SelectableFrame(
            title="Details",
            body=self.get_content,
            width=Dimension(min=56, preferred=100, max=100),
            height=Dimension(preferred=max_lines),
        )






    def __pt_container__(self) -> AnyContainer:
        return self.container
