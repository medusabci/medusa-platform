from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *


class NotificationStack:

    def __init__(self, parent, anim_ms=1000, timer_ms=10000):
        self.parent = parent
        self.anim_ms = anim_ms
        self.timer_ms = timer_ms

        # Stack of notification labels
        self.notifications = []
        self.init_h = 10
        self.stacked_height = self.init_h

    def new_notification(self, message):
        # First delete notifications that are finished
        self.delete_finished_notifications()

        # Create a new notification on the top of the stack
        not_ = NotificationBubble(self.parent, message, offset_height=self.stacked_height, anim_ms=self.anim_ms, timer_ms=self.timer_ms)
        not_.start()
        self.notifications.append(not_)
        self.stacked_height = self.stacked_height + not_.get_height()

    def delete_finished_notifications(self):
        # Delete finished items
        for i in range(len(self.notifications)-1, -1, -1):
            if self.notifications[i].is_done:
                self.notifications.pop(i)

        # Calculate the stack height
        self.update_stack_height()

    def update_stack_height(self):
        self.stacked_height = self.init_h
        for not_ in self.notifications:
            self.stacked_height += not_.get_height()


class NotificationBubble(QLabel):

    def __init__(self, parent=None, message='Notification message', offset_height=0, anim_ms=1000, timer_ms=1000):
        super().__init__(text=message, parent=parent)

        # Important things
        self.is_done = False
        self.timer_ms = timer_ms
        self.anim_ms = anim_ms
        self.setObjectName('notification')  # For the stylesheet
        self.setMinimumSize(200, 50)        # Required to view the border
        # rounded

        # Compute the initial and target positions
        x_ = self.parent().rect().width()
        y_ = self.parent().rect().height()
        self.init_pos = QRect(x_-self.width(), y_, self.width(), self.height())
        self.target_pos = QRect(x_-self.width(), y_-self.height()-offset_height, self.width(), self.height())

        # Movement -IN animation
        self.anim_in_ = QPropertyAnimation(self, b"geometry")
        self.anim_in_.setDuration(self.anim_ms)
        self.anim_in_.setEasingCurve(QEasingCurve.InOutCubic)
        self.anim_in_.setStartValue(self.init_pos)
        self.anim_in_.setEndValue(self.target_pos)
        self.anim_in_.finished.connect(self.timer_start)

        # Movement -OUT animation
        self.anim_out_ = QPropertyAnimation(self, b"geometry")
        self.anim_out_.setDuration(self.anim_ms)
        self.anim_out_.setEasingCurve(QEasingCurve.InOutCubic)
        self.anim_out_.setStartValue(self.target_pos)
        self.anim_out_.setEndValue(self.init_pos)
        self.anim_out_.finished.connect(self.on_end)

    def get_height(self):
        return self.height()

    def start(self):
        self.show()
        self.anim_in_.start()

    def timer_start(self):
        self.timer_ = QTimer(self)
        self.timer_.timeout.connect(self.timer_timeout)
        self.timer_.start(self.timer_ms)

    def timer_timeout(self):
        self.is_done = True
        self.anim_out_.start()

    def on_end(self):
        self.hide()