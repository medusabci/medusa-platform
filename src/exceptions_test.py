import exceptions
import threading
import multiprocessing
import sys
import traceback
import resources
import time
from abc import ABC, abstractmethod


class SomeRandomClass:

    exc_handler = exceptions.ExceptionHandler(None)

    def __init__(self):
        self.exc_handler = exceptions.ExceptionHandler(None)

    @exc_handler.method_excepthook
    def random_method(self):
        raise Exception('Hi from random_method!')


class SomeRandomClassThread(resources.MedusaThread):
    def __init__(self, exc_handler):
        super().__init__(exc_handler, name='RandomThread')

    def safe_run(self):
        c = 0
        while True:
            if c > 2:
                self.random_method()
            time.sleep(1)
            print('RandomProcess running ...')
            c += 1

    def random_method(self):
        raise Exception('Hi from SomeRandomClassThread.random_method!')


class SomeRandomClassProcess(resources.MedusaProcess):
    def __init__(self, exc_handler):
        super().__init__(exc_handler, name='RandomProcess')

    def safe_run(self):
        c = 0
        while True:
            if c > 2:
                self.random_method()
            time.sleep(1)
            print('RandomProcess running ...')
            c += 1

    def random_method(self):
        raise Exception('Hi from SomeRandomClassProcess.random_method!')


if __name__ == '__main__':

    exc_handler = exceptions.ExceptionHandler(None)

    cls = SomeRandomClass()
    cls.random_method()

    # Error in child thread
    # th = threading.Thread(target=random_method)
    # th.start()

    # Error in child thread with inheritance
    # th = SomeRandomClassThread()
    # th.start()
    # th.join()

    # Error in child process
    # pr = multiprocessing.Process(target=random_method)
    # pr.start()
    # pr.join()

    # Error in child process with inheritance
    # pr = SomeRandomClassProcess(exc_handler)
    # pr.start()
    # pr.join()





