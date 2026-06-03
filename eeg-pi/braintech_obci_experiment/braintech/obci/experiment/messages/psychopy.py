from braintech.obci.core.broker.messages.fields import Field
from braintech.obci.core.broker.messages.base import BaseMessage


class RunPsychopyExperiment(BaseMessage):
    script_path = Field(str)
    output_path_prefix = Field(str)


class PsychopyExperimentStarted(BaseMessage):
    pass


class PsychopyExperimentError(BaseMessage):
    details = Field(str)


class PsychopyExperimentFinished(BaseMessage):
    created_files = Field(list)
