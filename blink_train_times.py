#!/usr/bin/python
# -*- coding: utf8 -*-

import time, sys
import urllib
from xml.dom.minidom import parse, parseString
import threading
import argparse

import signal
from datetime import datetime

try:
	import usb
except ImportError:
	print "PyUSB is needed"
	sys.exit()

class blink_thread(threading.Thread):
	
	current_color = [0, 0, 0]

	cancel = False
	currently_blinking = False

	blink_repetitions = 0

	current_blink_delay = 0

	blink_device = None

	def get_color_string(self, color):
		color_string = ""
		for single_color in color:
			color_string = color_string + ", " + str(single_color)
		return color_string
	
	def __init__(self, color=[255,0,0]):
		self.cancel = False
		self.currently_blinking = False
		self.current_blink_delay = 250
		self.current_color = color
		self.blink_repetitions = 1

		# find the blink(1) device
		self.blink_device = usb.core.find(idVendor=0x27b8, idProduct=0x01ed)
		assert self.blink_device is not None, "No blink(1) device found..."

		threading.Thread.__init__(self)

	def stop_thread(self):
		self.cancel = True

	def set_new_color(self, new_color):
		self.current_color = new_color

	def blink(self, time, repetitions):
		self.currently_blinking = True
		self.current_blink_delay = time
		self.blink_repetitions = repetitions

	def stop_blinking(self):
		self.currently_blinking = False

	def run(self):
		# fade to self.current_color every second
		while True and not self.cancel:
			# build the USB command
			bmRequestTypeOut = usb.util.build_request_type(usb.util.CTRL_OUT, usb.util.CTRL_TYPE_CLASS, usb.util.CTRL_RECIPIENT_INTERFACE)
			# fade to color with timing set below: 0x63 
			action = 0x63
			red = self.current_color[0]
			green = self.current_color[1]
			blue = self.current_color[2]
			# a device timing tick is 10ms long, so 50 ticks will lead to a 500ms fade
			ticks = 50
			th = (ticks & 0xff00) >> 8
			tl = ticks & 0x00ff
			self.blink_device.ctrl_transfer(bmRequestTypeOut, 0x09, (3 << 8) | 0x01, 0, [0x00, action, red, green, blue, th, tl, 0x00, 0x00])
			time.sleep(1)

class blink_controller():

	spawned_blink_thread = None

	def set_new_color(self, new_color):
		self.spawned_blink_thread.set_new_color(new_color)

	def blink(self, time=500, repetitions=1):
		self.spawned_blink_thread.blink(time, repetitions)

	def stop_blinking(self):
		self.spawned_blink_thread.stop_blinking()

	def __init__(self, new_color):
		self.spawned_blink_thread = blink_thread()

	def spawn_blink_thread(self):
		self.spawned_blink_thread.start()

	def goodbye(self):
		self.spawned_blink_thread.stop_thread()


def find_correct_departure(dom):
	for train in dom.getElementsByTagName('Trains'):
		for train_departure in train.getElementsByTagName('DpsTrain'):
			for direction in train_departure.getElementsByTagName('JourneyDirection'):
				if direction.firstChild.data == '2':
					return train_departure

def find_next_departure(dom):
	departure = find_correct_departure(dom)
	if departure == None:
		# print "No matching departure found..."
		# if no departure was found, just use a date which will cause the device to blink red
		return "2012-12-12T12:12:12"
	else:
		return departure.getElementsByTagName('ExpectedDateTime')[0].firstChild.data

def get_information_and_update_blink(blink_instance, dom):
	next_departure = time.strptime(find_next_departure(dom), "%Y-%m-%dT%H:%M:%S")
	dt = datetime.fromtimestamp(time.mktime(next_departure))

	time_now = datetime.now()

	time_difference = dt - time_now

	print str(time_difference.seconds) + " seconds until the next train leaves to the city, set to",
	if time_difference.seconds > 1200:
		# the next train comes in more than 20 minutes, turn to red
		print "red..."
		blink_instance.set_new_color([255, 0, 0])
	elif time_difference.seconds > 720:
		# train comes in more than 12 minutes, turn to green
		print "green..."
		blink_instance.set_new_color([0, 255, 0])
	elif time_difference.seconds > 480:
		# train comes in less than 12 but more than 8 minutes, turn to yellow
		print "yellow..."
		blink_instance.set_new_color([255, 255, 0])
	else:
		# the next train leaves in less than 8 minutes, turn to red
		print "red..."
		blink_instance.set_new_color([255, 0, 0])

# has to be global to be visible to the signal handler function
train_blink_controller = blink_controller([255, 0,0])

def handler(signum, frame):
	print "\nGoodbye"
	train_blink_controller.goodbye()
	sys.exit()

def get_traffic_information(schedule_url):
	try:
		current_information = urllib.urlopen(schedule_url)
		return current_information
	except urllib.error.URLError:
		print "An error occured while trying to fetch the new traffic information data, using old data..."
		return None


def main():
	parser = argparse.ArgumentParser(description='Receive train departure information from trafiklab.se and show them via a blink(1) device.')
	parser.add_argument('--api_key', 
								action='store', 
								default="", 
								help='The API key from trafiklab.se',
								required=True)

	parser.add_argument('--station_id', 
								action='store', 
								default="9526", # Flemingsberg, commuter trains
								help='The station ID to be checked',
								required=False)

	args = parser.parse_args()
	# print args.api_key
	# print args.station_id

	train_blink_controller.spawn_blink_thread()

	schedule_url = "https://api.trafiklab.se/sl/realtid/GetDpsDepartures?key=" + str(args.api_key) + "&siteid=" + str(args.station_id)

	current_information = None
	saved_information = None

	signal.signal(signal.SIGINT, handler)

	while True:
		current_information = get_traffic_information(schedule_url)
		if current_information != None:
			dom = parse(current_information)
			saved_information = current_information
		else:
			if saved_information == None:
				print "An error occured while trying to get the traffic information and no stored information was found..."
				sys.exit()
			dom = parse(saved_information)
		get_information_and_update_blink(train_blink_controller, dom)
		time.sleep(10)

if __name__ == "__main__":
    main()
