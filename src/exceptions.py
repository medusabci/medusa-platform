import traceback, functools
import threading, multiprocessing
import warnings


def error_handler(def_importance=None, def_msg=None, def_scope=None,
                  def_origin=None, medusa_interface=None,
                  handle_exception=None):
    """Decorator to handle errors automatically within MEDUSA. This decorator
    must be used only as last resource, exceptions are better handled
    individually where they are raised!

    Parameters
    ----------
    def_importance: int or str
        Default importance of unhandled exceptions in the handler
    def_msg: str
        Default Message of the exception
    def_scope: str
        Indicates the default scope of the decorated method as defined in class
        MedusaException.
    def_origin: str
        Indicates the default origin of the exception. If None, it will be
        assigned automatically to the wrapped function __qualname__ attribute.
    medusa_interface: resources.MedusaInterface
        Current interface to medusa main gui. If the wrapped method is owned
        by a class with attribute medusa_interface, it will be used
        automatically.
    handle_exception: callable
        Function that will be executed in case an exception is detected. It
        must have 1 (and only 1) parameter to pass the exception. If the wrapped
        method is owned by a class with attribute handle_exception, it will
        be used automatically.

    Returns
    -------
    decorated_method: callable
        It returns the decorated method wiht automatic error handling
    """
    def inner(func):
        if def_scope not in MedusaException.SCOPES:
            raise ValueError('Scope must be one of %s' %
                             str(MedusaException.SCOPES))

        @functools.wraps(func)
        def wrapper_decorator(*args, **kwargs):
            # Do something before
            try:
                value = func(*args, **kwargs)
                return value
            except Exception as ex:
                # Get the current process and thread
                curr_th = threading.current_thread()
                curr_pr = multiprocessing.current_process()
                origin = func.__qualname__ if def_origin is None else def_origin
                medusa_interface_ = medusa_interface
                handle_exception_ = handle_exception
                importance_ = def_importance if def_importance is not None else \
                    MedusaException.IMPORTANCE_CODES['unknown']

                # Create MEDUSA exception if needed
                if not isinstance(ex, MedusaException):
                    mds_ex = MedusaException(
                        ex, importance=importance_, msg=def_msg, scope=def_scope,
                        origin=origin, process=curr_pr.name,
                        thread=curr_th.name)
                else:
                    mds_ex = ex

                # Check if the method is a class method
                if len(func.__qualname__.split('.')) > 1 and len(args) > 0:
                    # Get class and check the attributes
                    cls = args[0]
                    if medusa_interface_ is None and \
                            hasattr(cls, 'medusa_interface'):
                        medusa_interface_ = cls.medusa_interface
                    if handle_exception_ is None and \
                            hasattr(cls, 'handle_exception'):
                        handle_exception_ = cls.handle_exception
                # Handle exception
                if handle_exception_ is not None:
                    handle_exception_(ex)

                # Operations
                if mds_ex.thread != 'MainThread' or \
                        mds_ex.process != 'MainProcess':
                    if medusa_interface_ is not None:
                        medusa_interface_.error(mds_ex)
                    else:
                        warnings.warn('This exception occurred on a child '
                                      'process or thread and medusa_interface '
                                      'is None! This exception will not be '
                                      'passed to the main gui.')

        return wrapper_decorator

    return inner


class MedusaException(Exception):

    """This class must be used to communicate errors to the main process
    through the MedusaInterface (although it is not restricted to this scope).
    Qt throws errors asynchronously which are very difficult to locate
    afterwards.
    """

    IMPORTANCE_CODES = {
        'critical': 0,   # CRITICAL ERROR. SHUT DOWN ORIGIN
        'important': 1,  # IMPORTANT ERROR WITH UNKNOWN CONSEQUENCES
        'unknown': 2,    # ERROR WITH UNKNOWN CONSEQUENCES
    }
    SCOPES = ['app', 'plots', 'log', 'general']

    def __init__(self, exception, uid=None, importance=None, msg=None,
                 scope=None, origin=None, process=None, thread=None):
        """Class constructor for

        Parameters
        ----------
        exception: Exception
            Original exception class
         msg: int or str
            Unique identifier of the exception within a context
        msg: str or None
            Message of the exception. If None, Medusa will display the
            message of the original exception
        importance: int or str or None
            Importance of the exception. Depending of the importance,
            the main process take different actions. If None, the exception
            will be treated as unknown. Possible values {'critical'|'important'|
            'unknown'}.
        scope: str or None {'app'|'plots'|'log'|'general'}
            Scope of the error. Must be None, 'app', 'plots' or 'general'. If
            None, Medusa will treat this error as general. Actions will be taken
            in the chosen scope. For instance, if the scope is 'app', medusa
            will terminate the current application if the importance is set
            to critical.
        origin: str or None
            Qualified name of the exception origin.
        process: str or None
            Name of the process that thrown the exception
        thread: str or None
            Name of the thread that thrown the exception
        """
        # Check errors, default values, etc
        if not isinstance(exception, Exception):
            raise ValueError('Parameter exception must be subclass of '
                             'Exception')
        if importance is None:
            importance = self.IMPORTANCE_CODES['unknown']
        if isinstance(importance, str):
            importance = self.IMPORTANCE_CODES[importance]
        if scope is not None and scope not in self.SCOPES:
            raise ValueError('Scope must be one of %s' % str(self.SCOPES))
        # Set attributes
        self.exception = exception
        self.exception_type = type(exception)
        self.exception_msg = str(exception)
        self.traceback = traceback.format_exc()
        self.uid = uid
        self.importance = importance
        self.msg = msg
        self.scope = scope
        self.origin = origin
        self.process = process if process is not None else \
            multiprocessing.current_process().name
        self.thread = thread if thread is not None else \
            threading.current_thread().name
        self.handled = False

    def get_msg(self, verbose=False):
        """Return the message of the exception. Some info can be added if
        verbose is True."""
        msg = self.msg if self.msg is not None else str(self.exception_msg)
        msg = ': %s' % msg if len(msg) > 0 else ''
        msg = self.exception_type.__name__ + msg
        if verbose:
            tab = ''.join(['&nbsp;' for i in range(6)])
            msg += ' [Scope: %s]' % (str(self.scope)) \
                if self.scope is not None else ''
            msg += ' [Origin: %s]' % (str(self.origin)) \
                if self.origin is not None else ''
            msg += ' [Process: %s]' % (str(self.process)) \
                if self.process is not None else ''
            msg += ' [Thread: %s]' % (str(self.thread)) \
                if self.thread is not None else ''
        return msg

    def set_handled(self, handled):
        self.handled = handled


