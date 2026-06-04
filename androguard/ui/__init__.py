import os
import queue

from loguru import logger
from prompt_toolkit import Application
from prompt_toolkit.application import get_app
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.layout import (
    ConditionalContainer,
    Float,
    FloatContainer,
    HSplit,
    Layout,
    UIContent,
    UIControl,
    VSplit,
    Window,
)
from prompt_toolkit.styles import Style

from androguard.message import Message
from androguard.ui.data_types import DisplayTransaction
from androguard.ui.filter import Filter
from androguard.ui.selection import SelectionViewList
from androguard.ui.widget.details import DetailsFrame
from androguard.ui.widget.filters import FiltersPanel
from androguard.ui.widget.help import HelpPanel
from androguard.ui.widget.toolbar import StatusToolbar
from androguard.ui.widget.transactions import TransactionFrame


class DummyControl(UIControl):
    """
    A dummy control object that doesn't paint any content.

    Useful for filling a :class:`~prompt_toolkit.layout.Window`. (The
    `fragment` and `char` attributes of the `Window` class can be used to
    define the filling.)
    """




class DynamicUI:
    def __init__(self, input_queue):
        logger.info("Starting the Terminal UI")
        self.filter: Filter | None = None

        self.input_queue = input_queue
        self.all_transactions = []

        self.transactions = SelectionViewList([], max_view_size=1)
        self.transaction_table = TransactionFrame(self.transactions)

        self.details_pane = DetailsFrame(self.transactions, 1)

        self.filter_panel = FiltersPanel()
        self.help_panel = HelpPanel()

        self.resize_components(os.get_terminal_size())

    def run(self):
        self.focusable = [self.transaction_table, self.details_pane]
        self.focus_index = 0
        self.focusable[self.focus_index].activated = True

        kb1 = KeyBindings()



        dummy_control = DummyControl()
        main_layout = HSplit(
            key_bindings=kb1,
            children=[
                self.transaction_table,
                VSplit(
                    [
                        self.details_pane,
                        #    self.structure_pane,
                    ]
                ),
                StatusToolbar(self.transactions, self.filter_panel),
                Window(content=dummy_control),
            ],
        )


        @Condition
        def show_filters():
            return self.filter_panel.visible

        @Condition
        def show_help():
            return self.help_panel.visible

        layout = Layout(
            container=FloatContainer(
                content=main_layout,
                floats=[
                    Float(
                        top=10,
                        content=ConditionalContainer(
                            content=self.filter_panel, filter=show_filters
                        ),
                    ),
                    Float(
                        top=10,
                        content=ConditionalContainer(
                            content=self.help_panel, filter=show_help
                        ),
                    ),
                ],
            )
        )

        style = Style(
            [
                ('field.selected', 'ansiblack bg:ansiwhite'),
                ('field.default', 'fg:ansiwhite'),
                ('frame.label', 'fg:ansiwhite'),
                ('frame.border', 'fg:ansiwhite'),
                ('frame.border.selected', 'fg:ansibrightgreen'),
                ('transaction.heading', 'ansiblack bg:ansigray'),
                ('transaction.selected', 'ansiblack bg:ansiwhite'),
                ('transaction.default', 'fg:ansiwhite'),
                ('transaction.unsupported', 'fg:ansibrightblack'),
                ('transaction.error', 'fg:ansired'),
                ('transaction.no_aidl', 'fg:ansiwhite'),
                ('transaction.oneway', 'fg:ansimagenta'),
                ('transaction.request', 'fg:ansicyan'),
                ('transaction.response', 'fg:ansiyellow'),
                ('hexdump.default', 'fg:ansiwhite'),
                ('hexdump.selected', 'fg:ansiblack bg:ansiwhite'),
                ('toolbar', 'bg:ansigreen'),
                ('toolbar.text', 'fg:ansiblack'),
                ('dialog', 'fg:ansiblack bg:ansiwhite'),
                ('dialog frame.border', 'fg:ansiblack bg:ansiwhite'),
                ('dialog frame.label', 'fg:ansiblack bg:ansiwhite'),
                ('dialogger.textarea', 'fg:ansiwhite bg:ansiblack'),
            ]
        )

        kb = KeyBindings()





        app = Application(
            layout,
            key_bindings=merge_key_bindings(
                [
                    kb,
                    self.transaction_table.key_bindings(),
                    # self.structure_pane.key_bindings(),
                    # self.hexdump_pane.key_bindings()
                ]
            ),
            full_screen=True,
            style=style,
        )
        app.before_render += self.check_resize

        app.run()


        # self.structure_pane.max_height = lower_panels_height
        # self.hexdump_pane.max_lines = lower_panels_height

    def get_available_blocks(self):
        blocks: list[Message] = []
        # Retrieve every unhandled block currently available in the queue
        try:
            for _ in range(10):
                blocks.append(self.input_queue.get_nowait())
        except queue.Empty:
            pass
        return blocks

    def process_data(self):
        blocks = self.get_available_blocks()
        # For every block...
        for block in blocks:
            block = DisplayTransaction(block)
            if not self.filter or self.filter.passes(block):
                self.transactions.append(block)

            self.all_transactions.append(block)

        return bool(blocks)
