# BUILT-IN MODULES
import shutil, json, os, glob
from datetime import datetime
import zipfile, tempfile
from io import BytesIO
# EXTERNAL MODULES
from jinja2 import Template
from cryptography.fernet import Fernet
# INTERNAL MODULES
import constants, exceptions


class AppManager:

    def __init__(self, accounts_manager):
        # Get installed apps
        self.accounts_manager = accounts_manager
        self.apps_config_file_path = self.accounts_manager.wrap_path(
            constants.APPS_CONFIG_FILE)
        self.apps_folder = self.accounts_manager.wrap_path('apps')
        self.apps_dict = None
        self.load_apps_file()

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

    def install_app_bundle(self, bundle_path):
        # Install app (extract zip)
        with zipfile.ZipFile(bundle_path) as bundle:
            token = bundle.read('token').decode()
            license_key = \
                self.accounts_manager.current_session.get_license_key(token)
            f = Fernet(license_key)
            app = BytesIO(f.decrypt(bundle.read('app')))
            with zipfile.ZipFile(app) as app_zf:
                with tempfile.TemporaryDirectory() as temp_dir:
                    # Extract app
                    app_zf.extractall(temp_dir)
                    with open('%s/info' % temp_dir, 'r') as f:
                        info = json.load(f)
                    if info['id'] in self.apps_dict:
                        raise Exception('App %s is already installed' %
                                        info['name'])
                    dest_dir = '%s/%s' % (self.apps_folder, info['id'])
                    shutil.move(temp_dir, dest_dir)
            # Update apps file
            info['installation-date'] = self.get_date_today()
            self.apps_dict[info['id']] = info
            self.update_apps_file()

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

    def package_app(self, app_key, output_path,logger):
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
