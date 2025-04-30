# PYTHON MODULES
import copy
# EXTERNAL IMPORTS
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
matplotlib.use('QtAgg')
from matplotlib.widgets import Button
# MEDUSA-KERNEL IMPORTS
from medusa.components import SerializableComponent
from medusa.plots.head_plots import plot_head
from medusa import meeg


class EEGChannelSelectionPlot(SerializableComponent):
    """This class controls the interactive topographic representation.
        After selection, a dictionary with an EEGChannelSet consisting of
        the selected channels, the selected reference and the selected
        ground is returned."""

    def __init__(self, channel_set, channels_selected=None):
        # Parameters
        self.ch_labels = channel_set.l_cha

        # Initialize Variables
        self.channel_set = channel_set
        self.l_cha = self.channel_set.l_cha
        self.unlocated_channels = []
        self.located_channel_set = meeg.EEGChannelSet()
        self.channels_selected = channels_selected
        self.channel_location = None
        self.unlocated_ch_labels = None
        self.fig_head = None
        self.axes_head = None
        self.fig_unlocated = None
        self.axes_unlocated = None
        self.tolerance_radius = None
        self.selection_mode = 'Used'
        self.color = {
            "Used": '#76ba1b',
            'Ground': '#fff44f',
            'Reference': '#00bdfe'
        }
        self.final_channel_selection = {
            'Used': copy.copy(self.channel_set),
            'Ground': None,
            'Reference': None
        }

        self.init_plots()

        if self.channels_selected is None:
            self.set_channel_selection_dict()
        else:
            self.load_channel_selection_settings()

        # Uncomment to debug
        # self.fig_head.show()

    def check_unlocated_channels(self):
        """Separates located from unlocated channels"""
        for ch in self.channel_set.channels:
            if 'r' in ch.keys() or 'x' in ch.keys():
                self.located_channel_set.add_channel(ch, reference=None)
            else:
                self.unlocated_channels.append(ch)

    def init_plots(self):
        # Plot Channel Plot
        self.check_unlocated_channels()
        self.fig_head = plt.figure()
        self.fig_head.patch.set_alpha(False)
        self.axes_head = self.fig_head.add_subplot(111)
        if self.located_channel_set.channels != None:
            self.set_tolerance_radius()
            plot_head(axes=self.axes_head,
                      channel_set=self.located_channel_set,
                      plot_channel_labels=True,
                      channel_radius_size=self.tolerance_radius,
                      head_skin_color='#E8BEAC',
                      plot_channel_points=True)
            # Set channel coordinates
            self.set_channel_location()
        else:
            self.tolerance_radius = 0.25
            self.axes_head.set_axis_off()
            self.axes_head.set_facecolor('#00000000')

        # Add interactive functionality to the figure
        self.fig_head.canvas.mpl_connect('button_press_event', self.onclick)

        # Plot unlocated channels
        self.start_row = 0
        self.slider_ax = None
        self.unlocated_coords = {'radius':[],'theta':[],
                                 'ch_x':[],'ch_y':[]}
        self.unlocated_handles = dict()
        self.fig_unlocated, self.axes_unlocated = plt.subplots(figsize=(3, 8))
        self.fig_unlocated.patch.set_alpha(False)
        self.plot_unlocated()

        # Crear el botón de desplazamiento hacia arriba
        self.button_up_ax = self.fig_unlocated.add_axes(
            [0.4, 0.05, 0.1, 0.05])
        self.button_up = Button(self.button_up_ax, '↑')
        self.button_up.on_clicked(self.scroll_up)

        # Crear el botón de desplazamiento hacia abajo
        self.button_down_ax = self.fig_unlocated.add_axes(
            [0.6, 0.05, 0.1, 0.05])
        self.button_down = Button(self.button_down_ax, '↓')
        self.button_down.on_clicked(self.scroll_down)

        # Add interactive functionality to the figure
        self.fig_unlocated.canvas.mpl_connect('button_press_event',
                                              self.onclick)
    def plot_unlocated(self):
        # Clean axes before drawing
        self.axes_unlocated.axis("off")

        # Plot channels
        self.unlocated_ch_labels = [c['label'] for c in self.unlocated_channels]
        if len(self.unlocated_channels) > 0:

            # Plot channels as circunferences
            self.unlocated_handles['ch-contours'] = list()
            self.unlocated_handles['ch-labels'] = list()
            for ch_idx, ch in enumerate(self.unlocated_ch_labels):
                patch = matplotlib.patches.Circle(
                    (0.5, -0.5-ch_idx), radius=0.25, ec="none",
                    facecolor='#ffffff', edgecolor=None, alpha=0.4, zorder=10)
                handle_circ = self.axes_unlocated.add_patch(patch)
                self.unlocated_handles['ch-contours'].append(handle_circ)
                # Plot channels points
                handle_point = self.axes_unlocated.scatter(
                    0.5, -0.5-ch_idx, linewidths=1,
                    facecolors='w', edgecolors='k', zorder=12)
                self.unlocated_handles['ch-points'] = handle_point
                # Plot channels labels
                handle_label = self.axes_unlocated.text(
                    0.75, -0.5-ch_idx-0.125, ch,
                    fontsize=10, color='w', zorder=11)
                self.unlocated_handles['ch-labels'].append(handle_label)

                # Save coordinates
                self.unlocated_coords['radius'].append(
                    np.sqrt(0.5 ** 2 + (-0.5 - ch_idx) ** 2))
                self.unlocated_coords['theta'].append(
                    np.arctan2(-0.5 - ch_idx,0.5))
                self.unlocated_coords['ch_x'].append(0.5)
                self.unlocated_coords['ch_y'].append(-0.5 - ch_idx)

            # Number of channels to display
            max_data = min([len(self.unlocated_ch_labels),5])
            self.axes_unlocated.set_aspect('equal')
            self.axes_unlocated.set_xlim(0, 1)
            self.axes_unlocated.set_ylim(- max_data, 0)

            # Actualizar visibilidad de las etiquetas según los límites
            self.update_text_visibility()

        self.axes_unlocated.set_title('Unlocated \nChannels', fontsize=11,
                                      color='w')
        self.fig_unlocated.canvas.draw_idle()

    def update_text_visibility(self):
        # Obtener los límites actuales de y
        y_min, y_max = self.axes_unlocated.get_ylim()

        # Ajustar visibilidad de cada etiqueta
        for handle_label in self.unlocated_handles['ch-labels']:
            label_y = handle_label.get_position()[1]
            # Mostrar solo si la etiqueta está dentro de los límites
            handle_label.set_visible(y_min <= label_y <= y_max)

    def scroll_up(self, event):
        # Desplazar hacia arriba si no estamos en el inicio
        if self.start_row < 0:
            self.start_row += 1
            self.update_limits()  # Redibujar con el nuevo índice

    def scroll_down(self, event):
        # Desplazar hacia abajo si no hemos llegado al final
        if self.start_row > -len(self.unlocated_channels) + 5:
            self.start_row -= 1
            self.update_limits()  # Redibujar con el nuevo índice

    def update_limits(self):
        # Cambia los límites del eje y en función de la posición de start_row
        max_data = min(len(self.unlocated_channels), 5)
        y_min = self.start_row - max_data  # Ajusta el límite inferior
        y_max = self.start_row  # Ajusta el límite superior
        self.axes_unlocated.set_ylim(y_min, y_max)
        self.update_text_visibility()
        self.fig_unlocated.canvas.draw_idle()

    def set_channel_location(self):
        """For an easy treat of channel coordinates"""
        self.channel_location = dict()
        if 'r' in self.located_channel_set.channels[0].keys():
            self.channel_location['radius'] = \
                [c['r'] for c in self.located_channel_set.channels]
            self.channel_location['theta'] = \
                [c['theta'] for c in self.located_channel_set.channels]

            self.channel_location['ch_x'] = (
                    np.array(self.channel_location['radius']) * np.cos(
                self.channel_location['theta']))
            self.channel_location['ch_y'] = (
                    np.array(self.channel_location['radius']) * np.sin(
                self.channel_location['theta']))
        else:
            self.channel_location['ch_x'] = \
                [c['x'] for c in self.located_channel_set.channels]
            self.channel_location['ch_y'] = \
                [c['y'] for c in self.located_channel_set.channels]

            self.channel_location['radius'] = (
                np.sqrt(np.power(self.channel_location['ch_x'],2) +
                        np.power(self.channel_location['ch_y'],2)))
            self.channel_location['theta'] = (
                np.arctan2(np.array(self.channel_location['ch_y']),
                           np.array(self.channel_location['ch_x'])))

    def set_channel_selection_dict(self):
        """Initialize the state dict"""
        self.channels_selected = dict()
        self.channels_selected['Labels'] = np.asarray(self.l_cha,dtype='<U32')
        self.channels_selected['Selected'] = np.zeros(len(self.l_cha), dtype=bool)
        self.channels_selected['Plot line'] = np.full(len(self.l_cha), None)

    def set_tolerance_radius(self):
        """Calculates the radius of the click area of each channel."""
        dist_matrix = self.located_channel_set.compute_dist_matrix()
        dist_matrix.sort()
        percentage = self.set_tolerance_parameter()
        if len(self.l_cha) > 1:
            self.tolerance_radius = 1.5 * percentage * dist_matrix[:, 1].min()
        else:
            self.tolerance_radius = percentage

    def set_tolerance_parameter(self):
        """ Computes the percentage of the minimum distance between channels
            depending the montage standard with a linear function"""
        M = 345
        return len(self.l_cha) * (0.25 / (M - 2)) + 0.25 * ((M - 4) / (M - 2))

    def onclick(self, event):
        """ Handles the mouse click event"""
        xdata = event.xdata
        ydata = event.ydata
        if event.inaxes == self.axes_head:
            ch_label = self.check_channel_clicked((xdata, ydata),'head')
            if ch_label != None:
                self.change_state(ch_label)
                self.select_action(ch_label,'head')
            else:
                return
        elif event.inaxes == self.axes_unlocated:
            ch_label = self.check_channel_clicked((xdata, ydata),'unlocated')
            if ch_label != None:
                self.change_state(ch_label)
                self.select_action(ch_label,'unlocated')
            else:
                return

    def change_state(self,ch_label):
        ch_idx = self.l_cha.index(ch_label)
        self.channels_selected["Selected"][ch_idx] = not \
        self.channels_selected["Selected"][ch_idx]

    def check_channel_clicked(self, coord_click, figure):
        """ Checks if mouse was clicked inside the channel area"""
        if (coord_click[0] is None) or (coord_click[1] is None):
            return None
        distance = None

        if figure == 'head':
            if self.located_channel_set.channels != None:
                r = np.sqrt(coord_click[0] ** 2 + coord_click[1] ** 2) * \
                    np.ones((len(self.located_channel_set.channels)))
                theta = (np.arctan2(coord_click[1], coord_click[0]) *
                         np.ones((len(self.located_channel_set.channels))))
                distance = (r ** 2 + np.power(self.channel_location['radius'], 2) -
                            2 * r * self.channel_location['radius'] *
                            np.cos(theta - self.channel_location[
                                'theta'])) < self.tolerance_radius ** 2
        elif figure == 'unlocated':
            r = np.sqrt(coord_click[0] ** 2 + coord_click[1] ** 2) * \
                np.ones((len(self.unlocated_channels)))
            theta = np.arctan2(coord_click[1], coord_click[0]) * np.ones(
                (len(self.unlocated_channels)))
            distance = (r ** 2 + np.power(self.unlocated_coords['radius'], 2) -
                        2 * r * self.unlocated_coords['radius'] *
                        np.cos(theta - self.unlocated_coords[
                            'theta'])) < 0.25 ** 2
        if distance is None:
            return None
        else:
            if np.sum(distance) >= 1:
                idx = int(np.where(distance)[0])
                if figure == 'head':
                    ch_label = self.located_channel_set.l_cha[idx]
                elif figure == 'unlocated':
                    ch_label = self.unlocated_ch_labels[idx]
                return ch_label

    def channel_type_selected(self):
        """Avoids incompatibilities between different selection modes"""
        if self.selection_mode == 'Reference':
            idx_reference = np.where(self.channels_selected['Reference'])[0]
            if len(idx_reference) != 0:
                self.channels_selected['Selected'][int(idx_reference)] = False
                self.channels_selected['Plot line'][int(idx_reference)].remove()
                self.channels_selected['Reference'][int(idx_reference)] = False
                plt.setp(self.axes_head.texts[int(idx_reference)], fontweight='normal', color='w')
        elif self.selection_mode == 'Ground':
            idx_ground = np.where(self.channels_selected['Ground'])[0]
            if len(idx_ground) != 0:
                self.channels_selected['Selected'][int(idx_ground)] = False
                self.channels_selected['Plot line'][int(idx_ground)].remove()
                self.channels_selected['Ground'][int(idx_ground)] = False
                plt.setp(self.axes_head.texts[int(idx_ground)], fontweight='normal', color='w')

    def select_action(self, ch_label, figure):
        """Changes the 'Selected' state of the channel and its representation"""
        global_idx = self.l_cha.index(ch_label)
        location = None
        if figure == 'head':
            plot_idx = self.located_channel_set.l_cha.index(ch_label)
            location = self.channel_location
            axis = self.axes_head
        elif figure == 'unlocated':
            plot_idx = self.unlocated_ch_labels.index(ch_label)
            location = self.unlocated_coords
            axis = self.axes_unlocated

        if self.channels_selected['Selected'][global_idx]:
            # Check if reference or Ground are already selected
            # self.channel_type_selected()
            # Draw selection marker
            self.channels_selected['Plot line'][global_idx] = plt.Circle(
                (location['ch_x'][plot_idx], location['ch_y'][plot_idx]),
                radius=(0.5 * self.tolerance_radius),
                facecolor=self.color[self.selection_mode],
                edgecolor='k', alpha=1, zorder=12)
            # Highlight the selected label
            plt.setp(axis.texts[plot_idx], fontweight='extra bold', color=self.color[self.selection_mode])
            axis.add_patch(self.channels_selected['Plot line'][global_idx])
            # self.channels_selected[self.selection_mode][global_idx] = True
        else:
            self.channels_selected['Plot line'][global_idx].remove()
            self.channels_selected['Plot line'][global_idx] = None
            plt.setp(axis.texts[plot_idx], fontweight='normal', color='w')
            # self.channels_selected['Used'][global_idx] = False
            # self.channels_selected['Ground'][global_idx] = False
            # self.channels_selected['Reference'][global_idx] = False
        self.fig_head.canvas.draw()
        self.fig_unlocated.canvas.draw()
        return True

    def select_all(self):
        """Removes the already selected channels and then select them all"""
        plots = list(np.where(self.channels_selected['Plot line'])[0])
        for marker_idx in plots:
            self.channels_selected['Plot line'][int(marker_idx)].remove()
        self.set_channel_selection_dict()
        self.selection_mode = 'Used'
        self.channels_selected['Selected'] = np.ones(len(self.l_cha), dtype=bool)
        # self.channels_selected['Used'] = np.ones(len(self.l_cha), dtype=bool)
        for ch_label in self.l_cha:
            global_idx = self.l_cha.index(ch_label)
            if ch_label in self.located_channel_set.l_cha:
                plot_idx = self.located_channel_set.l_cha.index(ch_label)
                axis = self.axes_head
                location = self.channel_location
            else:
                plot_idx = self.unlocated_ch_labels.index(ch_label)
                axis = self.axes_unlocated
                location = self.unlocated_coords
            self.channels_selected['Plot line'][global_idx] = plt.Circle(
                (location['ch_x'][plot_idx], location['ch_y'][plot_idx]),
                radius=(0.5 * self.tolerance_radius),
                facecolor=self.color[self.selection_mode],
                edgecolor='k', alpha=1, zorder=12)
            plt.setp(axis.texts[plot_idx], fontweight='extra bold', color=self.color[self.selection_mode])
            axis.add_patch(self.channels_selected['Plot line'][global_idx])
        self.fig_head.canvas.draw()
        self.fig_unlocated.canvas.draw()

    def unselect_all(self):
        plots = list(np.where(self.channels_selected['Plot line'])[0])
        for marker_idx in plots:
            self.channels_selected['Plot line'][int(marker_idx)].remove()
            self.channels_selected['Plot line'][int(marker_idx)] = None
        plt.setp(self.axes_head.texts, fontweight='normal', color='w')
        plt.setp(self.axes_unlocated.texts, fontweight='normal', color='w')
        self.set_channel_selection_dict()
        self.fig_head.canvas.draw()
        self.fig_unlocated.canvas.draw()

    def load_channel_selection_settings(self):
        """Initialize the selection settings and make the necessary plots"""
        for key in self.channels_selected.keys():
            self.channels_selected[key] = np.asarray(self.channels_selected[key])
        if len(self.channel_set.l_cha) != 0:
            for idx in range(len(self.channel_set.l_cha)):
                if self.located_channel_set.channels is None :
                    if self.channels_selected['Selected'][idx]:
                        self.select_action(
                            self.channels_selected['Labels'][idx],
                            'unlocated')
                else:
                    if self.channels_selected['Labels'][idx] in \
                            self.located_channel_set.l_cha and \
                            self.channels_selected['Selected'][idx]:
                        self.select_action(
                            self.channels_selected['Labels'][idx],
                            'head')


                if self.unlocated_ch_labels is None:
                    if self.channels_selected['Selected'][idx]:
                        self.select_action(
                            self.channels_selected['Labels'][idx],
                            'head')
                else:
                    if self.channels_selected['Labels'][
                        idx] in self.unlocated_ch_labels and \
                            self.channels_selected['Selected'][idx]:
                        self.select_action(
                            self.channels_selected['Labels'][idx],
                            'unlocated')
                #
                # if self.located_channel_set.channels is None or\
                #         self.channels_selected['Labels'][idx] in \
                #         self.unlocated_ch_labels:
                #     if self.channels_selected['Selected'][idx]:
                #         self.select_action(self.channels_selected['Labels'][idx],
                #                                'unlocated')
                # if self.unlocated_ch_labels is None or self.channels_selected['Labels'][idx] in self.located_channel_set.l_cha:
                #     if self.channels_selected['Selected'][idx]:
                #         self.select_action(self.channels_selected['Labels'][idx],
                #                            'head')

    def get_channels_selection_from_gui(self):
        """Updates the final_channel_selection dict. It makes possible to get from widget
           the selected channels as a EEGChannelSet object"""
        self.final_channel_selection = dict()
        saved_channel_set = meeg.EEGChannelSet()
        saved_channel_set.set_standard_montage(
            l_cha=list(self.channels_selected['Labels'][self.channels_selected['Selected']]),
            montage='10-05',
            allow_unlocated_channels=True)
        self.final_channel_selection['Used'] = saved_channel_set

    def to_serializable_obj(self):
        channels_selected = {k: v.tolist() for k, v in self.channels_selected.items()}
        del channels_selected['Plot line']
        sett_dict = {'montage': self.montage,
                     'ch_labels': self.ch_labels,
                     'channels_selected': channels_selected}
        return sett_dict

    @classmethod
    def from_serializable_obj(cls, dict_data):
        return cls(**dict_data)

