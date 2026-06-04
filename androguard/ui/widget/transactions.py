import csv
import io

from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import AnyContainer
from prompt_toolkit.layout.dimension import AnyDimension, Dimension

from androguard.ui import table
from androguard.ui.selection import SelectionViewList
from androguard.ui.widget.frame import SelectableFrame

# import pyperclip




class TransactionFrame:

    def __init__(
        self, transactions: SelectionViewList, height: AnyDimension = None
    ) -> None:
        self.transactions = transactions
        self.transactions.on_update_event += self.update_table

        self.headings = [
            table.Label(""),
            table.Label("#"),
            table.Label("From"),
            table.Label("Method"),
        ]

        self.table = table.Table(
            table=[self.headings],
            # height=height,
            column_width=Dimension.exact(10),
            column_widths=[
                Dimension.exact(1),
                Dimension(min=2, preferred=4, max=4),
                Dimension(min=20, preferred=40),
                Dimension(min=20, preferred=30),
            ],
            borders=table.EmptyBorder,
        )

        self.pad_table()

        self.container = SelectableFrame(
            title="Transactions",
            body=self.get_content,
        )





    def key_bindings(self) -> KeyBindings:
        kb = KeyBindings()







        return kb


    # Define a "name" setter

    # def copy_to_clipboard(self):
    #    if self.transactions.selection_valid():
    #        output = io.StringIO()
    #        writer = csv.writer(output, quoting=csv.QUOTE_NONE)
    #        for t in self.transactions.data:
    #            writer.writerow([
    #                t.interface,
    #                str(t.method_number),
    #                t.method,
    #                hex(len(t.raw_data))
    #            ])
    #        pyperclip.copy(output.getvalue())


    def __pt_container__(self) -> AnyContainer:
        return self.container
