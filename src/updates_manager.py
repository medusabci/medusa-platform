import os
import pathlib
import requests
import shutil
import tempfile
import zipfile
import sys

import exceptions
import utils
from gui.qt_widgets import dialogs
from PySide6.QtWidgets import *


class UpdatesManager:

    ZIPBALL_SIZE = 400

    def __init__(self, medusa_interface, platform_release_info,
                 kernel_release_info):
        # Attributes
        self.medusa_interface = medusa_interface
        self.platform_release_info = platform_release_info
        self.kernel_release_info = kernel_release_info
        # Server and database name
        self.url_server = 'https://www.medusabci.com/api'
        # self.url_server = 'http://localhost/api'
        # Check versions
        self.platform_versions_info = None
        self.kernel_versions_info = None
        self.update_available_versions()

    def handle_exception(self, ex):
        # Send exception to gui main
        self.medusa_interface.error(ex)

    def update_available_versions(self):
        # Get versions info
        try:
            self.platform_versions_info = \
                utils.get_medusa_repo_releases_info(
                    depth=0, repo='medusa-platform',
                    exclude_prereleases=False)
            self.kernel_versions_info = \
                utils.get_medusa_repo_releases_info(
                    depth=2, repo='medusa-kernel',
                    exclude_prereleases=False)
        except (ConnectionError, requests.exceptions.ConnectionError) as e:
            # If there is no connection, updates are not possible
            self.platform_versions_info = None
            self.kernel_versions_info = None

    def show_check_for_updates_dialog(self):
        dialog = self.CheckForUpdatesDialog()
        return dialog.exec(), not dialog.prereleases_checkbox.isChecked()

    def check_for_medusa_platform_updates(self, exclude_prereleases=True):
        # Check versions info (could be none if there is no internet connection)
        if self.platform_versions_info is None:
            return False, False, None
        # Check development
        if self.platform_release_info['version'] == 'Dev':
            return False, False, None
        # Check for updates
        latest_version_info = self.platform_versions_info[
            self.platform_release_info['version']]
        update = False
        rejected = False
        if latest_version_info['depth_2_tag'] > \
                self.platform_release_info['tag_name']:
            if latest_version_info['prerelease'] and exclude_prereleases:
                return False, False, latest_version_info
            dialog = self.UpdateAvailableDialog(
                'platform', self.platform_release_info, latest_version_info)
            update = dialog.exec()
            rejected = not update
        return update, rejected, latest_version_info

    def check_for_medusa_kernel_updates(self, exclude_prereleases=True):
        # Check versions info (could be none if there is no internet connection)
        if self.kernel_versions_info is None:
            return False, False, None
        # Check development
        if self.platform_release_info['version'] == 'Dev':
            return False, False, None
        # Get requirement of this version
        with open('../requirements.txt', 'r') as f:
            requirement = None
            for line in f:
                if line.find('medusa-kernel') == 0:
                    requirement = line.replace('medusa-kernel', '')
                    # It must have this format >=min_version<max_version
                    requirement = requirement.split('<')
                    min_version = requirement[0].replace('>=', '')
                    max_version = requirement[1]
                    break
            if requirement is None:
                print('The file requirements.txt has been corrupted. '
                      'Dependency medusa-kernel cannot be found.',
                      file=sys.stderr)
        # Check if there are updates available
        update = False
        rejected = False
        latest_version_info = None
        sorted_versions = sorted(self.kernel_versions_info)
        sorted_versions.reverse()
        for versionv in sorted_versions:
            version = versionv.replace('v', '')
            if self.kernel_release_info['tag_name'] >= version:
                continue
            # Check if this kernel version fits the requirements
            if min_version <= version < max_version:
                latest_version_info = version
                if latest_version_info['prerelease'] and exclude_prereleases:
                    return False, False, latest_version_info
                dialog = self.UpdateAvailableDialog(
                    'kernel', self.kernel_release_info, latest_version_info)
                update = dialog.exec()
                rejected = not update
                print(rejected)
                break
        return update, rejected, latest_version_info

    @exceptions.error_handler(scope='general')
    def update_platform(self, latest_version_info, progress_dialog):
        try:
            # Temp file
            temp_medusa_src_file = tempfile.TemporaryFile()
            mds_path = os.path.dirname(os.getcwd())
            # Get latest MEDUSA release
            uri = "https://api.github.com/repos/medusabci/" \
                  "medusa-platform/zipball/%s" % latest_version_info['tag_name']
            headers = {}
            # Download zip
            progress_dialog.update_action('Downloading files...')
            with requests.get(uri, headers=headers, stream=True) as r:
                # Download zip file and store in temp file
                bytes_down = 0
                total_bytes = int(r.headers['Content-Length']) \
                    if 'Content-Length' in r.headers else 0
                if total_bytes == 0:
                    total_bytes = 140 * 1e6
                progress_dialog.update_log('Download size: %.2f MB' %
                                           (total_bytes / 1e6))
                for data in r.iter_content(chunk_size=int(1e6)):
                    # Update progress bar
                    bytes_down += len(data)
                    progress_dialog.update_value(
                        int(bytes_down / total_bytes * 80))
                    # Save data
                    temp_medusa_src_file.write(data)
            # Extract zip
            progress_dialog.update_action('Extracting files...')
            progress_dialog.update_value(80)
            with zipfile.ZipFile(temp_medusa_src_file) as zf:
                zf_info_list = zf.infolist()
                root_path = zf_info_list[0].filename
                n_files = len(zf_info_list)
                file_counter = 0
                for zf_info_file in zf_info_list[1:]:
                    file_path = pathlib.Path(zf_info_file.filename)
                    rel_path = file_path.relative_to(root_path)
                    real_ext_path = os.path.normpath(
                        '%s/%s' % (mds_path, rel_path))
                    ext_path = zf.extract(zf_info_file, path=mds_path)
                    # Check if its a file that already exists and delete it
                    if os.path.isfile(real_ext_path):
                        try:
                            os.remove(real_ext_path)
                        except PermissionError as e:
                            continue
                    # Check if its a directory and continue
                    if os.path.isdir(real_ext_path):
                        continue
                    # Move file
                    shutil.move(ext_path, real_ext_path)
                    # Update progress dialog
                    file_counter += 1
                    progress_dialog.update_value(
                        int(80 + (file_counter/n_files*20)))
                shutil.rmtree('%s/%s' % (mds_path, root_path))
            # Close temp file
            temp_medusa_src_file.close()
            # Generate version file
            with open('%s/version' % mds_path, 'w') as f:
                f.write('\n'.join([latest_version_info['depth_2_tag'],
                                   latest_version_info['name'],
                                   latest_version_info['date']]))
            # Update progress bar
            progress_dialog.update_action('Finished')
            progress_dialog.update_value(100)
            progress_dialog.finish()
        except Exception as e:
            progress_dialog.update_log('ERROR: %s' % str(e), style='error')
            progress_dialog.finish()

    def update_kernel(self, requirement, progress_dialog):
        cmds = list()
        cmds.append('call "..\\venv\\Scripts\\activate"')
        cmds.append('python -m pip install --upgrade pip')
        cmds.append('pip install %s' % requirement)
        # Execute
        utils.execute_shell_commands(cmds, progress_dialog)
        progress_dialog.update_action('Finished')
        progress_dialog.update_value(100)
        progress_dialog.finish()

    class CheckForUpdatesDialog(dialogs.MedusaDialog):

        def __init__(self):
            super().__init__('Check for updates', width=None, heigh=None)

        def create_layout(self):
            main_layout = QVBoxLayout()
            # Label
            self.label = QLabel('Click Ok to check for updates.')
            main_layout.addWidget(self.label)
            # Check for pre-releases
            self.prereleases_checkbox = QCheckBox(
                "Check pre-releases (only for advanced users)")
            main_layout.addWidget(self.prereleases_checkbox)
            # Function buttons
            func_btn_layout = QHBoxLayout()
            func_btn_layout.addItem(
                QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))
            self.ok_btn = QPushButton('Ok')
            self.ok_btn.clicked.connect(self.on_ok_btn_clicked)
            func_btn_layout.addWidget(self.ok_btn)
            self.cancel_btn = QPushButton('Cancel')
            self.cancel_btn.clicked.connect(self.on_cancel_btn_clicked)
            func_btn_layout.addWidget(self.cancel_btn)
            main_layout.addLayout(func_btn_layout)
            return main_layout

        def on_ok_btn_clicked(self):
            self.accept()

        def on_cancel_btn_clicked(self):
            self.reject()

    class UpdateAvailableDialog(dialogs.MedusaDialog):

        def __init__(self, component_to_update, curr_version, latest_version):
            self.component_to_update = component_to_update
            self.curr_version = curr_version
            self.latest_version = latest_version
            super().__init__('Update available', width=None, heigh=None)

        def create_layout(self):
            main_layout = QVBoxLayout()
            # Main label
            if self.component_to_update == 'platform':
                info_msg = 'MEDUSA\u00A9 Platform %s is out! Do you want ' \
                           'to update?' % self.latest_version['tag_name']
            else:
                info_msg = 'MEDUSA\u00A9 Kernel %s is out! This version is ' \
                           'recommended for the current version of ' \
                           'MEDUSA\u00A9 Platform. Do you want to update?' % \
                           self.latest_version['tag_name']
            self.label = QLabel(info_msg)
            main_layout.addWidget(self.label)
            # What's new text browser
            if 'new' in self.latest_version['params']:
                self.text_browser = QTextBrowser(
                    self.latest_version['params']['new'])
                main_layout.addWidget(self.text_browser)
            # Automatic updates
            # self.disable_updates_checkbox = QCheckBox(
            #     "Disable automatic updates")
            # main_layout.addWidget(self.disable_updates_checkbox)
            # Function buttons
            func_btn_layout = QHBoxLayout()
            func_btn_layout.addItem(
                QSpacerItem(0, 0, QSizePolicy.Expanding,
                            QSizePolicy.Minimum))
            self.ok_btn = QPushButton('Ok')
            self.ok_btn.clicked.connect(self.on_ok_btn_clicked)
            func_btn_layout.addWidget(self.ok_btn)
            self.cancel_btn = QPushButton('Cancel')
            self.cancel_btn.clicked.connect(self.on_cancel_btn_clicked)
            func_btn_layout.addWidget(self.cancel_btn)
            main_layout.addLayout(func_btn_layout)
            return main_layout

        def on_ok_btn_clicked(self):
            self.accept()

        def on_cancel_btn_clicked(self):
            self.reject()