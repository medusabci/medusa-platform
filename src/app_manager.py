# BUILT-IN MODULES
import shutil, json, os, glob, re
from datetime import datetime
import zipfile, tempfile
from io import BytesIO
import pkg_resources
# EXTERNAL MODULES
from jinja2 import Template
from cryptography.fernet import Fernet
# INTERNAL MODULES
import constants, exceptions, utils
from gui.qt_widgets import dialogs


class AppManager:

    def __init__(self, accounts_manager, medusa_interface):
        # Get installed apps
        self.accounts_manager = accounts_manager
        self.medusa_interface = medusa_interface
        self.apps_config_file_path = self.accounts_manager.wrap_path(
            constants.APPS_CONFIG_FILE)
        self.apps_folder = self.accounts_manager.wrap_path('apps')
        self.apps_dict = None
        self.load_apps_file()

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
        # Check
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
        return all(confirmation)

    def install_app_dependencies(self, app_dir):
        # Get medusa and requirements paths
        mds_path = '\\'.join(os.path.abspath(__file__).split('\\')[:-2])
        req_path = os.path.normpath('src/%s/requirements.txt' % app_dir)
        # Check dependencies
        if self.check_app_dependencies(app_dir):
            # Write bat file with the commands to install python dependencies
            cmds = list()
            cmds.append('%s:' % mds_path.split(':')[0])
            cmds.append('cd "%s"' % mds_path)
            cmds.append('call "venv\\Scripts\\activate"')
            cmds.append('pip install -r %s' % req_path)
            # Execute
            utils.execute_shell_commands(cmds)
        else:
            msg = """The dependencies were not installed to avoid conflicts
             between apps. You'll need to handle them manually if necessary"""
            self.medusa_interface.log(msg, style='warning')

    def install_app_bundle(self, bundle_path, logger):
        try:
            # Install app (extract zip)
            with zipfile.ZipFile(bundle_path) as bundle:
                token = bundle.read('token').decode()
                license_key = \
                    self.accounts_manager.current_session.get_license_key(token)
                f = Fernet(license_key)
                app = BytesIO(f.decrypt(bundle.read('app')))
                with zipfile.ZipFile(app) as app_zf:
                    with tempfile.TemporaryDirectory() as temp_dir:
                        # Notify the number of files in app zip
                        logger.info(f"Starting: {len(app_zf.namelist())} files",)
                        # Extract app files
                        for member in app_zf.namelist():
                            app_zf.extract(member, temp_dir)
                            logger.info("adding '%s'", member)
                        with open('%s/info' % temp_dir, 'r') as f:
                            info = json.load(f)
                        # Check the app id
                        if info['id'] in self.apps_dict:
                            raise Exception('App %s is already installed' %
                                            info['name'])
                        # Check target version of the platform
                        if info['target'] != constants.MEDUSA_VERSION:
                            # todo: convert to dialog
                            self.medusa_interface.log(
                                'This app has been designed for MEDUSA Platform'
                                ' %s. Correct operation is not guaranteed' %
                                info['target'])
                        # Move files from temp dir to final dir
                        dest_dir = '%s/%s' % (self.apps_folder, info['id'])
                        shutil.move(temp_dir, dest_dir)
                        # Install dependencies
                        self.install_app_dependencies(dest_dir)
                        # Finish
                        logger.info("Finished")
                # Update apps file
                info['installation-date'] = self.get_date_today()
                self.apps_dict[info['id']] = info
                self.update_apps_file()
        except Exception as e:
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

    def package_app(self, app_key, output_path, logger):
        input_dir = '%s/%s' % (self.apps_folder, app_key)
        shutil.make_archive(base_name=output_path,
                            format='zip',
                            root_dir=input_dir,
                            logger=logger)

    def uninstall_app(self, app_key):
        # Remove directory
        app_path = '%s/%s' % (self.apps_folder, app_key)
        shutil.rmtree(app_path)
        # Update apps file
        self.apps_dict.pop(app_key)
        self.update_apps_file()


