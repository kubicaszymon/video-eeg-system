Video EEG
=========

.. _camera-protocol:

Camera communications protocol
------------------------------

BCI Framework Server has CameraServer class, which handles BCI Framework Launcher messages of type ``cam_control_msg`` without delays.
These messages are sent as ZMQ multipart messages to BCI Framework servers REP port (default at 12012).

Messages consist of two parts: header and data. Header is a string formatted as ``message_type_name^sender_optional^``.
For example: ``cam_control_msg^svarog^`` or ``cam_control^msg^^.

Second part of the message is message data which consists of serialized JSON.

``cam_control_msg`` is JSON dictionary with fields: ``action_name``, ``args``, ``receiver``, ``sender_ip``:

    * ``action_name`` is camera action name (a string)
    * ``args`` is optionally empty dictionary with action arguments e.g. {argname: argvalue}
    * ``receiver`` Optionally empty string, id or a name of message recipient
    * ``sender_ip`` Optionally empty string, IP or a hostname of the sender
This and other BCI Framework Launcher messages are defined in :py:mod`obci.core.messages.launcher_msg_types`.

Camera server will answer with messages:
``rq_error`` - JSON dictionary describing an error in field: ``details``
``rq_ok`` - JSON dictionary, in field ``params`` it will have data payload of methods results.
    
**Available actions:**

``find_cameras`` - no arguments required (``args`` should be an empty dict).
Returns ``rq_ok`` with JSON dictionary of dictionaries created from
:class:`~obci.drivers.video.base_camera.CameraDescription`.
CameraServer is constantly, in background, updating its camera list, this action returns immediately.
ex {'cam_id': **camera_dict**}. Camera in field ``available presets`` has a dictionary of presets
{'preset_id': **preset_dict**}.

``get_presets`` args: *cam_id*: string. Returns ``rq_ok`` with a JSON dictionary of dictionaries created from
:class:`~obci.drivers.video.base_camera.StreamPreset` of the given cam. On error returns message of
type ``rq_error`` with description.
ex {'preset_id': **preset_dict**}

``get_stream`` - args *cam_id*: string, *preset_id*: string, optional. Returns ``rq_ok`` with a JSON dictionary created
from :class:`~obci.drivers.video.base_camera.StreamPreset` with URL to the RTSP stream.
If there was a video stream running previously it might get stopped and new stream will be started.
If there was no stream running one will be started. If no preset_id is given returns best available stream.
On error returns message of type ``rq_error`` with error details.
You **have** to drop all streams which you've taken. For every ``get_stream`` action, you should do ``drop_stream``
action.

``drop_stream`` - args *cam_id*: string, *preset_id*: string.
Cleanup function, declares that stream ``preset_id`` on camera ``cam_id`` is no longer needed by this client and can
be stopped (if no one else needs it and it is possible).
Returns ``rq_ok``, on success (dropping stream, which was taken) and ``rq_error`` for any failure.

``get_running_streams`` - args: *cam_id*: string. Returns ``rq_ok`` with a dictionary of dicts based on
:class:`~obci.drivers.video.base_camera.StreamPreset` with all running streams for given camera
(format same as in ``get_presets``) or ``rq_error` when there is no such camera.


Additionally there are PTZ movement, focusing and nightvision actions for camera which support them.
Action names and arguments are the same as methods in :class:`~obci.drivers.video.base_camera.BaseCamera`,
but require additional argument: ``cam_id``.
For example, if one would like to pan camera completely left they would send a ``cam_control_msg`` with fields:
``"action_name": "absolute_pan", "args":{"x": -1, "cam_id": "ipcamonip"}``

Those commands will return ``rq_error`` message when such action is not available on given cam.
If camera supports this action ``rq_ok`` type message will be returned.


**CameraDescription and StreamPreset**

CameraDescription and StreamPreset is returned as JSON dictionary, with all public properties as fields.
``None``s are sent as JSON ``null``s.

**Example:**

Moving camera completely to right. One would send to REP port 12012 such multipart strings:

First part:
``cam_control_msg^^``

Second:
``{"action_name": "absolute_pan", "args":{"x": 1, "cam_id": "ipcamonip"}, "receiver": "", "sender_ip":"localhost"}``

if camera supports this action, it would return:

``rq_ok^^``
``{"receiver": "", "sender_ip": "", "status": "", "request": "", "params": ""}``

else it would return:

``rq_error``
``{"sender_ip": "", "receiver": "", "details": "Action not available", "err_code": "", "request": ""}``


Camera Saver
------------

Camera Saver is a peer which is added to an experiment to save video from some RTSP feed.
It is subscribed to Broker messages of type ``SAVE_VIDEO`` and ``FINISH_SAVING_VIDEO``.

**Available actions:**

``SAVE_VIDEO`` - message consisting of JSON dict with fields:
``URL``: string with RTSP video stream and ``PATH``: string where the video should be saved (with extension - mkv).
When video saving is in progress all ``SAVE_VIDEO`` messages will be ignored until ``FINISH_SAVING_VIDEO`` is received.
Peer answers with message ``SAVE_VIDEO_OK`` when video saving started succesfully with path to file in ``status`` JSON dict field.
Peer will return ``SAVE_VIDEO_ERROR`` with string of human readable details in ``details``
field of JSON dict and with path to file in ``status``.


When saving is in progress this peer will send ``SAVE_VIDEO_OK`` with path to file which is now saved every 10 seconds.


``FINISH_SAVING_VIDEO`` - empty message, stops recording session and finalizes files. Camera Saver peer 
Answers with message ``SAVE_VIDEO_DONE`` when video saving started succesfuly with path to file in ``status`` JSON dict
field and float fimestamp of first frame in ``ts``.
Can return ``SAVE_VIDEO_ERROR`` with details in ``details`` field of JSON dict and with path to file in ``status``.

