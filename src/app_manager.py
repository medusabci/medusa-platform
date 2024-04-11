# BUILT-IN MODULES
import glob
import json
import os
import re
import shutil
import tempfile
import threading
import time
import zipfile
from datetime import datetime
from io import BytesIO

import pkg_resources
from cryptography.fernet import Fernet
# EXTERNAL MODULES
from jinja2 import Template

# INTERNAL MODULES
import constants
import exceptions
import utils


class AppManager:

    def __init__(self, accounts_manager, medusa_interface, release_info):
        # Get installed apps
        self.accounts_manager = accounts_manager
        self.medusa_interface = medusa_interface
        self.release_info = release_info
        self.apps_config_file_path = self.accounts_manager.wrap_path(
            constants.APPS_CONFIG_FILE)
        self.apps_folder = self.accounts_manager.wrap_path('apps')
        self.apps_dict = None
        # Load apps file
        self.load_apps_file()
        # Check apps updates
        self.check_updates()

    def handle_exception(self, ex):
        # Send exception to gui main
        self.medusa_interface.error(ex)

    def load_apps_file(self):
        if os.path.isfile(self.apps_config_file_path):
            with open(self.apps_config_file_path, 'r') as f:
                self.apps_dict = json.load(f)
        else:
            self.apps_dict = {}

    def update_apps_file(self):
        with open(self.apps_config_file_path, 'w') as f:
            json.dump(self.apps_dict, f, indent=4)

    def get_date_today(self):
        return datetime.today().strftime('%Y-%m-%d %H:%M:%S')

    def check_app_dependencies(self, app_dir):
        # Get requirements
        req_path = os.path.normpath('%s/requirements.txt' % app_dir)
        # Get installed packages
        current_pkgs = dict()
        for p in pkg_resources.working_set:
            current_pkgs[p.project_name] = p.version
        # Get app requirements
        with open(req_path, 'r') as f:
            app_reqs_txt = f.read()
        app_reqs_ = app_reqs_txt.replace(' ', '').split('\n')
        app_reqs = dict()
        for r in app_reqs_:
            if r == '':
                continue
            req = re.split('<|<=|!=|==|>=|>|~=|===', r)
            app_reqs[req[0]] = req[1] if len(req) > 1 else None
        # Check if there are something to install
        if len(app_reqs) == 0:
            return 'not-required'
        # Check requirements
        confirmation = list()
        for req_name, req_version in app_reqs.items():
            if req_name in current_pkgs:
                curr_ver = current_pkgs[req_name]
                app_ver = app_reqs[req_name]
                if curr_ver != app_ver:
                    msg = """Package %s with version %s is already installed, 
                    but the required version for this app is %s""" \
                          % (req_name, curr_ver, app_ver)
                    self.medusa_interface.log(msg, style='warning')
                    confirmation.append(False)
                else:
                    confirmation.append(True)
            else:
                confirmation.append(True)
        return 'conflict' if not all(confirmation) else 'proceed'

    def install_app_dependencies(self, app_dir):
        # Get medusa and requirements paths
        mds_path = '\\'.join(os.path.abspath(__file__).split('\\')[:-2])
        req_path = os.path.normpath('src/%s/requirements.txt' % app_dir)
        # Check dependencies
        check = self.check_app_dependencies(app_dir)
        if check == 'proceed':
            # Write bat file with the commands to install python dependencies
            cmds = list()
            cmds.append('%s:' % mds_path.split(':')[0])
            cmds.append('cd "%s"' % mds_path)
            cmds.append('call "venv\\Scripts\\activate"')
            cmds.append('pip install -r %s' % req_path)
            # Execute
            utils.execute_shell_commands(cmds)
        elif check == 'conflict':
            msg = """The dependencies were not installed to avoid conflicts
             between apps. You'll need to handle them manually if necessary"""
            self.medusa_interface.log(msg, style='warning')
        else:
            pass

    def install_app_bundle(self, bundle_path, progress_dialog):
        try:
            # Install app (extract zip)
            progress_dialog.update_action('Checking license...')
            progress_dialog.update_value(0)
            with zipfile.ZipFile(bundle_path) as bundle:
                token = bundle.read('token').decode()
                license_key = \
                    self.accounts_manager.current_session.get_license_key(token)
                f = Fernet(license_key)
                app = BytesIO(f.decrypt(bundle.read('app')))
                with zipfile.ZipFile(app) as app_zf:
                    progress_dialog.update_action('Extracting app...')
                    progress_dialog.update_value(5)
                    with tempfile.TemporaryDirectory() as temp_dir:
                        # Extract app files
                        n_files = len(app_zf.namelist())
                        file_counter = 0
                        for member in app_zf.namelist():
                            app_zf.extract(member, temp_dir)
                            file_counter += 1
                            progress_dialog.update_value(
                                5 + file_counter//n_files*85)
                            progress_dialog.update_log(member)
                        with open('%s/info' % temp_dir, 'r') as f:
                            info = json.load(f)
                        # Check the app id
                        if info['id'] in self.apps_dict:
                            raise Exception('App %s is already installed' %
                                            info['name'])
                        # Check target version of the platform
                        if self.release_info['version'] != 'Dev' and \
                            info['target'] != self.release_info['version']:
                        # if info['target'] != self.release_info['version']:
                            ex = exceptions.IncorrectAppVersionTarget()
                            self.medusa_interface.error(ex=ex, mode='dialog')
                            progress_dialog.update_action(
                                'Error!')
                            progress_dialog.update_log(
                                'Installation aborted',
                                style='error')
                            progress_dialog.finish()
                            return
                        # Move files from temp dir to final dir
                        progress_dialog.update_action(
                            'Moving to destination folder...')
                        dest_dir = '%s/%s' % (self.apps_folder, info['id'])
                        shutil.move(temp_dir, dest_dir)
                        progress_dialog.update_value(95)
                        # Install dependencies
                        progress_dialog.update_action(
                            'Installing dependencies...')
                        self.install_app_dependencies(dest_dir)
                        progress_dialog.update_action('Finished!')
                        progress_dialog.update_value(100)
                        progress_dialog.finish()
                # Default params
                info['installation-date'] = self.get_date_today()
                info['update'] = False
                info['update-version'] = None
                # Save apps dict
                self.apps_dict[info['id']] = info
                self.update_apps_file()
        except Exception as e:
            progress_dialog.update_log('ERROR: %s' % str(e), style='error')
            progress_dialog.finish()
            self.handle_exception(e)

    def install_app_template(self, app_id, app_name, app_extension,
                             app_template_path):
        """ This function is used to create a new template app for
        development purposes"""
        # Check errors
        if app_id in self.apps_dict:
            raise Exception('App with id %s is already installed' % app_id)
        # Copy tree
        app_path = '%s/%s' % (self.apps_folder, app_id)
        shutil.copytree(app_template_path, app_path)
        # App info
        info = {
            'id': app_id,
            'name': app_name,
            'description': 'Development version',
            'extension': app_extension,
            'version': '0.0.0',
            'compilation-date': 'development',
            'installation-date': self.get_date_today()
        }
        # Render jinja2 templates
        jinja2_files_path = glob.glob('%s/*.jinja2' % app_path)
        for jinja2_file_path in jinja2_files_path:
            jinja2_file_path_rendered = jinja2_file_path.split('.jinja2')[0]
            with open(jinja2_file_path, 'r') as f:
                jinja2_file_content = f.read()
                jinja2_template = Template(jinja2_file_content)
            with open(jinja2_file_path_rendered, 'w') as f:
                f.write(jinja2_template.render(app_info=info))
            os.remove(jinja2_file_path)
        # Update apps file
        self.apps_dict[info['id']] = info
        self.update_apps_file()

    def package_app(self, app_key, output_path, logger, progress_dialog):
        # Get input dir
        input_dir = '%s/%s' % (self.apps_folder, app_key)
        # Get number of files in directory and subdirectories
        n_files = sum(len(files) for _, _, files in os.walk(input_dir))
        n_files += sum(len(dirnames) for _, dirnames, _ in os.walk(input_dir))
        # Start event listener
        th = threading.Thread(target=self.package_event_listener,
                              args=(n_files, logger, progress_dialog))
        th.start()
        # Start packaging
        shutil.make_archive(base_name=output_path,
                            format='zip',
                            root_dir=input_dir,
                            logger=logger)
        th.join()

    def package_event_listener(self, n_files, logger, progress_dialog):
        try:
            # Read logger events
            progress_dialog.update_action('Creating app bundle...')
            num_files_packaged = 0
            while num_files_packaged < n_files:
                time.sleep(0.1)
                while not logger.handlers[0].queue.empty():
                    num_files_packaged += 1
                    progress_dialog.update_log(
                        logger.handlers[0].queue.get().getMessage())
                    progress_dialog.update_value(
                        int(num_files_packaged / n_files * 100))
            progress_dialog.update_value(100)
            progress_dialog.update_action('Finished!')
            progress_dialog.finish()
        except Exception as e:
            progress_dialog.update_log('ERROR: %s' % str(e), style='error')
            progress_dialog.finish()
            self.handle_exception(e)

    def check_updates(self):
        # Get app ids
        app_ids = list()
        for app_id, app_info in self.apps_dict.items():
            if app_info['compilation-date'] != 'development':
                app_ids.append(app_id)
        # Get target
        target = self.release_info['version']
        target = None if target == 'Dev' else target
        # Get latest versions
        latest_versions = self.accounts_manager.current_session.\
            get_medusa_latest_version_of_apps(app_ids, target)
        # Check for updates
        for app_id, app_info in self.apps_dict.items():
            if latest_versions is None or app_id not in latest_versions:
                self.apps_dict[app_id]['update'] = False
                self.apps_dict[app_id]['update-version'] = None
                continue
            if not isinstance(latest_versions[app_id], dict):
                # This happens when you change manually the id of an app that
                # was installed previously from the market. It can also
                # happen if the app is deleted from the market.
                self.apps_dict[app_id]['update'] = False
                self.apps_dict[app_id]['update-version'] = None
                ex = Exception('App %s is not available in the market' %
                               app_info['name'])
                self.medusa_interface.error(ex)
                continue
            # Check if an update is available
            curr_version = app_info['version']
            latest_version = latest_versions[app_id]['version']
                # Set update parameter
            if latest_version > curr_version:
                self.apps_dict[app_id]['update'] = True
                self.apps_dict[app_id]['update-version'] = \
                    latest_versions[app_id]
            else:
                self.apps_dict[app_id]['update'] = False
                self.apps_dict[app_id]['update-version'] = None

    def uninstall_app(self, app_key):
        # Remove directory
        app_path = '%s/%s' % (self.apps_folder, app_key)
        shutil.rmtree(app_path)
        # Update apps file
        self.apps_dict.pop(app_key)
        self.update_apps_file()


