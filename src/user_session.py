import requests
import json, pickle
import os, re
import exceptions


class UserSession:

    # TODO: Solve problems with SSL if verify is True
    # TODO: Handle connection error uniformly for all methods

    def __init__(self):

        """ This class handles user sessions to a BeeLab database """

        # Server and database name
        self.url_server = 'https://www.medusabci.com/api'
        # self.url_server = 'http://localhost/api'

        # User data
        self.user_info = None
        # Session
        self.session = requests.Session()

    def ping(self):
        """Ping to MEDUSA API to check connection and session
        """
        # Parse URL
        url = self.url_server + '/ping/'
        # Make request
        try:
            resp = self.session.get(url, verify=True)
        except requests.exceptions.SSLError as e:
            resp = self.session.get(url, verify=False)
        # Error handling
        if resp.status_code == 200:
            return True
        elif resp.status_code == 401:
            raise exceptions.AuthenticationError()
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
        try:
            resp = self.session.post(url, json=data, verify=True)
        except requests.exceptions.SSLError as e:
            resp = self.session.post(url, json=data, verify=False)
        # Response handling
        if resp.status_code == 200:
            self.user_info = json.loads(resp.content)
        elif resp.status_code == 401:
            raise exceptions.AuthenticationError()
        else:
            raise Exception("\n\n" + resp.text)

    def get_license_key(self, license_id):
        # Parse URL
        url = self.url_server + '/get-license-key/'
        # Make request
        params = {'license-id': license_id}
        data = json.dumps(params)
        try:
            resp = self.session.get(url, json=data, verify=True)
        except requests.exceptions.SSLError as e:
            resp = self.session.get(url, json=data, verify=False)
        # Response handling
        if resp.status_code == 200:
            return json.loads(resp.content)['license_key']
        elif resp.status_code == 401:
            raise exceptions.AuthenticationError(
                'You do not have permission to install this app, '
                'the bundle was not meant for you. Download '
                'it from the website using your account!')
        elif resp.status_code == 404:
            raise exceptions.NotFoundError(
                'This download is not licensed by MEDUSA. Please, '
                'download the app from the official website.'
            )
        else:
            raise Exception("\n\n" + resp.text)
