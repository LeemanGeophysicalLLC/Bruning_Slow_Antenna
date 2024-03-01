import serial
import RPi.GPIO as GPIO
from time import sleep
import numpy as np
#import matplotlib.pyplot as plt
import struct
import datetime
import os.path
from os import listdir

use_relay = 'a'
mins_before_write = 1
save_path ='/home/pi/Desktop/DATA/' 



write_success = False
for file in reversed(sorted(listdir(save_path))):
    try:
        this_file_dt = datetime.datetime.strptime(file.split('_')[0], '%Y%m%d%H%M%S')
    except Exception as e:
        print(str(e))
        continue
    if this_file_dt + datetime.timedelta(seconds=mins_before_write*60) > datetime.datetime.utcnow() - datetime.timedelta(seconds=mins_before_write*60+30):
        write_success = True
        break
bytes_before_write = 5400000*mins_before_write

def convert_adc_to_decimal(value):
    modulo = 1 << 24
    max_value = (1 << 23) - 1
    if value > max_value:
        value -= modulo
    return value

def decode_data_packet(mp):

    result = dict()
    result['start_byte'] = struct.unpack('B', mp[0:1])[0]
    result['b1'] = struct.unpack('B', mp[1:2])[0]
    result['b2'] = struct.unpack('B', mp[2:3])[0]
    result['b3'] = struct.unpack('B', mp[3:4])[0]
    result['adc_pps_micros'] = struct.unpack('I', mp[4:8])[0]
    result['end_byte'] = struct.unpack('B', mp[8:9])[0]
    adc_hex = mp[1:4].hex()
    adc_ba = bytearray()
    adc_ba += mp[1:2]
    adc_ba += mp[2:3]
    adc_ba += mp[3:4]
    adc_ba += b'\x00'
    
    #print(mp[3:4])
    #print(adc_ba)
    adc_reading = struct.unpack('>i', adc_ba[:])[0]    
    
    adc_reading = mp[1]
    adc_reading = (adc_reading << 8) | mp[2]
    adc_reading = (adc_reading << 8) | mp[3]
    adc_reading = convert_adc_to_decimal(adc_reading)

    
    result['adc_reading'] = adc_reading
    return result
    
SERIAL_SPEED = 2000000

#def do_run(bytes_to_read=972000000):
def do_run(bytes_to_read=38880000000):
    global write_success
    global pin_LED_status
    stamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S_%f") 
    print(stamp)    
    ser = serial.Serial('/dev/ttyACM0', SERIAL_SPEED, timeout=1)
    ser.flush()
    bytes_read = 0
    byte_count_since_last_write = 0
    bytes_data = bytearray()
    waiting = []
    while bytes_read < bytes_to_read:
        bytes_available = ser.in_waiting
        s = ser.read(bytes_available)
        #s = ser.read(1)
        bytes_data += s
       # byte_count_since_last_write += s
        if write_success:
            if pin_LED_status == 1000:
                GPIO.output(pin_LED, GPIO.LOW)
                pin_LED_status = -1
            elif pin_LED_status == 500:
                GPIO.output(pin_LED, GPIO.HIGH)
            pin_LED_status += 1
        if (byte_count_since_last_write >= bytes_before_write): #27000000):
            print('writing file')
            if stamp is not None:
                name = os.path.join(save_path,stamp + '_' + use_relay + '.raw')
                with open(name, mode='wb') as file:
                    file.write(bytes_data)
                stamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S_%f") #None
            else:
                name = os.path.join(save_path,datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S_%f") + '_' + use_relay + '.raw')
                with open(name, mode='wb') as file:
                    file.write(bytes_data)
            print(name)
            write_success = True
            bytes_data = bytearray()
            byte_count_since_last_write = 0
            print(ser.in_waiting)
        #bytes_read += 1
        bytes_read += bytes_available
        byte_count_since_last_write += bytes_available
        #if (bytes_read % 5000) == 0:
           
        #print(bytes_read, bytes_available)    
        
    ser.close()
    return bytes_data


pin_relay_a = 5
pin_relay_b = 6
pin_relay_c = 13
pin_LED = 19
pin_overflow_buffer = 10
pin_overflow_serial = 11

GPIO.setmode(GPIO.BCM)
GPIO.setup(pin_relay_a, GPIO.OUT)
GPIO.setup(pin_relay_b, GPIO.OUT)
GPIO.setup(pin_relay_c, GPIO.OUT)
GPIO.setup(pin_LED, GPIO.OUT)
GPIO.setup(pin_overflow_buffer, GPIO.IN)
GPIO.setup(pin_overflow_serial, GPIO.IN)


#ba = bytearray(do_run())

#print(do_run())

GPIO.output(pin_relay_a, GPIO.HIGH) if use_relay == 'a' else GPIO.output(pin_relay_a, GPIO.LOW)
GPIO.output(pin_relay_b, GPIO.HIGH) if use_relay == 'b' else GPIO.output(pin_relay_b, GPIO.LOW)
GPIO.output(pin_relay_c, GPIO.HIGH) if use_relay == 'c' else GPIO.output(pin_relay_c, GPIO.LOW)
GPIO.output(pin_LED, GPIO.LOW)
pin_LED_status = False

sleep(2)
ba = do_run()
#ba = bytearray(ba)
#print(ba)
print(type(ba))

data_start_bytes = []
data_packet_length = 8
# Determine the valid starting bytes for data packets
for i in range(len(ba) - data_packet_length):
    if (ba[i] == 190) and (ba[i+data_packet_length] == 239):
        data_start_bytes.append(i)
        
data_raw_packets = []
data_packets = []

for sb in data_start_bytes[:-1]:
    data_raw_packets.append(ba[sb:sb+12])
    data_packets.append(decode_data_packet(ba[sb:sb+12]))

starts = []
adc_ready = []
adc = []
end = []
for dp in data_packets:
    starts.append(dp['start_byte'])
    adc_ready.append(dp['adc_pps_micros'])
    adc.append(dp['adc_reading'])
    end.append(dp['end_byte'])
starts = np.array(starts)
adc_ready = np.array(adc_ready)
adc = np.array(adc)
end = np.array(end)

print(adc.shape, adc.dtype)
delta_t_adc = (adc_ready[-1]-adc_ready[0])*1e-6
sample_rate = adc_ready.shape[0]/delta_t_adc
print(f"Elapsed time {delta_t_adc:6.3} s with sample rate {sample_rate:6.1f} Hz")

name = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S") + '_' + use_relay + '.txt'

print('done with file')

GPIO.output(pin_relay_a, GPIO.LOW)
GPIO.output(pin_relay_b, GPIO.LOW)
GPIO.output(pin_relay_c, GPIO.LOW)

GPIO.cleanup()
