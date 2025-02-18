from PyQt6.QtWidgets import QHBoxLayout, QWidget

__all__ = [
    'setup_layout',
]


def setup_layout(parent: QWidget) -> None:
    """Set up widget layout."""

    file_widget = QWidget()
    file_layout = QHBoxLayout(file_widget)

    file_layout.addWidget(parent.file_label)
    file_layout.addWidget(parent.load_button)
    file_layout.addWidget(parent.dump_title_button)
    file_layout.addWidget(parent.dump_all_titles_button)
    file_layout.addWidget(parent.info_button)

    parent.vlayout.addWidget(file_widget)
    parent.vlayout.addWidget(parent.tree_manager.tree)
    parent.vlayout.addWidget(parent.info_label)
    parent.vlayout.addSpacing(10)
    parent.vlayout.addWidget(parent.tree_manager.chapters_tree)
