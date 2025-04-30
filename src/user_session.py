import requests
import json, pickle
import os, re
import exceptions


class UserSession:

    # TODO: Solve problems with SSL if verify is True
    # TODO: Handle connection error uniformly for all methods

    def __init__(self):
        """ This class handles user sessions"""

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
        """Login request to MEDUSA

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
            print("SSL verification failed. Retrying without verification...")
            resp = self.session.get(url, json=data, verify=False)
        except (ConnectionError, requests.exceptions.ConnectionError) as e:
            raise ConnectionError('Failed to connect to %s. Internet '
                                  'connection is required to perform this'
                                  ' operation' % self.url_server)
        # Response handling
        if resp.status_code == 200:
            return json.loads(resp.content)['license_key']
        elif resp.status_code in {400}:
            raise exceptions.AuthenticationError(
                "Access denied. You do not have permission to install this "
                "app because the license was issued for another user. Please "
                "download it from the official website using your account.")
        elif resp.status_code in {401}:
            raise exceptions.AuthenticationError(
                "Access denied. You do not have permission to install this "
                "app. Please download it from the official website using your "
                "account.")
        elif resp.status_code == 404:
            raise exceptions.NotFoundError(
                "This download is not licensed by MEDUSA. Please obtain "
                "the app from the official website.")
        else:
            raise Exception(f"Unexpected error from server "
                            f"({resp.status_code}): {resp.text}")

    def get_medusa_latest_version_of_apps(self, app_ids, target):
        # Parse URL
        url = self.url_server + '/get-medusa-apps-versions/'
        # Make request
        params = {'app_ids': app_ids,
                  'target': target}
        data = json.dumps(params)
        try:
            resp = self.session.post(url, json=data, verify=True)
        except requests.exceptions.SSLError as e:
            resp = self.session.post(url, json=data, verify=False)
        except (ConnectionError, requests.exceptions.ConnectionError) as e:
            return
        # Response handling
        if resp.status_code == 200:
            return json.loads(resp.content)['versions']
        else:
            raise Exception("\n\n" + resp.text)


