import traceback, sys, functools
import threading, multiprocessing
import warnings


# EXCEPTIONS IMPORTANCE
EXCEPTION_CRITICAL = 0      # CRITICAL ERROR. SHUT DOWN ORIGIN.
EXCEPTION_IMPORTANT = 1     # IMPORTANT ERROR WITH UNEXPECTED CONSEQUENCES.
EXCEPTION_HANDLED = 2       # CONTROLLED ERROR THAT HAS BEEN HANDLED.
EXCEPTION_UNKNOWN = 3       # ERROR WITH UNKNOWN CONSEQUENCES.


def error_handler(scope='app', medusa_interface=None,
                  handle_exception=None):
    """

    Parameters
    ----------
    scope: str
        Indicates the scope of the decorated method as defined in class
        MedusaException.
    medusa_interface: resources.MedusaInterface
        Current interface to medusa main gui
    handle_exception: callable
        Function that will be executed in case an exception is detected. It
        must have 1 (and only 1) parameter to pass the exception.

    Returns
    -------
    decorated_method: callable
        It returns the decorated method wiht automatic error handling
    """
    def inner(func):
        # if not isinstance(is_class_method, bool):
        #     raise ValueError('Parameter is_class_method must be boolean')
        if scope is not None and scope not in MedusaException.SCOPES:
            raise ValueError('Scope must be one of %s' %
                             str(MedusaException.SCOPES))

        @functools.wraps(func)
        def wrapper_decorator(*args, **kwargs):
            # Do something before
            try:
                value = func(*args, **kwargs)
                return value
            except Exception as ex:
                # Important variables
                curr_th = threading.current_thread()
                curr_pr = multiprocessing.current_process()
                scope_ = scope
                medusa_interface_ = medusa_interface
                handle_exception_ = handle_exception

                # Convert to MEDUSA exception
                if not isinstance(ex, MedusaException):
                    mds_ex = MedusaException(ex, importance=EXCEPTION_UNKNOWN,
                                             scope=scope_,
                                             origin=func.__qualname__)
                else:
                    mds_ex = ex

                # Check if the method is a class method
                if len(func.__qualname__.split('.')) > 1 and len(args) > 0:
                    # Get class and check the attributes
                    cls = args[0]
                    if hasattr(cls, 'scope'):
                        scope_ = cls.scope
                    if hasattr(cls, 'medusa_interface'):
                        medusa_interface_ = cls.medusa_interface
                    if hasattr(cls, 'handle_exception'):
                        handle_exception_ = cls.handle_exception

                # Print exception
                print('MEDUSA exceptions.error_handler report:',
                      file=sys.stderr)
                print('Exception in %s (process: %s) (thread: %s)' %
                      (func.__name__, curr_pr.name, curr_th.name),
                      file=sys.stderr)
                traceback.print_exc()

                # Operations
                if handle_exception_ is not None:
                    handle_exception_(mds_ex)
                    mds_ex.set_handled(True)
                if curr_th.name != 'MainThread' or \
                        curr_pr.name != 'MainProcess':
                    if medusa_interface_ is not None:
                        medusa_interface_.error(mds_ex)
                    else:
                        warnings.warn('The exception occurred on a child '
                                      'process and thread and medusa_interface '
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

    SCOPES = ['app', 'plots', 'log', 'general']

    def __init__(self, exception, importance=None, msg=None, scope=None,
                 origin=None):
        """Class constructor for

        Parameters
        ----------
        exception: Exception
            Original exception class
        msg: str or None
            Message of the exception. If None, Medusa will display the
            message of the original exception
        importance: int or None
            Importance of the exception. Depending of the importance,
            the main process take different actions. If None, the exception
            will be treated as critical. See module constants
            EXCEPTION_CRITICAL, EXCEPTION_IMPORTANT, EXCEPTION_HANDLED,
            EXCEPTION_UNKNOWN.
        scope: str or None {'app'|'plots'|'log'|'general'}
            Scope of the error. Must be None, 'app', 'plots' or 'general'. If
            None, Medusa will treat this error as general. Actions will be taken
            in the chosen scope. For instance, if the scope is 'app', medusa
            will terminate the current application if the importance is set
            to critical.
        origin: str or None
            Method that created the MedusaException instance. Ideally,
            this should be the same method that throws the original exception.
            It should contain as max info as possible.
            E.g., dev_app_qt/App.stop_run.
        """
        # Check errors, default values, etc
        if not isinstance(exception, Exception):
            raise ValueError('Parameter exception must be subclass of '
                             'Exception')
        if importance is None:
            importance = EXCEPTION_CRITICAL
        if scope is not None and scope not in self.SCOPES:
            raise ValueError('Scope must be one of %s' % str(self.SCOPES))
        # Set attributes
        self.exception = exception
        self.exception_type = type(exception)
        self.exception_msg = str(exception)
        self.traceback = traceback.format_exc()
        self.importance = importance
        self.msg = msg
        self.scope = scope
        self.origin = origin
        self.handled = False

    def get_msg(self, verbose=False):
        """Return the message of the exception. Some info can be added if
        verbose is True."""
        msg = self.msg if self.msg is not None else str(self.exception_msg)
        msg = ': %s' % msg if len(msg) > 0 else ''
        msg = self.exception_type.__name__ + msg
        if verbose:
            tab = ''.join(['&nbsp;' for i in range(6)])
            msg += ' [Scope: %s]' % (str(self.scope))
            msg += ' [Origin: %s]' % (str(self.origin))
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


