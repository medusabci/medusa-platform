# BUILT-IN MODULES
import time

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
    lsl streams that have been configured
    """
    for stream in working_lsl_streams:
        if stream.medusa_uid == medusa_uid:
            return False
    return True


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
        self.lsl_name = None
        self.lsl_type = None
        self.lsl_n_cha = None
        self.lsl_cha_format = None
        self.lsl_uid = None
        self.lsl_source_id = None
        self.fs = None
        self.hostname = None
        self.lsl_stream_info_xml = None
        self.lsl_stream_info_json_format = None
        # Additional Medusa parameters
        self.medusa_params_initialized = False
        self.medusa_uid = None
        self.medusa_type = None
        self.desc_channels_field = None
        self.channel_label_field = None
        self.selected_channels_idx = None
        self.n_cha = None
        self.cha_info = None
        self.l_cha = None
        # Set inlet and lsl info
        self.set_inlet()

    def set_inlet(self):
        self.lsl_stream_inlet = pylsl.StreamInlet(self.lsl_stream)
        self.lsl_stream_info = self.lsl_stream_inlet.info()
        # LSL parameters
        self.lsl_name = self.lsl_stream_info.name()
        self.lsl_type = self.lsl_stream_info.type()
        self.lsl_n_cha = self.lsl_stream_info.channel_count()
        self.lsl_cha_format = self.lsl_stream_info.channel_format()
        self.lsl_uid = self.lsl_stream_info.uid()
        self.lsl_source_id = self.lsl_stream_info.source_id()
        self.fs = self.lsl_stream_info.nominal_srate()
        self.hostname = self.lsl_stream_info.hostname()
        self.lsl_stream_info_xml = self.lsl_stream_info.as_xml()
        self.lsl_stream_info_json_format = \
            utils.xml_string_to_json(self.lsl_stream_info_xml)
        if 'desc' not in self.lsl_stream_info_json_format or \
                self.lsl_stream_info_json_format['desc'] == '':
            # This field desc must be a dict
            self.lsl_stream_info_json_format['desc'] = dict()

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
                              selected_channels_idx,
                              cha_info):
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
        medusa_params_initialized: bool
            Tells if this is the first time that the medusa parameters are set
            in this stream or we are updating them from a previous configured
            stream. This avoids problems when reselecting the channels in
            cha_info.
        """
        # Select channels
        n_cha = len(selected_channels_idx)
        cha_info = [cha_info[i] for i in selected_channels_idx]
        l_cha = [info[channel_label_field] for info in cha_info] \
            if channel_label_field is not None else list(range(n_cha))
        # Update parameters
        self.update_medusa_parameters(
            medusa_params_initialized=True,
            medusa_uid=medusa_uid,
            medusa_type=medusa_type,
            desc_channels_field=desc_channels_field,
            channel_label_field=channel_label_field,
            selected_channels_idx=selected_channels_idx,
            n_cha=n_cha,
            cha_info=cha_info,
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
            lsl_stream_wrapper.selected_channels_idx,
            lsl_stream_wrapper.n_cha,
            lsl_stream_wrapper.cha_info,
            lsl_stream_wrapper.l_cha
        )

    def update_medusa_parameters(self, medusa_params_initialized, medusa_uid,
                                 medusa_type, desc_channels_field,
                                 channel_label_field, selected_channels_idx,
                                 n_cha, cha_info, l_cha):
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
        self.selected_channels_idx = selected_channels_idx
        self.n_cha = n_cha
        self.cha_info = cha_info
        self.l_cha = l_cha

    def to_serializable_obj(self):
        # TODO: The dictionary is copied by hand due to problems with
        #  lsl_stream_info and lsl_stream_inlet. There has to be a
        #  better way!
        # LSL parameters
        class_dict = dict()
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
        class_dict['selected_channels_idx'] = self.selected_channels_idx
        class_dict['n_cha'] = self.n_cha
        class_dict['cha_info'] = self.cha_info
        class_dict['l_cha'] = self.l_cha
        return class_dict

    @classmethod
    def from_serializable_obj(cls, dict_data):
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
        instance = cls(lsl_stream)
        # Update medusa params (don't use set_medusa_parameters)
        instance.update_medusa_parameters(
            medusa_params_initialized=dict_data['medusa_params_initialized'],
            medusa_uid=dict_data['medusa_uid'],
            medusa_type=dict_data['medusa_type'],
            desc_channels_field=dict_data['desc_channels_field'],
            channel_label_field=dict_data['channel_label_field'],
            selected_channels_idx=dict_data['selected_channels_idx'],
            n_cha=dict_data['n_cha'],
            cha_info=dict_data['cha_info'],
            l_cha=dict_data['l_cha'],
        )
        return instance


