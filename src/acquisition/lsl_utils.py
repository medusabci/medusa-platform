# BUILT-IN MODULES
import time, socket

import numpy as np
# EXTERNAL MODULES
import pylsl
from medusa import components

# MEDUSA MODULES
import exceptions
import utils


def get_lsl_streams(wait_time=0.1, force_one_stream=False, **kwargs):
    """
    This function resolves the LSL streams matching the parameter
    stream_property given a property.

    Parameters
    ----------
    wait_time: float
        Wait time to find lsl streams
    force_one_stream: bool
        Only returns one stream. If more streams are found for the given
        properties, an error is triggered.
    kwargs: key-value arguments
        Key-value arguments specifying  the name and value of the property
        that the selected streams must match. Available LSL properties: name,
        type, source_id, uid, channel_count, nominal_srate, hostname
    """
    # Resolve EEG LSL streams
    streams = pylsl.resolve_stream(wait_time)
    match_streams = []
    if kwargs is None:
        match_streams = streams
    else:
        for stream in streams:
            check_all_properties = []
            for key, value in kwargs.items():
                check = False
                if key == 'name':
                    if value == stream.name():
                        check = True
                elif key == 'type':
                    if value == stream.type():
                        check = True
                elif key == 'source_id':
                    if value == stream.source_id():
                        check = True
                elif key == 'uid':
                    if value == stream.uid():
                        check = True
                elif key == 'channel_count':
                    if value == stream.channel_count():
                        check = True
                elif key == 'nominal_srate':
                    if value == stream.nominal_srate():
                        check = True
                elif key == 'hostname':
                    if value == stream.hostname():
                        check = True
                else:
                    raise ValueError('Property %s not available.' % key)
                check_all_properties.append(check)
            if all(check_all_properties):
                match_streams.append(stream)
    # Check that at least one stream has been found
    if len(match_streams) == 0:
        raise exceptions.LSLStreamNotFound(kwargs)
    # Return
    if force_one_stream:
        if len(match_streams) > 1:
            raise exceptions.UnspecificLSLStreamInfo(kwargs)
        return match_streams[0]
    else:
        return match_streams


def check_if_medusa_uid_is_available(working_lsl_streams, medusa_uid):
    """This function checks if an uid is available given the current working
    lsl streams that have been configured.
    """
    for stream in working_lsl_streams:
        if stream.medusa_uid == medusa_uid:
            return False
    return True


def find_lsl_stream(lsl_streams, force_one_stream, **kwargs):
    """This function finds matching LSL streams using different properties.

    Parameters
    ----------
    lsl_streams: list of LSLStreamWrapper
        List of LSLStreamWrapper. For instance, the working_lsl_streams list
    force_one_stream: bool
        Only returns one stream. If more streams are found for the given
        properties, an error is triggered.
    kwargs: key-value arguments
        Key-value arguments specifying  the name and value of the property
        that the selected streams must match. Available LSL properties: name,
        type, source_id, uid, channel_count, nominal_srate, hostname

    """
    match_streams = []
    for stream in lsl_streams:
        check_all_properties = []
        for key, value in kwargs.items():
            check = False
            if key == 'medusa_uid':
                if value == stream.medusa_uid:
                    check = True
            elif key == 'name':
                if value == stream.lsl_name:
                    check = True
            elif key == 'type':
                if value == stream.lsl_type:
                    check = True
            elif key == 'source_id':
                if value == stream.lsl_source_id:
                    check = True
            elif key == 'uid':
                if value == stream.lsl_uid:
                    check = True
            elif key == 'channel_count':
                if value == stream.lsl_n_cha:
                    check = True
            elif key == 'nominal_srate':
                if value == stream.fs:
                    check = True
            elif key == 'hostname':
                if value == stream.hostname:
                    check = True
            else:
                raise ValueError('Property %s not available.' % key)
            check_all_properties.append(check)
        if all(check_all_properties):
            match_streams.append(stream)
    # Check that at least one stream has been found
    if len(match_streams) == 0:
        raise exceptions.LSLStreamNotFound(kwargs)
        # Return
    if force_one_stream:
        if len(match_streams) > 1:
            raise exceptions.UnspecificLSLStreamInfo(kwargs)
        return match_streams[0]
    else:
        return match_streams


