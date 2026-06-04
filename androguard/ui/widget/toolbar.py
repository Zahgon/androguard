from typing import Sequence

from prompt_toolkit.formatted_text import AnyFormattedText, FormattedText
from prompt_toolkit.layout.containers import AnyContainer, DynamicContainer
from prompt_toolkit.widgets import FormattedTextToolbar

from androguard.ui.widget.filters import FiltersPanel


class StatusToolbar:

    def __init__(self, transactions: Sequence, filters: FiltersPanel) -> None:
        self.transactions = transactions
        self.filters = filters
        self.container = DynamicContainer(self.toolbar_container)



    def __pt_container__(self) -> AnyContainer:
        return self.container
