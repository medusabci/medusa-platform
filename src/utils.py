import xml.etree.ElementTree as et
import requests
import subprocess, os, sys, json, datetime


def xml_string_to_json(xml_str, convert_numbers=False):
    """Converts an xml string to json format (dicts and lists). Take into
    account that xml supports more data types than json, so there is no direct
    conversion!

    Parameters
    ----------
    xml_str: str
        XML string that will be converted to json format
    convert_numbers: bool
        If True, it looks for numbers formatted as trings within the fields and
        tries to convert them to int or float
    """
    el_tree = et.fromstring(xml_str)
    return xml_element_to_json(el_tree, convert_numbers)


def xml_element_to_json(element, convert_numbers=False):
    """Converts xml.etree.ElementTree.Element to json format (dicts and lists).
    Take into account that xml supports more data types than json, so there is
    no direct conversion!

    Parameters
    ----------
    element: xml.etree.ElementTree.Element
        XML element that will be converted to json format
    convert_numbers: bool
        If True, it looks for numbers formatted as trings within the fields and
        tries to convert them to int or float
    """
    # Get childs
    el_childs = list(element)

    # Define the root element
    if __is_list(el_childs):
        parent_list = True
        el_json = []
    else:
        parent_list = False
        el_json = {}

    for child in el_childs:
        if parent_list:
            el_json.append(xml_element_to_json(
                child, convert_numbers=convert_numbers))
        else:
            if len(list(child)) > 0:
                el_json[child.tag] = xml_element_to_json(
                    child, convert_numbers=convert_numbers)
            else:
                if convert_numbers:
                    el_json[child.tag] = __str_to_number(child.text)
                else:
                    el_json[child.tag] = child.text or ''
    return el_json


def __is_list(element):
    tags = []
    for el in list(element):
        tags.append(el.tag)
    return not tags or (tags.count(tags[0]) == len(tags) and len(tags) > 1)


def __str_to_number(number_str):
    """Tries to convert the string to int or float. If it is not possible, it
    returns the same string
    """
    try:
        n = int(number_str)
    except ValueError as e:
        try:
            n = float(number_str)
        except ValueError as e:
            n = number_str
    return n


def execute_shell_commands(cmds):
    # Save temporal bat file
    bat_file_name = 'temp_bat_venv.bat'
    with open(bat_file_name, 'w') as f:
        for cmd in cmds:
            f.write(cmd + '\n')
    # Execute bat file
    with subprocess.Popen('%s' % bat_file_name, shell=True,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,
                          universal_newlines=True) as p:
        while True:
            if p.poll() is not None:
                break
            for line in p.stdout:
                if line == '\n':
                    continue
                print(line)
            for line in p.stderr:
                if line == '\n':
                    continue
                print(line, file=sys.stderr)
    # Delete bat file
    os.remove(bat_file_name)


def decode_github_release_info(release_body):
    split_body = release_body.split('@@VERSION_PARAMETERS')
    descr = split_body[0].strip()
    params = json.loads(split_body[1]) if len(split_body) > 1 else dict()
    return descr, params


def get_medusa_repo_releases_info(depth, repo='medusa-platform'):
    """Function to get the medusa versions from github with different depths.

    Parameters
    ----------
    depth: int
        Detail of the versions that should be retrieved:

            - Depth = 0 returns the yearly versions (e.g., v2022, v2023)
            - Depth = 1 returns the major versions updated to the last minor
                patch (e.g., v2022.1, 2022.2)
            - Depth=2 returns all versions (e.g., v2022.1.0, v2022.1.1)
    repo: string
        Repository name in GitHub
    """
    # TODO: If you change this function, update also in MEDUSA Installer and
    #   MEDUSA Web!
    # Get MEDUSA releases
    uri = "https://api.github.com/repos/medusabci/%s/releases" % repo
    # Token
    response = requests.get(uri)
    if response.status_code == 200:
        github_releases_info = response.json()
    else:
        raise ConnectionError()
    # Extract params
    releases_info = dict()
    for i in range(len(github_releases_info)):
        body = github_releases_info[i]['body']
        descr, params = decode_github_release_info(body)
        github_releases_info[i]['description'] = descr
        github_releases_info[i]['params'] = params
        # Get publishing date
        d = datetime.datetime.strptime(github_releases_info[i]["published_at"],
                                       "%Y-%m-%dT%H:%M:%SZ")
        github_releases_info[i]['date'] = d.strftime("%Y-%m-%d")
        # Split version
        tag_version = github_releases_info[i]['tag_name'].split('-')
        tag_version_stage = '' if len(tag_version) == 1 else tag_version[1]
        tag_version_split = tag_version[0].split('.')
        github_releases_info[i]['stage'] = tag_version_stage
        github_releases_info[i]['version'] = tag_version_split[0]
        github_releases_info[i]['major_patch'] = \
            int(tag_version_split[1] if len(tag_version_split) >= 2 else 0)
        github_releases_info[i]['minor_patch'] = \
            int(tag_version_split[2] if len(tag_version_split) >= 3 else 0)
        # 3 different tags depending on the required depth of the version
        depth_0_tag = '%s' % github_releases_info[i]['version']
        github_releases_info[i]['depth_0_tag'] = depth_0_tag
        depth_1_tag = '%s.%s' % (github_releases_info[i]['version'],
                                 github_releases_info[i]['major_patch'])
        github_releases_info[i]['depth_1_tag'] = depth_1_tag
        depth_2_tag = '%s.%s.%s' % (github_releases_info[i]['version'],
                                    github_releases_info[i]['major_patch'],
                                    github_releases_info[i]['minor_patch'])
        github_releases_info[i]['depth_2_tag'] = depth_2_tag
        # Add release. Only the most updated versions is added taking into
        # account the depth
        if depth == 0:
            if depth_0_tag in releases_info:
                # Check depth 0 release version and only save if it is more
                # recent
                if github_releases_info[i]['major_patch'] > \
                        releases_info[depth_0_tag]['major_patch']:
                    releases_info[depth_0_tag] = github_releases_info[i]
            else:
                releases_info[depth_0_tag] = github_releases_info[i]
        elif depth == 1:
            if depth_1_tag in releases_info:
                # Check minor release version and only save if it is more recent
                if github_releases_info[i]['minor_patch'] > \
                        releases_info[depth_1_tag]['minor_patch']:
                    releases_info[depth_1_tag] = github_releases_info[i]
            else:
                releases_info[depth_1_tag] = github_releases_info[i]
        else:
            # All versions are added
            releases_info[depth_2_tag] = github_releases_info[i]
    return releases_info


def restart():
    """Restarts the platform. If you are running the program from from PyCharm,
    it makes strange things, but from medusa.exe works just fine."""
    os.execv(sys.executable, ['python'] + sys.argv)














