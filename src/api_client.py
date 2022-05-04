import requests
import json, pickle
import os, re


class UserSession:

    def __init__(self):

        """ This class handles user sessions to a BeeLab database """

        # Server and database name
        self.url_server = 'http://www.medusabci.com/api'

        # Session
        self.session = requests.Session()

    def login(self, email, password):

        """Request to login to MEDUSA.

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
        resp = self.session.post(url, json=data)
        # Error handling
        if resp.status_code != 200:
            if resp.status_code == 401:
                raise AuthenticationError()
            else:
                raise Exception("\n\n" + resp.text)

    def logout(self):
        """Request to logout from MEDUSA.
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


class AuthenticationError(Exception):

    def __init__(self):
        super().__init__()