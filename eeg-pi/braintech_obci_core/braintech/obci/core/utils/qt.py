# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

""""Module contains useful methods when working with pyside2.

http://stackoverflow.com/questions/10991991/pyside-easier-way-of-updating-gui-from-another-thread
"""
# pylint: disable-all
from PySide2.QtCore import QEvent, QObject, QCoreApplication, QLocale, QTranslator, QLibraryInfo


class _InvokeEvent(QEvent):
    """Helper class for updating and running Gui in the main thread. Uses events."""

    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, fun, *args, **kwargs):
        """Initialize parameters."""
        QEvent.__init__(self, _InvokeEvent.EVENT_TYPE)
        self.fn = fun
        self.args = args
        self.kwargs = kwargs


class _Invoker(QObject):
    """Class invoking event."""

    def event(self, event):
        """Invoke event function with event parameters."""
        event.fn(*event.args, **event.kwargs)
        return True


_INVOKER = _Invoker()


def invoke_in_main_thread(fun, *args, **kwargs):
    """Invoke given function with parameters in the main thread."""
    QCoreApplication.postEvent(_INVOKER, _InvokeEvent(fun, *args, **kwargs))


def init_translation(app: QCoreApplication, locale: QLocale = None) -> None:
    """
    Initialize basic translations for application according to given locale or system locale.

    :param app: QCoreApplication
    :param locale: QLocale
    """
    if locale is None:
        locale = QLocale.system()
    translator = QTranslator(app)
    translator.load("qtbase_" + locale.name(), QLibraryInfo.location(QLibraryInfo.TranslationsPath))
    app.installTranslator(translator)
