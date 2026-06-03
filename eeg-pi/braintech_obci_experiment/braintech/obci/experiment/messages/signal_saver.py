from braintech.obci.core.broker.messages.fields import Field
from braintech.obci.core.broker.messages.base import BaseMessage


class StartSavingSignal(BaseMessage):
    save_file_path = Field(str)
    save_file_name = Field(str)


class SignalSavingStarted(BaseMessage):
    pass


class SignalSavingError(BaseMessage):
    details = Field(str)


class StopSavingSignal(BaseMessage):
    pass


class SavingSignalStopped(BaseMessage):
    pass
