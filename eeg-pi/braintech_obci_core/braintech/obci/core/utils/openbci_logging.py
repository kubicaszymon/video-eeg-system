# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

"""Module defines methods that return logger with set logging level. Change logging.INFO lines to change logging level.
"""
import copy
import functools
import inspect
import logging
import logging.config
import logging.handlers
import sys

LEVELS = {'debug': logging.DEBUG,
          'info': logging.INFO,
          'warning': logging.WARNING,
          'error': logging.ERROR,
          'critical': logging.CRITICAL}

MAX_FILE_SIZE_B = 1000000
LOG_BUFFER_SIZE_B = 5000
BACKUP_COUNT = 2
DEFAULT_LOG_PROPAGATION_LVL = "DEBUG"
DISABLE = 100


def enable_handlers(handler_names):
    root_logger = logging.getLogger()
    for name in handler_names:
        handler = logging._handlers.get(name, None)
        if handler and handler not in root_logger.handlers:
            root_logger.addHandler(handler)


def init_logging(logging_config):
    """
    Add obci specific log handlers to root logger.
    """
    from braintech.obci.core.conf import settings
    log_config = copy.deepcopy(logging_config)
    log_config.setdefault('version', 1)
    logging.config.dictConfig(log_config)
    try:
        logging.config.fileConfig(settings.parser, disable_existing_loggers=False)
    except KeyError:
        pass
    logging.getLogger('').debug("Using config :%s", logging_config.get('file', settings.module_path))


def get_logger(name, log_level='notset'):
    """Return logger with name as name and logging level p_level.

    :param: log_level: should be in (starting with the most talkactive):
    'debug', 'info', 'warning', 'error', 'critical'.
    """
    logger = logging.getLogger(name)
    if logger.level == logging.NOTSET:
        logger.setLevel(getattr(logging, log_level.upper()))
    return logger


get_dummy_logger = get_logger  # Backwards compatibility


def log_crash(func):
    """Crash information enhancing decorator."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            self = args[0]
            logger = getattr(self, '_logger', None) or getattr(self, 'logger', None)
            if logger:
                info = sys.exc_info()
                frames = inspect.getouterframes(info[2].tb_frame)
                extra_obj = _find_extra_obj(frames)

                msg = _crash_log_msg(func, args, kwargs, extra_obj, info, e)
                extra = {'data': {}, 'tags': {}}
                extra['data'].update(_crash_log_data(e, extra_obj))
                extra['tags'].update(_crash_log_tags(e, extra_obj))
                extra['culprit'] = caller_name(skip=2)
                logger.critical(msg, exc_info=True, extra=extra)
                del info
                del frames
            raise e

    return wrapper


def _find_extra_obj(frames):
    for frame in frames:
        arg_info = inspect.getargvalues(frame[0])
        if len(arg_info.args) > 0 and arg_info.args[0] == 'self':
            callee = arg_info.locals['self']
            if hasattr(callee, '_crash_extra_tags'):
                return callee
    return None


def _crash_log_tags(exception, callee):
    if hasattr(callee, '_crash_extra_tags'):
        return callee._crash_extra_tags(exception)
    else:
        return {}


def _crash_log_msg(func, args, kwargs, callee=None, exc_info=None, exception=None):
    msg = ' \n\n  CRASH INFO:\n'
    if exception:
        msg += "Peer crashed with exception %s\n" % str(exception)
    msg += "\nfunction/method  %s called with  args: %s" % (func, args)
    msg += "\n\nkwargs:  %s" % kwargs

    if hasattr(callee, '_crash_extra_description'):
        msg += "\n\n" + callee._crash_extra_description(exception)
    del exc_info
    return msg


def _crash_log_data(exception, callee):
    if hasattr(callee, '_crash_extra_data'):
        return callee._crash_extra_data(exception)
    else:
        return {}


def caller_name(skip=2):
    """
    Get a name of a caller in the format module.class.method`skip`.

    Specifies how many levels of stack to skip while getting caller name.

    :param  skip :  = 1 means "who calls me",
                    = 2"who calls my caller" etc.

    An empty string is returned if skipped levels exceed stack height
    copied from gist:  https://gist.github.com/techtonik/2151727
    """
    stack = inspect.stack()
    start = 0 + skip
    if len(stack) < start + 1:
        return ''
    parentframe = stack[start][0]

    name = []
    module = inspect.getmodule(parentframe)
    # `modname` can be None when frame is executed directly in console
    # TODO(techtonik): consider using __main__
    if module:
        name.append(module.__name__)
    # detect classname
    if 'self' in parentframe.f_locals:
        # I don't know any way to detect call from the object method
        # XXX: there seems to be no way to detect static method call - it will
        #      be just a function call
        name.append(parentframe.f_locals['self'].__class__.__name__)
    codename = parentframe.f_code.co_name
    if codename != '<module>':  # top level usually
        name.append(codename)  # function or a method
    del parentframe
    return ".".join(name)


logging.captureWarnings(True)
