import json, pickle, shutil
import os, re
import exceptions
from user_session import UserSession
from gui.qt_widgets import dialogs


class AccountsManager:

    ACCOUNTS_DIR = 'accounts'
    ACCOUNTS_PATH = '%s/accounts' % ACCOUNTS_DIR
    CURRENT_SESSION_PATH = '%s/session' % ACCOUNTS_DIR

    def __init__(self):
        if not os.path.isdir(self.ACCOUNTS_DIR):
            os.mkdir(self.ACCOUNTS_DIR)
        if os.path.isfile(self.ACCOUNTS_PATH):
            self.accounts = self.load_accounts()
        else:
            self.accounts = dict()
        if os.path.isfile(self.CURRENT_SESSION_PATH):
            self.current_session = self.load_session()
        else:
            self.current_session = UserSession()

    def wrap_path(self, path):
        """This function wraps the given path for the current session foler
        """
        if self.check_session():
            alias = self.current_session.user_info['alias']
            wrapped_path = '%s/%s/%s' % (self.ACCOUNTS_DIR, alias, path)
            return wrapped_path
        else:
            return False

    def check_session(self):
        check = True
        if self.current_session is None:
            check = False
        if self.current_session.user_info is None:
            check = False
        return check

    def on_login(self):
        alias = self.current_session.user_info['alias']
        if alias not in self.accounts:
            self.accounts['alias'] = self.current_session.user_info
            os.makedirs('%s/%s' % (self.ACCOUNTS_DIR, alias), exist_ok=True)
            self.save_accounts()
        self.save_session()

    def on_logout(self):
        self.current_session = UserSession()
        if os.path.isfile(self.CURRENT_SESSION_PATH):
            os.remove(self.CURRENT_SESSION_PATH)

    def on_delete_account(self):
        alias = self.current_session.user_info['alias']
        self.on_logout()
        shutil.rmtree('%s/%s' % (self.ACCOUNTS_DIR, alias))

    def save_session(self):
        with open(self.CURRENT_SESSION_PATH, 'wb') as f:
            pickle.dump(self.current_session, f)

    def load_session(self):
        with open(self.CURRENT_SESSION_PATH, 'rb') as f:
            session = pickle.load(f)
        return session

    def save_accounts(self):
        with open(self.ACCOUNTS_PATH, 'wb') as f:
            pickle.dump(self.accounts, f)

    def load_accounts(self):
        with open(self.ACCOUNTS_PATH, 'rb') as f:
            accounts = pickle.load(f)
        return accounts
