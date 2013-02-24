blink1_trains
=============

Color-coded train departure notification using a blink(1) from http://thingm.com/products/blink-1.html

usage: blink_train_times.py [-h] --api_key API_KEY [--station_id STATION_ID]

Receive train departure information from trafiklab.se and show them via a
blink(1) device.

optional arguments:
  -h, --help            show this help message and exit
  --api_key API_KEY     The API key from trafiklab.se
  --station_id STATION_ID
                        The station ID to be checked
