import shutil, json, requests, os, sys, tempfile, zipfile, pathlib

import constants, exceptions
import utils
from gui.qt_widgets import dialogs


class UpdatesManager:

    """Class to manage updates in MEDUSA. It should distinguish patch updates
    (from v2022.0.0 to v2022.0.1) which are bug fixes and minor updates (from
    v2022.0.1 to v2022.1.0) which add features assuring apps compatibility.
    Things to consider:

        - Check shutil.copytree with dirs_exist_ok=True for updates
        - Having a file named version is probably a good idea to manage versions
    """

    ZIPBALL_SIZE = 400

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
        # Check for updates
        versions = utils.get_medusa_repo_releases_info(depth=0)
        latest_version = versions[self.release_info['version']]
        update = False
        if int(latest_version['major_patch']) > \
                int(self.release_info['major_patch']):
            update = dialogs.confirmation_dialog(
                'MEDUSA Platform %s is out! You want to update?' %
                self.release_info['tag_name'], 'Major update available'
            )
        elif int(latest_version['minor_patch']) > \
                int(self.release_info['minor_patch']):
            update = dialogs.confirmation_dialog(
                'MEDUSA Platform %s is out! You want to update?' %
                self.release_info['tag_name'], 'Minor update available'
            )

        if update:
            self.update_version(latest_version['tag_name'])

    def update_version(self, tag_name):
        # TODO: Update medusa
        # Download last release
        self.__update_medusa_source(tag_name)
        # Restar medusa
        utils.restart()
        pass

    def __update_medusa_source(self, tag_name):
        # Temp file
        temp_medusa_src_file = tempfile.TemporaryFile()
        mds_path = os.path.dirname(os.getcwd())
        # Get latest MEDUSA release
        uri = "https://api.github.com/repos/medusabci/" \
              "medusa-platform/zipball/%s" % tag_name
        headers = {}
        # Download zip
        with requests.get(uri, headers=headers, stream=True) as r:
            # Download zip file and store in temp file
            bytes_down = 0
            for data in r.iter_content(chunk_size=int(1e6)):
                bytes_down += len(data)
                # Update progress bar
                # pct = int(bytes_down / 1e6 / self.ZIPBALL_SIZE * 100)
                # self.update_progress_bar(
                #     "(1/4) Downloading MEDUSA %s (%i%%)..." %
                #     (self.mds_release_info['depth_0_tag'], pct),
                #     pct / 100 * 25)
                temp_medusa_src_file.write(data)
                print('%.2f MB' % (bytes_down / int(1e6)))
        # Extract zip
        with zipfile.ZipFile(temp_medusa_src_file) as zf:
            zf_info_list = zf.infolist()
            root_path = zf_info_list[0].filename
            for zf_info_file in zf_info_list[1:]:
                file_path = pathlib.Path(zf_info_file.filename)
                rel_path = file_path.relative_to(root_path)
                real_ext_path = os.path.normpath(
                    '%s/%s' % (mds_path, rel_path))
                # zf_info_file.filename = rel_path
                ext_path = zf.extract(zf_info_file, path=mds_path)
                shutil.move(ext_path, real_ext_path)
            shutil.rmtree('%s/%s' % (mds_path, root_path))
        # Close file
        temp_medusa_src_file.close()


