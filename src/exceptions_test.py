import exceptions
import threading
import multiprocessing
import sys
import traceback
import resources
import time
from abc import ABC, abstractmethod
from PyQt5 import QtCore


class MedusaThread(threading.Thread):

    def __init__(self, name, medusa_interface=None, **th_kwargs):
        super().__init__(name=name, **th_kwargs)
        self.name = name
        self.medusa_interface = medusa_interface


class MedusaProcess(multiprocessing.Process):

    def __init__(self, name, medusa_interface=None, **pr_kwargs):
        super().__init__(name=name, **pr_kwargs)
        self.name = name
        self.medusa_interface = medusa_interface


def handle_exception(ex):
    print('CUSTOM EXCEPTION HANDLING')


@exceptions.error_handler()
def random_method():
    c = 0
    while True:
        if c > 2:
            raise Exception('Hi from random_method!')
        time.sleep(1)
        print('RandomProcess running ...')
        c += 1


class SomeRandomClassSkeleton(ABC):

    def __init__(self):
        pass

    @abstractmethod
    @exceptions.error_handler()
    def random_method(self):
        raise Exception('Hi from random_method!')


class SomeRandomClass(SomeRandomClassSkeleton):

    def __init__(self):
        super().__init__()

    def random_method(self):
        raise Exception('Hi from random_method!')


class SomeRandomClassThread(MedusaThread):

    def __init__(self):
        super().__init__(name='RandomThread')

    def handle_exception(self, ex):
        print('CUSTOM EXCEPTION HANDLING in SomeRandomClassThread')

    @exceptions.error_handler()
    def run(self):
        c = 0
        while True:
            if c > 2:
                self.random_method()
            time.sleep(1)
            print('RandomProcess running ...')
            c += 1

    def random_method(self):
        raise Exception('Hi from SomeRandomClassThread.random_method!')


class SomeRandomClassQThread(QtCore.QThread):

    def __init__(self):
        super().__init__()
        self.setObjectName('RandomQThread')

    def handle_exception(self, ex):
        print('CUSTOM EXCEPTION HANDLING in SomeRandomClassThread')

    @exceptions.error_handler()
    def run(self):
        c = 0
        while True:
            if c > 2:
                self.random_method()
            time.sleep(1)
            print('RandomProcess running ...')
            c += 1

    def random_method(self):
        raise Exception('Hi from SomeRandomClassThread.random_method!')


class SomeRandomClassProcess(MedusaProcess):
    def __init__(self):
        super().__init__(name='RandomProcess')

    @exceptions.error_handler()
    def run(self):
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

    # # Error in method
    # random_method()
    # print('\n\n==============================================================')
    # time.sleep(1)
    #
    # # Error in class
    cls = SomeRandomClass()
    cls.random_method()
    print('\n\n==============================================================')
    time.sleep(1)
    #
    # # Error in child thread
    # th = threading.Thread(target=random_method)
    # th.start()
    # th.join()
    # print('\n\n==============================================================')
    # time.sleep(1)
    #
    # Error in child thread with inheritance
    # th = SomeRandomClassThread()
    # th.start()
    # th.join()
    # print('\n\n==============================================================')
    # time.sleep(1)

    # Error in child thread with inheritance
    # th = SomeRandomClassQThread()
    # th.start()
    # th.wait()
    # print('\n\n==============================================================')
    # time.sleep(1)

    # Error in child process
    # pr = multiprocessing.Process(target=random_method)
    # pr.start()
    # pr.join()
    # print('\n\n==============================================================')
    # time.sleep(1)
    #
    # # Error in child process with inheritance
    # pr = SomeRandomClassProcess()
    # pr.start()
    # pr.join()




