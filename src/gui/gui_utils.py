# Built-in modules
import os, pathlib
# External imports
from PIL import Image, ImageQt
from PyQt5.QtGui import *
from PyQt5.Qt import Qt
import numpy as np
# Medusa imports
import constants
from gui.themes import themes


# ------------------------------- QT UTILS ----------------------------------- #
def select_entry_combobox(combobox, entry_text, force_selection=False,
                          throw_error=False):
    index = combobox.findText(entry_text, Qt.MatchFixedString)
    if index >= 0:
        combobox.setCurrentIndex(index)
    else:
        if force_selection:
            combobox.setCurrentIndex(0)
        else:
            if throw_error:
                raise ValueError('Entry text not valid')
            else:
                return


# --------------------------- COLOR CONVERSION ------------------------------- #
def hex_to_rgb(hex):
    """ Converts an hexadecimal color string to a RGB tuple.

    Parameters
    ----------
    hex: string
        Hexadecimal RGB/RGBA string (e.g., '#AABBCC' or '#AABBCCFF').

    Returns
    ---------
    color : tuple
        RGB or RGBA values.
    """
    hex = hex.lstrip('#')
    lv = len(hex)
    return tuple(int(hex[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))


def rgb_to_hex(color):
    """ Converts a RGB/RGBA color into a hexadecimal string

        Parameters
        ----------
        color : tuple
            RGB or RGBA values.

        Returns
        ---------
        hex: string
            Hexadecimal RGB/RGBA string (e.g., '#AABBCC' or '#AABBCCFF').
    """
    return ('#' + ''.join(['%02x' for i in range(len(color))])) % color


def rgb_to_hsv(rgb):
    """ Converts RGB to HSV (Hue, Saturation, Value) colors.

    Parameters
    ----------
    rgb : tuple
        Tuple containing non-normalized RGB values (0-255, 0-255, 0-255).

    Returns
    ----------
    hsv : tuple
        Tuple containing non-normalized HSV values (0-360 º, 0-100 %, 0-100 %).
    """
    r = rgb[0] / 255.
    g = rgb[1] / 255.
    b = rgb[2] / 255.
    maxc = max(r, g, b)
    minc = min(r, g, b)
    rangec = (maxc - minc)
    v = maxc
    if minc == maxc:
        return 0.0, 0.0, v * 100
    s = rangec / maxc
    rc = (maxc - r) / rangec
    gc = (maxc - g) / rangec
    bc = (maxc - b) / rangec
    if r == maxc:
        h = bc - gc
    elif g == maxc:
        h = 2.0 + rc - bc
    else:
        h = 4.0 + gc - rc
    h = (h / 6.0) % 1.0
    return tuple([h * 360, s * 100, v * 100])


def hsv_to_rgb(hsv):
    """ Converts HSV to RGB colors.

        Parameters
        ----------
        hsv : tuple
            Tuple containing non-normalized HSV values
            (0-360 º, 0-100 %, 0-100 %).

        Returns
        ----------
        rgb : tuple
            Tuple containing non-normalized RGB values (0-255, 0-255, 0-255).
    """
    h = hsv[0] / 360.
    s = hsv[1] / 100.
    v = hsv[2] / 100.
    rgb = []
    if s == 0.0:
        rgb = [v, v, v]
    else:
        i = int(h * 6.0)  # XXX assume int() truncates!
        f = (h * 6.0) - i
        p = v * (1.0 - s)
        q = v * (1.0 - s * f)
        t = v * (1.0 - s * (1.0 - f))
        i = i % 6
        if i == 0:
            rgb = [v, t, p]
        if i == 1:
            rgb = [q, v, p]
        if i == 2:
            rgb = [p, v, t]
        if i == 3:
            rgb = [p, q, v]
        if i == 4:
            rgb = [t, p, v]
        if i == 5:
            rgb = [v, p, q]
    return tuple(np.array(rgb) * 255)


# ---------------------------- USEFUL METHODS -------------------------------- #
def img_to_icon(image):
    """ Converts a PIL Image into a QIcon

    :param image: PIL.Image
        Image to convert (RGBA).
    """
    qim = ImageQt.ImageQt(image)
    pix = QPixmap.fromImage(qim)
    qicon = QIcon(pix)
    return qicon


def img_to_pixmap(image):
    """ Converts a PIL image into a QPixmap

    :param image: PIL.Image
        Image to convert.
    """
    if image.mode == "RGB":
        r, g, b = image.split()
        im = Image.merge("RGB", (b, g, r))
    elif image.mode == "RGBA":
        r, g, b, a = image.split()
        im = Image.merge("RGBA", (b, g, r, a))
    elif image.mode == "L":
        im = image.convert("RGBA")
    im2 = im.convert("RGBA")
    data = im2.tobytes("raw", "RGBA")
    qim = QImage(data, im.size[0], im.size[1], QImage.Format_ARGB32)
    pixmap = QPixmap.fromImage(qim)
    return pixmap


def clear_layout(layout):
    """ Clears a given layout.

    :param layout: layout
        Layout to clear.
    """
    if layout is not None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            else:
                clear_layout(item.layout())


# --------------------------------------------------- CSS EDITING ---------------------------------------------------- #
def modify_properties(handle, dict_name_value):
    for name, value in dict_name_value.items():
        modify_property(handle, name, value)

def modify_property(handle, name, value):
    """ Modifies a CSS property of a given handle.

    :param handle: Qt object handle
        Handle that identifies the object to modify.
    :param name: basestring
        Name of the CSS property (e.g., 'color', 'font-size').
    :param value: basestring
        Value of the CSS property. Note that measurements must be specified, and ; is not required (e.g., '15px')
    """

    # Find if the property exists
    css_orig = handle.styleSheet()
    offset = 0
    css = css_orig
    while True:
        idx_1 = css.find(name + ":")
        if idx_1 == -1:
            # It does not exist, so append it
            prop = css_orig + name + ": " + value + ";"
            break

        idx_2 = css[idx_1:].find(";")
        if css.find("-" + name + ":") == -1:
            prop = css[idx_1:idx_1 + idx_2]
            idx_3 = prop.find(":")
            prop = css_orig[:offset + idx_1 + idx_3] + ": " + value + "; " + \
                   css_orig[offset + idx_1 + idx_2 + 1:]
            break
        else:
            # This was a property that contains the name but it is not the
            # desired one. For instance, 'background-color'
            # contains 'color'
            css = css[idx_1 + idx_2:]
            offset += idx_1 + idx_2

    # Update the CSS
    handle.setStyleSheet(prop)
    return prop


def get_property(handle, name):
    """ Gets the value of a given CSS property in a handle.

    :param handle: Qt object handle
        Handle that identifies the object.
    :param name: basestring
        Name of the CSS property (e.g., 'color', 'font-size').
    """
    # Find if the property exists
    css = handle.styleSheet()

    # Find the appropriate property, not just one that contains the given name
    while True:
        idx_1 = css.find(name + ":")
        if idx_1 == -1:
            # It does not exist
            print(handle.styleSheet())
            raise ValueError('Property "%s" is not specified in %s.' % (name, handle))

        idx_2 = css[idx_1:].find(";")
        if css.find("-" + name + ":") == -1:
            value = css[idx_1:idx_1+idx_2]
            value = value.replace(name + ": ", "")  # Delete its name
            break
        else:
            # This was a property that contains the name but it not the desired one. For instance, 'background-color'
            # contains 'color'
            css = css[idx_1 + idx_2:]
    return value


# ============================ THEME DEFINITIONS ============================ #
def set_css_and_theme(gui_handle, theme_colors, stylesheet_path=None):
    """Reads the stylesheet and sets a theme.

    :param gui_handle: object
        Instance of the GUI.
    :param theme_colors: basestring
        Theme to select:
           'dark': Dark theme (i.e., darcula).
    :return stylesheet: basestring
        Gui stylesheet.
    """
    if stylesheet_path is None:
        start_dir = os.getcwd()
        end_dir = os.path.dirname(__file__)
        gui_dir_rel_path = os.path.relpath(end_dir, start=start_dir)
        stylesheet_rel_path = '%s/style.css' % gui_dir_rel_path
    else:
        stylesheet_rel_path = stylesheet_path
    stl = load_stylesheet(stylesheet_rel_path)
    stl = set_theme(stl, theme_colors)
    gui_handle.setStyleSheet(stl)
    return stl


def load_stylesheet(path, charset='utf-8'):
    """ Loads and decodes a stylesheet in stylesheet parameter.

    :param path: basestring
        Absolute path of the CSS file.
    :param charset: basestring
        (Optional, default='utf-8') Decoding charset.

    :return stylesheet: basestring
        Decoded stylesheet
    """
    with open(path, "rb") as f:
        stl = f.read().decode(charset)
    return stl


def set_theme(stylesheet, theme_colors):
    """ Sets a theme by replacing key string in the stylesheet.

    :param stylesheet: basestring
        Stylesheet to modify
    :param theme_colors: basestring
        Theme selection:
            'dark': Dark theme (i.e., darcula).

    :return stylesheet: basestring
        Modified stylesheet
    """
    for key, color in theme_colors.items():
        stylesheet = stylesheet.replace('@' + key, color)
    return stylesheet


def get_theme_colors(theme='dark'):
    """ Returns the colors of the given theme.

    :return dictionary: theme colors
    """
    theme_colors = themes[theme]
    return theme_colors
