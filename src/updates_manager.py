import shutil


class UpdatesManager:

    """Class to manage updates in MEDUSA. It should distinguish patch updates
    (from v2022.0.0 to v2022.0.1) which are bug fixes, minor updates (from
    v2022.0.1 to v2022.1.0) which add features assuring apps compatibility, and
    major updates (from v2022.0.1 to v2023.0.1), which don't assure app
    compatibility with apps.

    Things to consider:

        - Check shutil.copytree with dirs_exist_ok=True for updates
        - Having a file named version is probably a good idea to manage versions
    """

    def __init__(self):
        # TODO: everything
        # For updates check shutil.copytree with parameter dirs_exist_ok set to
        # True
        pass
