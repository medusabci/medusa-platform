import traceback, sys, functools


# EXCEPTIONS IMPORTANCE
EXCEPTION_CRITICAL = 0      # CRITICAL ERROR. SHUT DOWN ORIGIN.
EXCEPTION_IMPORTANT = 1     # IMPORTANT ERROR WITH UNEXPECTED CONSEQUENCES.
EXCEPTION_HANDLED = 2       # CONTROLLED ERROR THAT HAS BEEN HANDLED.
EXCEPTION_UNKNOWN = 3       # ERROR WITH UNKNOWN CONSEQUENCES.


class ExceptionHandler:
    """ Class to handle exceptions within medusa
    """
    def __init__(self, medusa_interface):
        self.medusa_interface = medusa_interface
        self.scope = None

    def set_scope(self, scope):
        possible_scopes = ['app', 'plots', 'log', 'general']
        if scope is not None and scope not in possible_scopes:
            raise ValueError('Scope must be one of %s' % str(possible_scopes))
        self.scope = scope

    def handle_exception(self, ex):
        print('exceptions.ExceptionHandler:', file=sys.stderr)
        traceback.print_exc()

    def method_excepthook(self, func):
        @functools.wraps(func)
        def wrapper_decorator(*args, **kwargs):
            # Do something before
            try:
                value = func(*args, **kwargs)
                return value
            except Exception as ex:
                if not isinstance(ex, MedusaException):
                    ex = MedusaException(ex, importance=EXCEPTION_UNKNOWN,
                                         scope=self.scope,
                                         origin=func.__qualname__)
                self.handle_exception(ex)
        return wrapper_decorator

    def safe_excepthook(self, thread, ex):
        if not isinstance(ex, MedusaException):
            ex = MedusaException(ex, importance=EXCEPTION_UNKNOWN,
                                 scope=self.scope,
                                 origin=thread.name)
        self.medusa_interface.error(ex)


class MedusaException(Exception):

    """This class must be used to communicate errors to the main process
    through the MedusaInterface (although it is not restricted to this scope).
    Qt throws errors asynchronously which are very difficult to locate
    afterwards.
    """
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
        possible_scopes = ['app', 'plots', 'log', 'general']
        if scope is not None and scope not in possible_scopes:
            raise ValueError('Scope must be one of %s' % str(possible_scopes))
        # Set attributes
        self.exception = exception
        self.exception_type = type(exception)
        self.exception_msg = str(exception)
        self.traceback = traceback.format_exc()
        self.importance = importance
        self.msg = msg
        self.scope = scope
        self.origin = origin

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