class LSLStreamWrapper(components.SerializableComponent):
    """LSL stream wrapper class for medusa. It includes the stream_info and
    stream_inlet objects for easier use.
    """

    def __init__(self, lsl_stream):
        """Class constructor

        Parameters
        ----------
        lsl_stream: pylsl.stream_info
            LSL Stream info object. This info can be directly passed from
            function get_lsl_streams, since the LSL inlet will be initialized
            here.
        """
        # LSL stream
        if not isinstance(lsl_stream, pylsl.stream_info):
            raise TypeError('Parameter lsl_stream must be '
                            'of type pylsl.stream_info')
        self.lsl_stream = lsl_stream
        # LSL parameters
        self.lsl_stream_inlet = None
        self.lsl_stream_info = None
        self.lsl_proc_clocksync = None
        self.lsl_proc_dejitter = None
        self.lsl_proc_monotonize = None
        self.lsl_proc_threadsafe = None
        self.processing_flags = None
        self.lsl_name = None
        self.lsl_type = None
        self.lsl_n_cha = None
        self.lsl_cha_format = None
        self.lsl_uid = None
        self.lsl_source_id = None
        self.fs = None
        self.time_correction = None
        self.hostname = None
        self.local_stream = None
        self.lsl_stream_info_xml = None
        self.lsl_stream_info_json_format = None
        # Additional Medusa parameters
        self.medusa_params_initialized = False
        self.medusa_uid = None
        self.medusa_type = None
        self.desc_channels_field = None
        self.channel_label_field = None
        self.cha_info = None
        self.selected_channels_idx = None
        self.n_cha = None
        self.l_cha = None
        # Set inlet and lsl info
        # self.set_inlet(clocksync=self.lsl_proc_clocksync,
        #                dejitter=self.lsl_proc_dejitter,
        #                monotonize=self.lsl_proc_monotonize,
        #                threadsafe=self.lsl_proc_threadsafe)

    def set_inlet(self, proc_clocksync=False, proc_dejitter=False,
                  proc_monotonize=False, proc_threadsafe=True):
        # Possible LSL flags {proc_none, proc_clocksync , proc_dejitter,
        processing_flags = 0
        # Conditionally add each flag based on the variables
        if proc_clocksync:
            processing_flags |= pylsl.proc_clocksync
        if proc_dejitter:
            processing_flags |= pylsl.proc_dejitter
        if proc_monotonize:
            processing_flags |= pylsl.proc_monotonize
        if proc_threadsafe:
            processing_flags |= pylsl.proc_threadsafe
        self.lsl_proc_clocksync = proc_clocksync
        self.lsl_proc_dejitter = proc_dejitter
        self.lsl_proc_monotonize = proc_monotonize
        self.lsl_proc_threadsafe = proc_threadsafe
        self.processing_flags = processing_flags
        self.lsl_stream_inlet = pylsl.StreamInlet(
            self.lsl_stream, processing_flags=processing_flags)
        self.lsl_stream_info = self.lsl_stream_inlet.info()
        # LSL parameters
        self.lsl_name = self.lsl_stream_info.name()
        self.lsl_type = self.lsl_stream_info.type()
        self.lsl_n_cha = self.lsl_stream_info.channel_count()
        self.lsl_cha_format = self.lsl_stream_info.channel_format()
        self.lsl_uid = self.lsl_stream_info.uid()
        self.lsl_source_id = self.lsl_stream_info.source_id()
        self.fs = self.lsl_stream_info.nominal_srate()
        self.time_correction = self.lsl_stream_inlet.time_correction()
        self.hostname = self.lsl_stream_info.hostname()
        self.local_stream = socket.gethostname() == self.hostname
        self.lsl_stream_info_xml = self.lsl_stream_info.as_xml()
        self.lsl_stream_info_json_format = None
        # Check lsl stream info format
        self.lsl_stream_info_to_json()

    def lsl_stream_info_to_json(self):
        # Custom corrections for different manufacturers
        if self.lsl_stream_info_xml.find('NeuroElectrics') > 0:
            """Neuroelectrics uses the following structure:
            
            <desc>
                <manufacturer>NeuroElectrics</manufacturer>
                <channel>
                    <name>Ch1</name>
                    <unit>microvolts</unit>
                    <type>EEG</type>
                </channel>
                .
                .
                .
                <channel>
                    <name>Ch32</name>
                    <unit>microvolts</unit>
                    <type>EEG</type>
                </channel>
            </desc>
            """
            if self.lsl_stream_info_xml.find('<channel>') > 0:
                # Correct structure introducing channels element to wrap the
                # channels
                idx1 = self.lsl_stream_info_xml.find('<channel>')
                self.lsl_stream_info_xml = \
                    self.lsl_stream_info_xml[:idx1] + '<channels>\n\t\t' + \
                    self.lsl_stream_info_xml[idx1:]
                idx2 = self.lsl_stream_info_xml.rfind('</channel>') + \
                       len('</channel>')
                self.lsl_stream_info_xml = \
                    self.lsl_stream_info_xml[:idx2] + \
                    '\n\t\t</channels>' + self.lsl_stream_info_xml[idx2:]
                # Correct indentations
                idx1 = self.lsl_stream_info_xml.find('<channels>\n\t\t') + \
                       len('<channels>\n\t\t')
                idx2 = self.lsl_stream_info_xml.find('\n\t\t</channels>')
                lines = self.lsl_stream_info_xml[idx1:idx2].splitlines(True)
                self.lsl_stream_info_xml = \
                    self.lsl_stream_info_xml[:idx1] + \
                    ''.join('\t' + line for line in lines) + \
                    self.lsl_stream_info_xml[idx2:]
            else:
                # Some NeuroElectrics streams do not have channels in LSL desc
                idx = self.lsl_stream_info_xml.rfind('</manufacturer>') + \
                      len('</manufacturer>')
                for i in range(self.lsl_n_cha):
                    self.lsl_stream_info_xml = \
                        self.lsl_stream_info_xml[:idx] + \
                        '\n\t\t<channels>\n\t\t\t<channel>' \
                        '\n\t\t\t\t<name>Ch%i</name>' \
                        '\n\t\t\t\t<unit>None</unit>' \
                        '\n\t\t\t\t<type>None</type>' \
                        '\n\t\t\t</channel>\n\t\t</channels>' % i + \
                        self.lsl_stream_info_xml[idx:]
                    idx = self.lsl_stream_info_xml.rfind('</channels>') + \
                          len('</channels>')
        # Update json description
        self.lsl_stream_info_json_format = \
            utils.xml_string_to_json(self.lsl_stream_info_xml)
        # Check json description
        if 'desc' not in self.lsl_stream_info_json_format or \
                self.lsl_stream_info_json_format['desc'] == '':
            # This field desc must be a dict
            self.lsl_stream_info_json_format['desc'] = dict()
        if 'channels' not in self.lsl_stream_info_json_format['desc']:
            self.lsl_stream_info_json_format['desc']['channels'] = list()
            for i in range(self.lsl_n_cha):
                self.lsl_stream_info_json_format['desc']['channels'].append(
                    {'name': 'Ch%i' % i}
                )
        channels = self.lsl_stream_info_json_format['desc']['channels']
        if not isinstance(channels, list):
            # If there is only one channel, it has to be converted to list
            self.lsl_stream_info_json_format['desc']['channels'] = \
                list(channels.values())

    def get_easy_description(self):
        if self.medusa_params_initialized:
            stream_descr = '%s (host: %s, type: %s, channels: %i)' % \
                           (self.medusa_uid, self.hostname,
                            self.medusa_type, self.n_cha)
        else:
            stream_descr = '%s (host: %s, type: %s, channels: %i)' % \
                           (self.lsl_name, self.hostname,
                            self.lsl_type, self.lsl_n_cha)
        return stream_descr

    def get_description_fields(self):
        return self.lsl_stream_info_json_format['desc'].keys()

    def get_desc_field_value(self, desc_field):
        """Returns a field of the description in the lsl inlet. Usually used to
        retrieve channel information"""
        # Get all channels
        return self.lsl_stream_info_json_format['desc'][desc_field]

    def set_medusa_parameters(self, medusa_uid, medusa_type,
                              desc_channels_field,
                              channel_label_field,
                              cha_info,
                              selected_channels_idx):
        """Decodes the channels from the extended description of the stream,
        in XML format, contained in lsl_stream_info

        medusa_uid: str
            Unique identifier for the LSL stream in Medusa
        medusa_type: str
            Medusa type of the stream (e.g., EEG, MEG, etc). It should match a
            type from medusa core.
        desc_channels_field: str
            Field within the extended description (obtained through
            lsl_stream_info.desc()) that contains the channels information in
        channel_label_field: str
            Field that contains the label of the channels
        selected_channels_idx: list of int
            Indexes of the channels to be used.
        cha_info: list of dict [Optional]
            List with the channel info. If None, the info will be extracted
            automatically from the lsl_stream.
        """
        # Select channels
        sel_cha_info = [cha_info[i] for i in selected_channels_idx]
        n_cha = len(selected_channels_idx)
        l_cha = [info[channel_label_field] for info in sel_cha_info] \
            if channel_label_field is not None else list(range(n_cha))
        # Update parameters
        self.update_medusa_parameters(
            medusa_params_initialized=True,
            medusa_uid=medusa_uid,
            medusa_type=medusa_type,
            desc_channels_field=desc_channels_field,
            channel_label_field=channel_label_field,
            cha_info=cha_info,
            selected_channels_idx=selected_channels_idx,
            n_cha=n_cha,
            l_cha=l_cha
        )

    def update_medusa_parameters_from_lslwrapper(self, lsl_stream_wrapper):
        """Use this function to manually update the medusa params from one
        stream to another. An error will be raised if the passed lsl stream
        does not have the medusa params initialized"""
        self.update_medusa_parameters(
            lsl_stream_wrapper.medusa_params_initialized,
            lsl_stream_wrapper.medusa_uid,
            lsl_stream_wrapper.medusa_type,
            lsl_stream_wrapper.desc_channels_field,
            lsl_stream_wrapper.channel_label_field,
            lsl_stream_wrapper.cha_info,
            lsl_stream_wrapper.selected_channels_idx,
            lsl_stream_wrapper.n_cha,
            lsl_stream_wrapper.l_cha
        )

    def update_medusa_parameters(self, medusa_params_initialized, medusa_uid,
                                 medusa_type, desc_channels_field,
                                 channel_label_field, cha_info,
                                 selected_channels_idx, n_cha, l_cha):
        """Use this function to manually update the medusa params"""
        if not medusa_params_initialized:
            raise ValueError('The medusa parameters have not been '
                             'initialized yet. Use function '
                             'set_medusa_parameters instead')
        self.medusa_params_initialized = \
            medusa_params_initialized
        self.medusa_uid = medusa_uid
        self.medusa_type = medusa_type
        self.desc_channels_field = desc_channels_field
        self.channel_label_field = channel_label_field
        self.cha_info = cha_info
        self.selected_channels_idx = selected_channels_idx
        self.n_cha = n_cha
        self.l_cha = l_cha

    def to_serializable_obj(self):
        # TODO: The dictionary is copied by hand due to problems with
        #  lsl_stream_info and lsl_stream_inlet. There has to be a
        #  better way!
        # LSL parameters
        class_dict = dict()
        class_dict['lsl_proc_clocksync'] = self.lsl_proc_clocksync
        class_dict['lsl_proc_dejitter'] = self.lsl_proc_dejitter
        class_dict['lsl_proc_monotonize'] = self.lsl_proc_monotonize
        class_dict['lsl_proc_threadsafe'] = self.lsl_proc_threadsafe
        class_dict['lsl_name'] = self.lsl_name
        class_dict['lsl_type'] = self.lsl_type
        class_dict['lsl_n_cha'] = self.lsl_n_cha
        class_dict['lsl_cha_format'] = self.lsl_cha_format
        class_dict['lsl_uid'] = self.lsl_uid
        class_dict['lsl_source_id'] = self.lsl_source_id
        class_dict['fs'] = self.fs
        class_dict['hostname'] = self.hostname
        class_dict['lsl_stream_info_xml'] = self.lsl_stream_info_xml
        # Additional Medusa parameters
        class_dict['medusa_params_initialized'] = \
            self.medusa_params_initialized
        class_dict['medusa_uid'] = self.medusa_uid
        class_dict['medusa_type'] = self.medusa_type
        class_dict['desc_channels_field'] = self.desc_channels_field
        class_dict['channel_label_field'] = self.channel_label_field
        class_dict['cha_info'] = self.cha_info
        class_dict['selected_channels_idx'] = self.selected_channels_idx
        class_dict['n_cha'] = self.n_cha
        class_dict['l_cha'] = self.l_cha
        return class_dict

    @classmethod
    def from_serializable_obj(cls, dict_data, weak_search=False):
        if weak_search:
            lsl_stream = get_lsl_streams(
                force_one_stream=True,
                name=dict_data['lsl_name'],
                type=dict_data['lsl_type'],
                source_id=dict_data['lsl_source_id'],
                channel_count=dict_data['lsl_n_cha'],
                nominal_srate=dict_data['fs']
            )
        else:
            lsl_stream = get_lsl_streams(
                force_one_stream=True,
                name=dict_data['lsl_name'],
                type=dict_data['lsl_type'],
                uid=dict_data['lsl_uid'],
                source_id=dict_data['lsl_source_id'],
                channel_count=dict_data['lsl_n_cha'],
                nominal_srate=dict_data['fs']
            )
        # Create LSLWrapper
        clocksync = dict_data['lsl_proc_clocksync']
        dejitter = dict_data['lsl_proc_dejitter']
        monotonize = dict_data['lsl_proc_monotonize']
        threadsafe = dict_data['lsl_proc_threadsafe']
        instance = cls(lsl_stream)
        instance.set_inlet(proc_clocksync=clocksync,
                           proc_dejitter=dejitter,
                           proc_monotonize=monotonize,
                           proc_threadsafe=threadsafe)
        # Update medusa params (don't use set_medusa_parameters)
        instance.update_medusa_parameters(
            medusa_params_initialized=dict_data['medusa_params_initialized'],
            medusa_uid=dict_data['medusa_uid'],
            medusa_type=dict_data['medusa_type'],
            desc_channels_field=dict_data['desc_channels_field'],
            channel_label_field=dict_data['channel_label_field'],
            cha_info=dict_data['cha_info'],
            selected_channels_idx=dict_data['selected_channels_idx'],
            n_cha=dict_data['n_cha'],
            l_cha=dict_data['l_cha'],
        )
        return instance


