# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved
from braintech.obci.experiment.messages import LauncherMessageBase, Field


class SvarogStartSavingSignal(LauncherMessageBase):
    experiment_id = Field(str)
    signal_source_id = Field(str)
    signal_filename = Field(str)
    save_tags = Field(bool)
    video_filename = Field(str)
    video_stream_url = Field(str)
    save_impedance = Field(bool)
    append_timestamps = Field(bool)


class SvarogSavingSignalStarting(LauncherMessageBase):
    saving_session_id = Field(str)


class SvarogCheckSavingSignalStatus(LauncherMessageBase):
    saving_session_id = Field(str)


class SvarogSavingSignalStatus(LauncherMessageBase):
    saving_session_id = Field(str)
    status = Field(str)


class SvarogFinishSavingSignal(LauncherMessageBase):
    saving_session_id = Field(str)


class SvarogSavingSignalFinishing(LauncherMessageBase):
    saving_session_id = Field(str)


class SvarogSavingSignalError(LauncherMessageBase):
    saving_session_id = Field(str)
    details = Field(dict)


class OBCIServerCapabilitiesReq(LauncherMessageBase):
    pass


class OBCIServerCapabilities(LauncherMessageBase):
    capabilities = Field(list)
