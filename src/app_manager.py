# BUILT-IN MODULES
import shutil, json, os, glob
from datetime import datetime
import zipfile, tempfile
# EXTERNAL MODULES
from jinja2 import Template
# INTERNAL MODULES
import constants


class AppManager:

    def __init__(self):
        # Get installed apps
        self.apps_dict = None
        self.load_apps_file()

    def load_apps_file(self):
        if os.path.isfile(constants.APPS_CONFIG_FILE):
            with open(constants.APPS_CONFIG_FILE, 'r') as f:
                self.apps_dict = json.load(f)
        else:
            self.apps_dict = {}

    def update_apps_file(self):
        with open(constants.APPS_CONFIG_FILE, 'w') as f:
            json.dump(self.apps_dict, f, indent=4)

    def get_date_today(self):
        return datetime.today().strftime('%Y-%m-%d %H:%M:%S')

    def install_app_bundle(self, bundle_path):
        # Install app (extract zip)
        with zipfile.ZipFile(bundle_path) as bundle:
            with tempfile.TemporaryDirectory() as temp_dir:
                # Extract app
                bundle.extractall(temp_dir)
                with open('%s/info' % temp_dir, 'r') as f:
                    info = json.load(f)
                if info['id'] in self.apps_dict:
                    raise Exception('App %s is already installed' %
                                    info['name'])
                dest_dir = 'apps/%s' % info['id']
                shutil.move(temp_dir, dest_dir)
            # Update apps file
            info['installation-date'] = self.get_date_today()
            self.apps_dict[info['id']] = info
            self.update_apps_file()

    def install_app_template(self, app_id, app_name, app_extension,
                             app_template_path):
        # Check errors
        if app_id in self.apps_dict:
            raise Exception('App with id %s is already installed' % app_id)
        # Copy tree
        app_path = 'apps/%s' % app_id
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

    def uninstall_app(self, app_key):
        # Remove directory
        shutil.rmtree('apps/%s' % app_key)
        # Update apps file
        self.apps_dict.pop(app_key)
        self.update_apps_file()