class LSLStreamReceiver:
    """ This class calculates the difference between the LSL clock and the
     local time (time.time()) for synchronization with applications,
     which will use the latter
     """

    def __init__(self, lsl_stream_mds, max_chunk_size=1024, timeout=1):
        """Class constructor

        Parameters
        ----------
        lsl_stream_mds: LSLStreamWrapper
            Medusa representation of a LSL stream
        max_chunk_size: int
            Max chunk size to receive
        timeout: int
            Timeout in seconds.
        """
        # LSL info
        self.TAG = '[LSLStreamReceiver] '
        self.lsl_stream_info = lsl_stream_mds
        self.max_chunk_size = max_chunk_size
        self.timeout = timeout
        # Copy some attributes from lsl stream info for direct access
        self.name = self.lsl_stream_info.medusa_uid
        self.fs = self.lsl_stream_info.fs
        self.n_cha = self.lsl_stream_info.n_cha
        self.l_cha = self.lsl_stream_info.l_cha
        self.info_cha = self.lsl_stream_info.cha_info
        self.idx_cha = self.lsl_stream_info.selected_channels_idx
        self.lsl_clock_offset = \
            np.mean([time.time() - pylsl.local_clock() for i in range(10)])
        self.chunk_counter = 0
        self.last_t = 0
        # ============================================================ #
        # DELETE
        # self.time_offset = None
        # ============================================================ #

    def get_chunk(self):
        """Get signal chunk. Throws an error if the reception time exceeds
        the timeout
        """
        timer = self.Timer()
        while True:
            chunk, timestamps = \
                self.lsl_stream_info.lsl_stream_inlet.pull_chunk(
                    max_samples=self.max_chunk_size
                )
            if len(timestamps) > 0:
                # ============================================================ #
                # DELETE
                # if self.time_offset is None:
                #     self.time_offset = time.time() - timestamps[0]
                # times2 = np.array(timestamps) + self.time_offset
                # ============================================================ #
                # Increment chunk counter
                self.chunk_counter += 1
                # LSL time to local time
                times = np.array(timestamps) + self.lsl_clock_offset
                samples = np.array(chunk)
                # ============================================================ #
                # UNCOMMENT FOR DEBUGGING
                # for i in range(len(times)):
                #     print('#%i, LSL time: %s; New time: %s; Old time: %s; '
                #           'LSL offset: %s, Transmission time: %s; Signal %s' %
                #           (self.chunk_counter, timestamps[i], times[i],
                #            times2[i], self.lsl_clock_offset,
                #            pylsl.local_clock() - timestamps[-1],
                #            str(chunk[i][-1])))
                # ============================================================ #
                # Aliasing detection and correction
                dt_aliasing = \
                    (times[-1] - (len(times) - 1) * 1 / self.fs) - self.last_t
                if dt_aliasing < 0:
                    print('%sCorrecting an aliasing of %.3f ms...' %
                          (self.TAG, dt_aliasing * 1000))
                    corrected_times = np.linspace(self.last_t, times[-1],
                                                  len(times))
                    times = corrected_times
                self.last_t = times[-1]

                return samples[:, self.idx_cha], times

            if timer.get_s() > self.timeout:
                raise exceptions.LSLStreamTimeout()

    def flush_stream(self):
        """Call this function to stop queueing input data, but preserve the
        StreamInlet. Calling pull_chunk will open the stream again
        """
        self.lsl_stream_info.lsl_stream_inlet.flush()

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
