from machine import Pin
import time
import micropython
import _thread
import array

'''
    de-dh 2024. MIT License.
    
    ThermoPro TP65S Micropython Receiver
    
    Receive and decode 433 MHz RF signal from ThermoPro TP65S outdoor
    temperature sensor on Raspberry Pi Pico or Esp32 with RX470C-V01
    module. RX470C-V01 works with 3.3V and 5V and only needs one GPIO-
    Pin for data connection to mcu. For best result, the module should
    be equipped with an additional resistor and a ceramic supply bypass
    capacitor, see documentation.
    
    Data is encoded similar to a morse encoding with alternating high
    and low pulses. Data is transmitted every 50s.
    High pulses have fixed durations of ~500us followed by low pulse
    durations of 2000us or 4000us encoding 0 and 1, respectively.
    Transmission is repeated six times seperated by a 8800us gap low
    pulse.
    
    Each message consists of 37 high and low pulses + gap.
    sync_sequence = '1001111001000000'
    data = 12 Bit
    end_sequence = '000000011' + gap
    
    Parts of the signal decoding function are based on Peter Hinch's
    micropython_remote RX class provided under MIT license.
'''

RECEIVER_PIN = 18 		# GPIO-Pin with 433 Mhz receiver
DEBUG_MESSAGE = False 	# Show pulse data for debugging
RX_MIN_LEN = 38  		# Minimum length of a transmission (37 low pulses + gap)
MAX_PULSES = 400 		# Maximum number of pulses in receiver buffer


low_pulse_durations = array.array('I', [0] * MAX_PULSES)
low_pulse_index = 0

last_falling_time = 0

lock = _thread.allocate_lock()

micropython.alloc_emergency_exception_buf(100)


def rx_interrupt(pin):
    global last_rising_time, last_falling_time, low_pulse_index
    
    current_time = time.ticks_us()
    
    if pin.value() == 1:
        if last_falling_time != 0:
            low_duration = time.ticks_diff(current_time, last_falling_time)
            
            if low_pulse_index < MAX_PULSES:
                with lock:
                    if 1000 < low_duration < 9000: # Prefilter pulses
                        low_pulse_durations[low_pulse_index] = low_duration
                        low_pulse_index += 1
    else:
        last_falling_time = current_time


def find_clusters(data):
    overall_mean = sum(data) / len(data)
    
    lower_group = [x for x in data if x < overall_mean]
    upper_group = [x for x in data if x >= overall_mean]
    
    lower_mean = (sum(lower_group) / len(lower_group)) if lower_group else None
    upper_mean = (sum(upper_group) / len(upper_group)) if upper_group else None
    
    data_mean = (upper_mean + lower_mean) / 2
    
    return int(data_mean), int(lower_mean), int(upper_mean)



def decode_tp_signal(pulse_durations, debug = True):
    if not pulse_durations or pulse_durations is None: return None
    
    diffs = list(pulse_durations)
    frames = len(diffs)
    
    # Prefilter pulse lengths either in irq or here
    # diffs = [x for x in diffs if 1500 < x < 9000]
    
    # Abort if pulse list is too short
    if len(diffs) < RX_MIN_LEN: return None
    
    ''' Algorithm used to split pulse array in single transmission
        by identifying TX gap and averaging individual frames.
        Based on Peter Hinch's micropython_remote
        RX class provided under MIT license '''
    
    gap = round(max(diffs) * 0.9)  # Allow for tolerance
    # Discard data prior to and including 1st gap
    start = 0
    while diffs[0] < gap:
        start += 1
        diffs.pop(0)
    diffs.pop(0)

    # Create individual lists for each message
    res = []  # list of frames. Each entry ends with gap.
    while True:
        lst = []
        try:
            while diffs[0] < gap:
                lst.append(diffs.pop(0))
            lst.append(diffs.pop(0))  # Add the gap
        except IndexError:
            break  # all done
        res.append(lst)
    
    # include only transmissions of correct length
    res = [r for r in res if len(r) == RX_MIN_LEN] # 37 Pulses + Gap = 38
    
    n_messages = len(res) # No of messages
    if n_messages == 0: return None

    m = [round(sum(x)/n_messages) for x in zip(*res)]  # Mean values
    
    gap_mean = m[-1] # for debugging
    m.pop(-1) # Remove gap from individual transmissions for evaluation
    
    # Calculate mean pulse durations for parsing to binary string
    pulse_mean, lower_mean, upper_mean = find_clusters(m[:])
    
    # Use mean pulse length to set bounds for conversion of high and low pulses
    # Short pulses: ~ 2 ms -> 0
    # Long pulses:  ~ 4 ms -> 1
    binary_string = ''
    for i in m:
        if i < pulse_mean:
            binary_string += '0'
        elif i >= pulse_mean:
            binary_string += '1'
            
    if debug:
        debug_msg = f'------------------------------------------------------------\n'
        debug_msg += f'Input {frames} pulses. Message start {start}.\n'
        debug_msg += f'Averaging {n_messages} transmissions with {len(m)} pulses. Mean values:\n'
        debug_msg += f'Low: {lower_mean} us   High: {upper_mean} us   '
        debug_msg += f'Pulse: {pulse_mean} us   Gap: {gap_mean} us\n'
        debug_msg += f'Binary string: {binary_string}\n'
        print(debug_msg)

    return binary_string
    

def decode_tp_data(binary_string):
    if not(binary_string) or binary_string is None:
        return None
    sync_sequence = '1001111001000000'
    end_sequence = '000000011'
    if binary_string.startswith(sync_sequence) and binary_string.endswith(end_sequence):
        data_bits = binary_string[len(sync_sequence):-len(end_sequence)]
        if len(data_bits) == 12:
            data_value = int(data_bits, 2)
            if data_value >= 1024: data_value = data_value - 4096
            return data_value * 0.1
    return None

try:
    last_rcv = time.ticks_ms()
    
    # Wait for receiver to startup before attaching irq
    # Increases reliability to capture signal
    time.sleep(3)
    receiver = Pin(RECEIVER_PIN, Pin.IN)
    receiver.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=rx_interrupt)
    print(f'Starting 433 MHz receiver on Pin {RECEIVER_PIN}.')
    
    while True:
        delta_rcv = int(abs(time.ticks_diff(last_rcv, time.ticks_ms()) / 1000))
        delta_str = 'dt: {:02d} s'.format(delta_rcv)
        print(delta_str, end='\r')
            
        time.sleep(2)
        
        if low_pulse_index > RX_MIN_LEN:
            with lock:
                low_pulse_copy = low_pulse_durations[:low_pulse_index]
                low_pulse_index = 0
            
            binary_message = decode_tp_signal(low_pulse_copy, DEBUG_MESSAGE)
            
            if binary_message:
                data_value = decode_tp_data(binary_message)
                if data_value is not None:
                    timestamp = time.localtime()
                    timestamp_formatted = '[{:02d}:{:02d}:{:02d}]'.format(timestamp[3],
                                                                          timestamp[4],
                                                                          timestamp[5])
                    
                    data_formatted = '{:.1f} °C'.format(data_value)
                    
                    print(timestamp_formatted + ': ' + data_formatted)
                    last_rcv = time.ticks_ms()

except KeyboardInterrupt:
    print('Programm beendet.')