class LSLStreamReceiver:
    """ This class calculates the difference between the LSL clock and the
     local time (time.time()) for synchronization with applications,
     which will use the latter
     """

    def __init__(self, lsl_stream_mds, min_chunk_size=None, max_chunk_size=None,
                 timeout=None, auto_mode=True):
        """Class constructor

        Parameters
        ----------
        lsl_stream_mds: LSLStreamWrapper
            Medusa representation of an LSL stream
        min_chunk_size: int or None
            Min chunk size to receive. It can be used to reduce computing
            load. If None, it will be set automatically.
        max_chunk_size: int or None
            Max chunk size to receive. If None, it will be set automatically.
        timeout: int or None
            Timeout in seconds.If None, it will be set automatically.
        auto_mode: bool
            If True, the max_chunk_size and timeout variables are
            automatically adjusted to avoid problems with strange
            configurations on the transmitter side.
        """
        # LSL info
        self.TAG = '[LSLStreamReceiver] '
        self.lsl_stream = lsl_stream_mds
        # Copy some attributes from lsl stream info for direct access
        self.name = self.lsl_stream.medusa_uid
        self.fs = self.lsl_stream.fs
        self.n_cha = self.lsl_stream.n_cha
        self.l_cha = self.lsl_stream.l_cha
        self.info_cha = self.lsl_stream.cha_info
        self.idx_cha = self.lsl_stream.selected_channels_idx
        self.auto_mode = auto_mode
        # Min chunk size cannot be None. By default, sets the minimum update
        # rate to 10 ms to avoid excessive computing load
        self.min_chunk_size = max(int(0.01 * self.fs), 1) \
            if min_chunk_size is None else min_chunk_size
        # Max chunk size cannot be None. Default max chunk size 2 *
        # min_chunk_size. Set automode=True to update this value on demand
        self.max_chunk_size = max(int(2*self.min_chunk_size), int(self.fs)) \
            if max_chunk_size is None else max_chunk_size
        # Timeout cannot be None in order to avoid blocking processes
        self.timeout = 1.5 * self.max_chunk_size / self.fs \
            if timeout is None else timeout
        # print('LSL stream: %s\nmin_chunk_size: %i\nmax_chunk_size: '
        #       '%i\ntimeout: %.2f' % (self.lsl_stream.lsl_name,
        #                              self.min_chunk_size,
        #                              self.max_chunk_size, self.timeout))
        # Calculate Unix clock offset
        self.unix_clock_offset = \
            np.mean([time.time() - pylsl.local_clock() for _ in range(10)])
        # Calculate LSL clock offset
        self.lsl_clock_offset = \
            np.mean([self.lsl_stream.lsl_stream_inlet.time_correction() for _ in range(10)])
        # Aliasing correction
        self.aliasing_correction = True

        # Initialize auxiliary and debugging variables
        self.chunk_counter = 0
        self.sample_counter = 0
        self.last_t_local = -1
        self.last_t_lsl = -1
        self.init_time = None
        self.last_time = None
        self.hist_unix_clock_offsets = list()
        self.hist_lsl_clock_offsets = list()
        self.hist_local_timestamps = list()
        self.hist_lsl_timestamps = list()

    def get_chunk(self):
        """Get signal chunk. Throws an error if the reception time exceeds
        the timeout
        """
        timer = self.Timer()
        samples = list()
        times = list()

        if self.init_time is None:
            self.init_time = time.time()

        # Estimate the current clock offset between LSL and UNIX local time
        unix_clock_offset = time.time() - pylsl.local_clock()
        lsl_clock_offset = 0
        if not self.lsl_stream.local_stream:
            lsl_clock_offset = self.lsl_stream.lsl_stream_inlet.time_correction()

        # Get data
        while True:
            # Check if we need to update the max_chunk_size and timeout
            if self.auto_mode:
                s_avlbl = self.lsl_stream.lsl_stream_inlet.samples_available()
                if s_avlbl > self.max_chunk_size:
                    self.max_chunk_size = s_avlbl
                    self.timeout = 1.5 * self.max_chunk_size / self.fs
                    # print('LSL stream parameters updated: '
                    #       '%s\nmin_chunk_size: '
                    #       '%i\nmax_chunk_size: '
                    #       '%i\ntimeout: %.2f' %
                    #       (self.lsl_stream.lsl_name, self.min_chunk_size,
                    #        self.max_chunk_size, self.timeout))
            # Get chunk
            chunk, timestamps = self.lsl_stream.lsl_stream_inlet.pull_chunk(
                max_samples=self.max_chunk_size)
            samples += chunk
            times += timestamps
            if len(times) >= self.min_chunk_size:
                # Increment chunk counter
                self.chunk_counter += 1
                self.sample_counter += len(times)
                # LSL time to local time
                lsl_times = np.array(times) + lsl_clock_offset
                local_times = lsl_times + unix_clock_offset
                samples = np.array(samples)
                # Aliasing detection and correction
                if self.aliasing_correction:
                    dt_aliasing = local_times[0] - self.last_t_local
                    if dt_aliasing < 0 and self.last_t_local != -1:
                        print('%sCorrecting an aliasing of %.4f ms...' %
                              (self.TAG, dt_aliasing * 1000))
                        corrected_times = np.linspace(
                            self.last_t_local, local_times[-1], len(local_times) + 1)
                        local_times = corrected_times[1:]

                    dt_aliasing = lsl_times[0] - self.last_t_lsl
                    if dt_aliasing < 0 and self.last_t_lsl != -1:
                        corrected_times = np.linspace(
                            self.last_t_lsl, lsl_times[-1], len(lsl_times) + 1)
                        lsl_times = corrected_times[1:]
                self.last_t_local = local_times[-1]
                self.last_t_lsl = lsl_times[-1]

                # ============================================================ #
                # Debugging synchronization
                # ============================================================ #
                # self.hist_unix_clock_offsets.append(unix_clock_offset)
                # self.hist_lsl_clock_offsets.append(lsl_clock_offset)
                # self.hist_local_timestamps += local_times.tolist()
                # self.hist_lsl_timestamps += lsl_times.tolist()
                # ============================================================ #
                return samples[:, self.idx_cha], local_times, lsl_times

            if timer.get_s() > self.timeout:
                # Update timeout because it can be inadequate for the LSL
                # stream configuration of the outlet (transmitter)
                raise exceptions.LSLStreamTimeout()

    def flush_stream(self):
        """Call this function to stop queueing input data, but preserve the
        StreamInlet. Calling pull_chunk will open the stream again
        """
        self.lsl_stream.lsl_stream_inlet.flush()

    def get_channel_indexes_from_labels(self, l_cha, case_sensitive=False):
        """Returns the index of the channels given by l_cha

        Parameters
        ----------
        l_cha: list or string
            Labels of the channels to get the indexes.
        case_sensitive: boolean
            If true, the search of the indexes is case sensitive
        """
        if isinstance(l_cha, list):
            cha_idx = list()
            for wanted_cha_label in l_cha:
                for idx, cha_label in enumerate(self.l_cha):
                    if case_sensitive:
                        if wanted_cha_label == cha_label:
                            cha_idx.append(cha_idx)
                    else:
                        if wanted_cha_label.lower() == cha_label.lower():
                            cha_idx.append(cha_idx)
            return cha_idx
        else:
            for idx, cha_label in enumerate(self.l_cha):
                if case_sensitive:
                    if l_cha == cha_label:
                        return idx
                else:
                    if l_cha.lower() == cha_label.lower():
                        return idx

    def get_historic_offsets(self):
        return self.hist_unix_clock_offsets, self.hist_lsl_clock_offsets

    class Timer(object):
        """ Represents a watchdog timer. The watchdog timer is used to detect
        failures. The timer is regularly reset to prevent it from timing out.
        """

        def __init__(self):
            self.start_time = time.time()

        def reset(self):
            self.start_time = time.time()

        def get_s(self):
            return time.time() - self.start_time

        def get_ms(self):
            return (time.time() - self.start_time) * 1000.0