class LSLStreamNotFound(Exception):

    """Raise to indicate that there is no LSL stream that meet the search
    criteria
    """
    def __init__(self, prop_dict):
        """Class constructor

        Parameters
        ----------
        prop_dict: dict or string
            Dict with the properties that were compared with current LSL
            streams. If string, it is directly assigned to the exception
            message, which avoids problems with pickle to propagate the
            exception across processes using queues.
        """
        # TODO: check strange behaviour when the exception is propagated
        #  trough processes using medusa_interface (mp.queues)
        if isinstance(prop_dict, dict):
            self.prop_dict = prop_dict
            self.prop_list_str = ['%s: %s' % (k, v) for k, v
                                  in self.prop_dict.items()]
            if len(self.prop_list_str) > 0:
                msg = 'No matching LSL streams with %s' % \
                      ', '.join(self.prop_list_str)
            else:
                msg = 'No LSL streams available'
        else:
            msg = prop_dict
        super().__init__(msg)


class UnspecificLSLStreamInfo(Exception):

    """Raise to indicate that there is more than one LSL stream that meet the
    search criteria
    """
    def __init__(self, prop_dict):
        """Class constructor

        Parameters
        ----------
        prop_dict: dict or string
            Dict with the properties that were compared with current LSL
            streams. If string, it is directly assigned to the exception
            message, which avoids problems with pickle to propagate the
            exception across processes using queues.
        """
        # TODO: check strange behaviour when the exception is propagated
        #  trough processes using medusa_interface (mp.queues)
        if isinstance(prop_dict, dict):
            prop_list_str = ['%s: %s' % (k, v) for k, v in prop_dict.items()]
            msg = 'The number of streams with %s is greater than 1' %\
                  ', '.join(prop_list_str)
        else:
            msg = prop_dict

        super().__init__(msg)


class NoLSLStreamsAvailable(Exception):

    """Raise to indicate that there are no LSL streams available in this moment
    """
    def __init__(self, msg=None):
        """Class constructor

        Parameters
        ----------
        msg: string or None
            Custom message. This parameter avoids problems with pickle to
            propagate the exception across processes using queues.
        """
        # TODO: check strange behaviour when the exception is propagated
        #  trough processes using medusa_interface (mp.queues)

        if msg is None:
            msg = 'No LSL streams available. Configure LSL protocol ' \
                  'before this action.'
        super().__init__(msg)


class LSLStreamTimeout(Exception):

    """Raise to indicate that LSL timeout was triggered while receiving data
    """
    def __init__(self, msg=None):
        """Class constructor

        Parameters
        ----------
        msg: string or None
            Custom message. This parameter avoids problems with pickle to
            propagate the exception across processes using queues.
        """
        # TODO: check strange behaviour when the exception is propagated
        #  trough processes using medusa_interface (mp.queues)
        if msg is None:
            msg = 'LSL stream timeout. Check if amplifier is connected.'
        super().__init__(msg)


class IncorrectLSLConfig(Exception):

    """Raise to indicate that the current LSL config is invalid for an app or
    process
    """
    def __init__(self, msg=None):
        """Class constructor

        Parameters
        ----------
        msg: string or None
            Custom message. This parameter avoids problems with pickle to
            propagate the exception across processes using queues.
        """
        # TODO: check strange behaviour when the exception is propagated
        #  trough processes using medusa_interface (mp.queues)
        if msg is None:
            msg = 'The LSL configuration is incorrect.'
        super().__init__(msg)


def get_imp_code(code_str):
    return MedusaException.IMPORTANCE_CODES[code_str]


def importance_code_to_str(code):
    imp_codes = MedusaException.IMPORTANCE_CODES

    if code == imp_codes['critical']:
        return 'critical'
    elif code == imp_codes['important']:
        return 'important'
    elif code == imp_codes['handled']:
        return 'handled'
    elif code == imp_codes['unknown']:
        return 'unknown'
    else:
        raise ValueError('Unknown importance code')