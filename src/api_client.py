import requests
import json, pickle
import os, re
import exceptions


class UserSession:

    def __init__(self):

        """ This class handles user sessions to a BeeLab database """

        # Server and database name
        # self.url_server = 'https://www.medusabci.com/api'
        self.url_server = 'http://localhost/api'

        # User data
        self.user_info = None

        # Session
        self.session = requests.Session()

    def check_session(self):
        """Checks if the session is valid and returns any exception thrown by
        the checking process"""
        # Check session
        if not isinstance(self, UserSession):
            raise TypeError()
        # Check connection with web
        self.ping()

    def ping(self):
        """Ping to MEDUSA API
        """
        # Parse URL
        url = self.url_server + '/ping/'
        # Make request
        try:
            resp = self.session.get(url, verify=True)
        except requests.exceptions.SSLError as e:
            resp = self.session.get(url, verify=False)
        # Error handling
        if resp.status_code != 200:
            if resp.status_code == 401:
                raise AuthenticationError()
            else:
                raise Exception("\n\n" + resp.text)

    def login(self, email, password):
        """Request to login to MEDUSA

        Parameters
        ----------
        email: str
            User email
        password: str
            User password
        """
        # Parse URL
        url = self.url_server + '/login/'
        # Make request
        params = {'email': email, 'password': password}
        data = json.dumps(params)
        # TODO: Solve problems with SSL if verify is True
        try:
            resp = self.session.post(url, json=data, verify=True)
        except requests.exceptions.SSLError as e:
            resp = self.session.post(url, json=data, verify=False)
        # Error handling
        if resp.status_code != 200:
            if resp.status_code == 401:
                raise AuthenticationError()
            else:
                raise Exception("\n\n" + resp.text)
        # Save user info
        self.user_info = json.loads(resp.content)

    def logout(self):
        """Request to logout from MEDUSA
        """
        # Parse URL
        url = self.url_server + '/logout/'
        # Make request
        resp = self.session.post(url)
        # Error handling
        if resp.status_code != 200:
            raise Exception("\n\n" + resp.text)

    def save(self):
        with open('session', 'wb') as f:
            pickle.dump(self, f)

    @staticmethod
    def load():
        with open('session', 'rb') as f:
            user_session = pickle.load(f)
        return user_session


class AuthenticationError(Exception):

    def __init__(self):
        super().__init__()