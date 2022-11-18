import shutil, json, requests

import constants, exceptions
from gui.qt_widgets import dialogs


class UpdatesManager:

    """Class to manage updates in MEDUSA. It should distinguish patch updates
    (from v2022.0.0 to v2022.0.1) which are bug fixes and minor updates (from
    v2022.0.1 to v2022.1.0) which add features assuring apps compatibility.
    Things to consider:

        - Check shutil.copytree with dirs_exist_ok=True for updates
        - Having a file named version is probably a good idea to manage versions
    """

    def __init__(self, medusa_interface, release_info):
        # Attributes
        self.medusa_interface = medusa_interface
        self.release_info = release_info
        # Server and database name
        self.url_server = 'https://www.medusabci.com/api'
        # self.url_server = 'http://localhost/api'

    def handle_exception(self, ex):
        # Send exception to gui main
        self.medusa_interface.error(ex)

    def check_for_updates(self):
        # Check development
        if self.release_info['version'] == 'Dev':
            return
        # Check updates
        versions = \
            self.get_medusa_platform_versions(depth=0)
        latest_version = versions[self.release_info['version']]
        self.release_info['minor_patch'] = 0
        if int(latest_version['major_patch']) > \
                int(self.release_info['major_patch']):
            dialogs.confirmation_dialog(
                'MEDUSA Platform %s is out! You want to update?' %
                self.release_info['tag_name'], 'Major update available'
            )
        elif int(latest_version['minor_patch']) > \
                int(self.release_info['minor_patch']):
            dialogs.confirmation_dialog(
                'MEDUSA Platform %s is out! You want to update?' %
                self.release_info['tag_name'], 'Minor update available'
            )
        # TODO: Update medusa

    def get_medusa_platform_versions(self, depth=0):
        # Parse URL
        url = self.url_server + '/get-medusa-platform-versions/'
        # Make request
        params = {'depth': depth}
        data = json.dumps(params)
        try:
            resp = requests.get(url, json=data, verify=True)
        except requests.exceptions.SSLError as e:
            resp = requests.get(url, json=data, verify=False)
        # Response handling
        if resp.status_code == 200:
            return json.loads(resp.content)['versions']
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
